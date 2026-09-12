#!/bin/bash
# 豆瓣讨论查询 - 一键部署脚本 (Ubuntu/Debian)
# 用法: 在服务器上和 server.py、douban.db.gz、static/ 放在同一目录，然后运行 bash deploy.sh
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

APP_DIR=/opt/douban-api
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${GREEN}=== 1/7 安装系统依赖 ===${NC}"
apt update && apt install -y python3 python3-venv python3-pip nginx

echo -e "${GREEN}=== 2/7 创建应用目录 ===${NC}"
mkdir -p $APP_DIR/static

echo -e "${GREEN}=== 3/7 复制应用文件 ===${NC}"
cp "$SCRIPT_DIR/server.py" $APP_DIR/
cp -r "$SCRIPT_DIR/static/"* $APP_DIR/static/ 2>/dev/null || cp -r "$SCRIPT_DIR/static" $APP_DIR/
cp "$SCRIPT_DIR/requirements.txt" $APP_DIR/

echo -e "${GREEN}=== 4/7 设置 Python 环境 ===${NC}"
python3 -m venv $APP_DIR/.venv
$APP_DIR/.venv/bin/pip install --upgrade pip -q
$APP_DIR/.venv/bin/pip install -r $APP_DIR/requirements.txt -q

echo -e "${GREEN}=== 5/7 处理数据库 ===${NC}"
if [ -f "$SCRIPT_DIR/douban.db.gz" ]; then
    echo "解压 douban.db.gz ..."
    gunzip -c "$SCRIPT_DIR/douban.db.gz" > $APP_DIR/douban.db
    echo "数据库大小: $(du -h $APP_DIR/douban.db | cut -f1)"
elif [ -f "$SCRIPT_DIR/douban.db" ]; then
    cp "$SCRIPT_DIR/douban.db" $APP_DIR/douban.db
    echo "数据库大小: $(du -h $APP_DIR/douban.db | cut -f1)"
else
    echo -e "${RED}错误: 未找到 douban.db.gz 或 douban.db${NC}"
    echo "请先将数据库文件上传到 $SCRIPT_DIR/"
    exit 1
fi

echo -e "${GREEN}=== 6/7 配置 Nginx ===${NC}"
cat > /etc/nginx/sites-available/douban << 'NGINX_EOF'
server {
    listen 80;
    server_name _;

    # 静态文件直接由 nginx 处理（更快）
    location /static/ {
        alias /opt/douban-api/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # 禁用数据库下载端点（538MB，避免占用带宽）
    location /download/ {
        return 403;
    }

    # 其余请求代理到 uvicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;

        # gzip 压缩 JSON 响应，节省带宽
        gzip on;
        gzip_types application/json text/csv;
        gzip_min_length 1000;
    }
}
NGINX_EOF

ln -sf /etc/nginx/sites-available/douban /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
systemctl enable nginx

echo -e "${GREEN}=== 7/7 配置并启动服务 ===${NC}"
cat > /etc/systemd/system/douban-api.service << 'SYSTEMD_EOF'
[Unit]
Description=Douban Discussion API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/douban-api
Environment=DOUBAN_DB=/opt/douban-api/douban.db
ExecStart=/opt/douban-api/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

systemctl daemon-reload
systemctl enable douban-api
systemctl restart douban-api

sleep 2

if systemctl is-active --quiet douban-api; then
    echo ""
    echo -e "${GREEN}========== 部署成功 ==========${NC}"
    echo ""
    PUBLIC_IP=$(curl -s --max-time 3 ifconfig.me 2>/dev/null || curl -s --max-time 3 ip.sb 2>/dev/null || echo "你的公网IP")
    echo "  访问地址:  http://$PUBLIC_IP/"
    echo "  健康检查:  http://$PUBLIC_IP/health"
    echo ""
    echo "  查看日志:  journalctl -u douban-api -f"
    echo "  重启服务:  systemctl restart douban-api"
    echo "  Nginx日志: tail -f /var/log/nginx/error.log"
    echo ""
    echo -e "${YELLOW}  ⚠  重要: 请在阿里云控制台开放 80 端口${NC}"
    echo "  路径: ECS实例 -> 安全组 -> 配置规则 -> 入方向 -> 添加 TCP 80 端口"
    echo ""
else
    echo -e "${RED}服务启动失败，查看日志:${NC}"
    journalctl -u douban-api -n 30
fi
