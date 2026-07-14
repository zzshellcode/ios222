"""Payload 管理 API 路由"""

import os
import json
import hashlib
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from config import get_config

config = get_config()
router = APIRouter(prefix="/api/payloads", tags=["payloads"])


def calculate_file_hash(file_path: str) -> str:
    """计算文件哈希值"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


@router.post("/upload")
async def upload_payload(
    name: str,
    ios_version: str,
    exploit_stage: str,
    description: Optional[str] = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    上传 Payload 文件
    用于管理不同 iOS 版本和 exploit 阶段的 payload
    """
    # 验证文件类型
    allowed_extensions = ['.js', '.bin', '.dylib', '.plist']
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file_ext}")
    
    # 创建目录结构
    stage_dir = config.PAYLOADS_DIR / exploit_stage
    version_dir = stage_dir / ios_version
    version_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存文件
    file_path = version_dir / file.filename
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # 计算哈希
    file_hash = calculate_file_hash(str(file_path))
    
    # 生成元数据
    metadata = {
        "name": name,
        "filename": file.filename,
        "ios_version": ios_version,
        "exploit_stage": exploit_stage,
        "description": description,
        "file_size": len(content),
        "file_hash": file_hash,
        "upload_time": __import__("datetime").datetime.utcnow().isoformat(),
        "file_path": str(file_path)
    }
    
    # 保存元数据
    metadata_file = file_path.with_suffix('.json')
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    return {
        "ok": True,
        "message": "Payload 上传成功",
        "metadata": metadata
    }


@router.get("/list")
def list_payloads(
    ios_version: Optional[str] = None,
    exploit_stage: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    获取 Payload 列表
    支持按 iOS 版本和 exploit 阶段筛选
    """
    payloads = []
    
    # 遍历 payload 目录
    for stage_dir in config.PAYLOADS_DIR.iterdir():
        if not stage_dir.is_dir():
            continue
        
        stage = stage_dir.name
        
        # 筛选 exploit 阶段
        if exploit_stage and stage != exploit_stage:
            continue
        
        for version_dir in stage_dir.iterdir():
            if not version_dir.is_dir():
                continue
            
            version = version_dir.name
            
            # 筛选 iOS 版本
            if ios_version and version != ios_version:
                continue
            
            # 查找所有 payload 文件
            for file_path in version_dir.glob('*'):
                # 跳过元数据文件
                if file_path.suffix == '.json':
                    continue
                
                # 读取元数据
                metadata_file = file_path.with_suffix('.json')
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                        payloads.append(metadata)
                    except Exception:
                        pass
                else:
                    # 如果没有元数据，创建基本信息
                    payloads.append({
                        "name": file_path.name,
                        "filename": file_path.name,
                        "ios_version": version,
                        "exploit_stage": stage,
                        "file_size": file_path.stat().st_size,
                        "file_path": str(file_path)
                    })
    
    return {
        "ok": True,
        "count": len(payloads),
        "payloads": payloads
    }


@router.get("/download/{payload_id}")
async def download_payload(payload_id: str):
    """
    下载 Payload 文件
    payload_id 格式: stage/version/filename
    """
    from fastapi.responses import FileResponse
    
    try:
        parts = payload_id.split('/')
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid payload ID format")
        
        stage, version, filename = parts
        file_path = config.PAYLOADS_DIR / stage / version / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Payload not found")
        
        return FileResponse(
            file_path,
            filename=filename,
            media_type="application/octet-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{payload_id}")
def delete_payload(payload_id: str):
    """
    删除 Payload 文件
    payload_id 格式: stage/version/filename
    """
    try:
        parts = payload_id.split('/')
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid payload ID format")
        
        stage, version, filename = parts
        file_path = config.PAYLOADS_DIR / stage / version / filename
        metadata_path = file_path.with_suffix('.json')
        
        # 删除文件
        if file_path.exists():
            file_path.unlink()
        
        # 删除元数据
        if metadata_path.exists():
            metadata_path.unlink()
        
        return {
            "ok": True,
            "message": "Payload 删除成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/versions")
def get_supported_versions():
    """获取支持的 iOS 版本列表"""
    return {
        "ok": True,
        "versions": list(config.SUPPORTED_IOS_VERSIONS.keys())
    }


@router.get("/stages")
def get_exploit_stages():
    """获取 exploit 阶段列表"""
    return {
        "ok": True,
        "stages": config.EXPLOIT_STAGES
    }


@router.post("/generate-link")
def generate_exploit_link(
    ios_version: str,
    exploit_chain: Optional[str] = None
):
    """
    生成 exploit 链接
    返回完整的 exploit URL
    """
    # 验证 iOS 版本
    if ios_version not in config.SUPPORTED_IOS_VERSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的 iOS 版本: {ios_version}")
    
    # 获取 exploit chain
    chain = exploit_chain or config.SUPPORTED_IOS_VERSIONS[ios_version]
    
    # 生成 exploit 链接
    exploit_url = f"{config.CORUNA_SERVER_URL}/group.html"
    
    # 同时生成直接下载链接模板
    download_base = f"{config.CORUNA_SERVER_URL}/downloaded"
    
    return {
        "ok": True,
        "exploit_url": exploit_url,
        "ios_version": ios_version,
        "exploit_chain": chain,
        "server_url": config.CORUNA_SERVER_URL
    }


@router.get("/status")
def get_payload_status():
    """
    获取 Payload 状态
    检查各个 iOS 版本和 exploit 阶段的 payload 是否完整
    """
    status = {}
    
    for ios_version, chain in config.SUPPORTED_IOS_VERSIONS.items():
        status[ios_version] = {
            "chain": chain,
            "stages": {},
            "complete": False
        }
        
        for stage in config.EXPLOIT_STAGES:
            stage_dir = config.PAYLOADS_DIR / stage / ios_version
            has_payload = stage_dir.exists() and any(stage_dir.glob('*'))
            
            status[ios_version]["stages"][stage] = {
                "has_payload": has_payload,
                "payload_count": len(list(stage_dir.glob('*'))) if has_payload else 0
            }
        
        # 检查是否完整
        status[ios_version]["complete"] = all(
            stage_info["has_payload"] 
            for stage_info in status[ios_version]["stages"].values()
        )
    
    return {
        "ok": True,
        "status": status
    }


@router.post("/validate/{payload_id}")
def validate_payload(payload_id: str):
    """
    验证 Payload 文件完整性
    检查文件哈希是否匹配
    """
    try:
        parts = payload_id.split('/')
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid payload ID format")
        
        stage, version, filename = parts
        file_path = config.PAYLOADS_DIR / stage / version / filename
        metadata_path = file_path.with_suffix('.json')
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Payload not found")
        
        # 读取元数据
        if not metadata_path.exists():
            return {
                "ok": True,
                "valid": False,
                "message": "No metadata found"
            }
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # 计算当前哈希
        current_hash = calculate_file_hash(str(file_path))
        stored_hash = metadata.get('file_hash')
        
        is_valid = current_hash == stored_hash
        
        return {
            "ok": True,
            "valid": is_valid,
            "current_hash": current_hash,
            "stored_hash": stored_hash,
            "message": "Payload is valid" if is_valid else "Payload hash mismatch"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))