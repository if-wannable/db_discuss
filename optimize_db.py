import sqlite3, time

DB = '/opt/douban-api/douban.db'
conn = sqlite3.connect(DB)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA busy_timeout=60000')

print('=== 创建覆盖索引 (author_id, author_name) ===')
print('这可能需要几分钟，请等待...')
t0 = time.time()
try:
    conn.execute('CREATE INDEX IF NOT EXISTS idx_posts_author_name ON posts(author_id, author_name)')
    print(f'索引创建完成 ({time.time()-t0:.1f}s)')
except Exception as e:
    print(f'创建失败: {e} ({time.time()-t0:.1f}s)')

print()
print('=== 测试 top authors 查询 ===')
t0 = time.time()
rows = conn.execute("""
    SELECT author_id, COUNT(*) AS posts, MAX(author_name) AS name
    FROM posts WHERE author_id <> ''
    GROUP BY author_id ORDER BY posts DESC LIMIT 20
""").fetchall()
print(f'top authors: {len(rows)}行 ({time.time()-t0:.1f}s)')

print()
print('=== 测试 stats 查询 ===')
t0 = time.time()
totals = conn.execute(
    "SELECT (SELECT COUNT(*) FROM topics), (SELECT COUNT(*) FROM posts), "
    "(SELECT COUNT(DISTINCT author_id) FROM posts WHERE author_id <> '')"
).fetchone()
print(f'stats: topics={totals[0]}, posts={totals[1]}, authors={totals[2]} ({time.time()-t0:.1f}s)')

print()
print('=== 测试 groups 查询 ===')
t0 = time.time()
rows = conn.execute("""
    SELECT g.group_id, g.name,
           (SELECT COUNT(*) FROM topics t WHERE t.group_id = g.group_id) AS topics,
           (SELECT COUNT(*) FROM posts p JOIN topics t ON t.url = p.url
            WHERE t.group_id = g.group_id) AS posts
    FROM groups g ORDER BY posts DESC
""").fetchall()
print(f'groups: {len(rows)}行 ({time.time()-t0:.1f}s)')

print()
print('=== 测试 author lookup ===')
t0 = time.time()
rows = conn.execute("""
    SELECT p.seq, p.type, p.url, t.title, p.author_name, p.content, p.time
    FROM posts p JOIN topics t ON t.url = p.url
    WHERE p.author_id = ? LIMIT 5
""", ('196402633',)).fetchall()
print(f'author lookup: {len(rows)}行 ({time.time()-t0:.1f}s)')

conn.close()
print('\n=== 优化完成 ===')
