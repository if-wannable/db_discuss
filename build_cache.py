import sqlite3, time, json

DB = '/opt/douban-api/douban.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA busy_timeout=60000')

# === stats_cache ===
print('=== 1/3 创建 stats_cache ===')
conn.execute('DROP TABLE IF EXISTS stats_cache')
conn.execute('CREATE TABLE stats_cache (topics INT, posts INT, authors INT)')

t0 = time.time()
topics_count = conn.execute('SELECT COUNT(*) FROM topics').fetchone()[0]
print(f'  topics: {topics_count} ({time.time()-t0:.1f}s)')

t0 = time.time()
posts_count = conn.execute('SELECT COUNT(*) FROM posts').fetchone()[0]
print(f'  posts: {posts_count} ({time.time()-t0:.1f}s)')

t0 = time.time()
authors_count = conn.execute("SELECT COUNT(DISTINCT author_id) FROM posts WHERE author_id <> ''").fetchone()[0]
print(f'  authors: {authors_count} ({time.time()-t0:.1f}s)')

conn.execute('INSERT INTO stats_cache VALUES (?, ?, ?)', (topics_count, posts_count, authors_count))
conn.commit()
print('  stats_cache 填充完成')

# === top_authors_cache ===
print('\n=== 2/3 创建 top_authors_cache ===')
conn.execute('DROP TABLE IF EXISTS top_authors_cache')
conn.execute('CREATE TABLE top_authors_cache (author_id TEXT, posts INT, name TEXT)')

# Step 1: 覆盖索引扫描取 top 20 author_id (不回表，快)
t0 = time.time()
top_ids = conn.execute("""
    SELECT author_id, COUNT(*) AS posts
    FROM posts WHERE author_id <> ''
    GROUP BY author_id ORDER BY posts DESC LIMIT 20
""").fetchall()
print(f'  top 20 ids 取出 ({time.time()-t0:.1f}s)')

# Step 2: 只查 20 个作者的名字 (20 次查询，每次几行)
for row in top_ids:
    aid, posts = row['author_id'], row['posts']
    name_row = conn.execute("""
        SELECT author_name FROM posts
        WHERE author_id = ? AND author_name <> '' AND author_name IS NOT NULL
        ORDER BY time_sort DESC LIMIT 1
    """, (aid,)).fetchone()
    name = name_row['author_name'] if name_row else ''
    conn.execute('INSERT INTO top_authors_cache VALUES (?, ?, ?)', (aid, posts, name))
    print(f'  {aid}: {posts} posts, {name}')

conn.commit()
print('  top_authors_cache 填充完成')

# === groups_cache ===
print('\n=== 3/3 创建 groups_cache ===')
conn.execute('DROP TABLE IF EXISTS groups_cache')
conn.execute('CREATE TABLE groups_cache (group_id TEXT, name TEXT, topics INT, posts INT)')

t0 = time.time()
rows = conn.execute("""
    SELECT g.group_id, g.name,
           (SELECT COUNT(*) FROM topics t WHERE t.group_id = g.group_id) AS topics,
           (SELECT COUNT(*) FROM posts p JOIN topics t ON t.url = p.url
            WHERE t.group_id = g.group_id) AS posts
    FROM groups g ORDER BY posts DESC
""").fetchall()
print(f'  groups 查询完成: {len(rows)}行 ({time.time()-t0:.1f}s)')

for r in rows:
    conn.execute('INSERT INTO groups_cache VALUES (?, ?, ?, ?)',
                 (r['group_id'], r['name'], r['topics'], r['posts']))
conn.commit()
print('  groups_cache 填充完成')

# === 验证 ===
print('\n=== 验证 ===')
s = conn.execute('SELECT * FROM stats_cache').fetchone()
print(f'stats: topics={s["topics"]}, posts={s["posts"]}, authors={s["authors"]}')
print(f'top authors: {len(conn.execute("SELECT * FROM top_authors_cache").fetchall())} rows')
print(f'groups: {len(conn.execute("SELECT * FROM groups_cache").fetchall())} rows')

conn.close()
print('\n=== 全部完成 ===')
