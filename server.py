#!/usr/bin/env python3
"""豆瓣讨论库的只读查询服务（FastAPI）。

本地运行：
    python server.py
或：
    uvicorn server:app --host 127.0.0.1 --port 8000

环境变量：
    DOUBAN_DB  数据库路径，默认与脚本同目录的 douban.db
    HOST/PORT  监听地址与端口（python server.py 直跑时生效）
"""
from __future__ import annotations

import csv
import io
import os
import sqlite3
import threading
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DOUBAN_DB", BASE_DIR / "douban.db"))
STATIC_DIR = BASE_DIR / "static"

_local = threading.local()
_UNKNOWN = "时间未知"


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.conn = conn
    return conn


app = FastAPI(title="豆瓣讨论查询")


@app.get("/health")
def health():
    return {"ok": True, "db": str(DB_PATH), "exists": DB_PATH.exists()}


@app.get("/api/groups")
def api_groups():
    rows = get_conn().execute(
        """
        SELECT g.group_id, g.name,
               (SELECT COUNT(*) FROM topics t WHERE t.group_id = g.group_id) AS topics,
               (SELECT COUNT(*) FROM posts p JOIN topics t ON t.url = p.url
                WHERE t.group_id = g.group_id) AS posts
        FROM groups g
        ORDER BY posts DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/stats")
def api_stats():
    conn = get_conn()
    totals = dict(conn.execute(
        "SELECT (SELECT COUNT(*) FROM topics), (SELECT COUNT(*) FROM posts), "
        "(SELECT COUNT(DISTINCT author_id) FROM posts WHERE author_id <> '')"
    ).fetchone())
    top = conn.execute(
        """
        SELECT author_id, COUNT(*) AS posts, MAX(author_name) AS name
        FROM posts WHERE author_id <> ''
        GROUP BY author_id ORDER BY posts DESC LIMIT 20
        """
    ).fetchall()
    return {"topics": totals[0], "posts": totals[1], "authors": totals[2], "top_authors": [dict(r) for r in top]}


@app.get("/api/author/{author_id}")
def api_author(
    author_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    group_id: str = Query(""),
    ptype: str = Query("", alias="type"),
    min_time: str = Query(""),
    max_time: str = Query(""),
    q: str = Query(""),
    order: str = Query("desc"),
):
    conn = get_conn()

    where = "p.author_id = ?"
    params: list = [author_id]
    if group_id:
        where += " AND t.group_id = ?"
        params.append(group_id)
    if ptype:
        where += " AND p.type = ?"
        params.append(ptype)
    if min_time:
        where += " AND substr(p.time, 1, 10) >= ?"
        params.append(min_time)
    if max_time:
        where += " AND substr(p.time, 1, 10) <= ?"
        params.append(max_time)
    if q:
        where += " AND instr(p.content, ?) > 0"
        params.append(q)

    summary = dict(conn.execute(
        f"""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN p.type = 'discussion' THEN 1 ELSE 0 END), 0) AS discussions,
               COALESCE(SUM(CASE WHEN p.type <> 'discussion' THEN 1 ELSE 0 END), 0) AS replies,
               MIN(NULLIF(substr(p.time, 1, 19), '')) AS first_time,
               MAX(NULLIF(substr(p.time, 1, 19), '')) AS last_time
        FROM posts p JOIN topics t ON t.url = p.url WHERE {where}
        """,
        params,
    ).fetchone())

    name_row = conn.execute(
        "SELECT author_name, COUNT(*) AS c FROM posts "
        "WHERE author_id = ? AND author_name <> '' "
        "GROUP BY author_name ORDER BY c DESC LIMIT 1",
        (author_id,),
    ).fetchone()

    grp_rows = conn.execute(
        """
        SELECT t.group_id, g.name, COUNT(*) AS count
        FROM posts p
        JOIN topics t ON t.url = p.url
        LEFT JOIN groups g ON g.group_id = t.group_id
        WHERE p.author_id = ?
        GROUP BY t.group_id ORDER BY count DESC
        """,
        (author_id,),
    ).fetchall()

    direction = "ASC" if order == "asc" else "DESC"
    posts = conn.execute(
        f"""
        SELECT p.seq, p.type, p.url, t.title, p.author_name, p.content,
               p.time, p.quote, p.quote_author, t.group_id, g.name AS group_name
        FROM posts p
        JOIN topics t ON t.url = p.url
        LEFT JOIN groups g ON g.group_id = t.group_id
        WHERE {where}
        ORDER BY CASE WHEN p.time = '' OR p.time = ? OR p.time IS NULL THEN '9999'
                      ELSE substr(p.time, 1, 19) END {direction},
                 p.seq {direction}
        LIMIT ? OFFSET ?
        """,
        params + [_UNKNOWN, limit, offset],
    ).fetchall()

    return {
        "author_id": author_id,
        "author_name": name_row["author_name"] if name_row else "",
        "total": summary["total"],
        "discussions": summary["discussions"],
        "replies": summary["replies"],
        "first_time": summary["first_time"],
        "last_time": summary["last_time"],
        "groups": [dict(r) for r in grp_rows],
        "limit": limit,
        "offset": offset,
        "posts": [dict(r) for r in posts],
    }


@app.get("/api/author/{author_id}/export")
def api_author_export(
    author_id: str,
    group_id: str = Query(""),
    ptype: str = Query("", alias="type"),
    min_time: str = Query(""),
    max_time: str = Query(""),
    q: str = Query(""),
    order: str = Query("asc"),
):
    conn = get_conn()
    where = "p.author_id = ?"
    params: list = [author_id]
    if group_id:
        where += " AND t.group_id = ?"
        params.append(group_id)
    if ptype:
        where += " AND p.type = ?"
        params.append(ptype)
    if min_time:
        where += " AND substr(p.time, 1, 10) >= ?"
        params.append(min_time)
    if max_time:
        where += " AND substr(p.time, 1, 10) <= ?"
        params.append(max_time)
    if q:
        where += " AND instr(p.content, ?) > 0"
        params.append(q)

    direction = "ASC" if order == "asc" else "DESC"
    rows = conn.execute(
        f"""
        SELECT p.type, t.title, p.url, p.author_id, p.author_name,
               p.content, p.time, p.quote, p.quote_author,
               t.group_id, g.name AS group_name
        FROM posts p
        JOIN topics t ON t.url = p.url
        LEFT JOIN groups g ON g.group_id = t.group_id
        WHERE {where}
        ORDER BY CASE WHEN p.time = '' OR p.time = ? OR p.time IS NULL THEN '9999'
                      ELSE substr(p.time, 1, 19) END {direction},
                 p.seq {direction}
        """,
        params + [_UNKNOWN],
    ).fetchall()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "type", "discussion title", "url", "author_id", "author_name",
        "content", "time", "quote", "quote_author", "group_id", "group_name",
    ])
    for r in rows:
        w.writerow([
            r["type"], r["title"], r["url"], r["author_id"], r["author_name"],
            r["content"], r["time"], r["quote"], r["quote_author"],
            r["group_id"], r["group_name"],
        ])

    data = "\ufeff" + buf.getvalue()
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="douban_author_{author_id}.csv"'},
    )


@app.get("/api/author-suggest")
def api_author_suggest(q: str = Query("", min_length=1)):
    if not q.isdigit():
        return []
    rows = get_conn().execute(
        """
        SELECT author_id, COUNT(*) AS posts, MAX(substr(time, 1, 19)) AS last
        FROM posts WHERE author_id LIKE ?
        GROUP BY author_id ORDER BY posts DESC LIMIT 15
        """,
        (q + "%",),
    ).fetchall()
    return [dict(r) for r in rows]


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/download/douban.db.gz")
def download_db():
    path = BASE_DIR / "douban.db.gz"
    if not path.exists():
        return {"error": "douban.db.gz not found"}
    return FileResponse(path, media_type="application/gzip", filename="douban.db.gz")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
    )
