"""反向代理模块 - 用于抓包分析第三方利用链"""

import httpx, json
from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from api.websocket import sse_manager
from database import get_db
from models import CollectedData

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

TARGET_BASE = "https://cursor.railway.cam/qqtime"
PROXY_PREFIX = "/api/proxy"

client = httpx.AsyncClient(follow_redirects=True, timeout=30)


@router.api_route("/{path:path}", methods=["GET", "POST", "HEAD"])
async def proxy_handler(path: str, request: Request, db: Session = Depends(get_db)):
    # 构建目标 URL
    target_url = f"{TARGET_BASE}/{path}" if path else TARGET_BASE.rstrip("/") + "/"

    # 收集请求信息
    ua = request.headers.get("user-agent", "")
    ip = request.client.host if request.client else "unknown"
    headers = dict(request.headers)
    query = dict(request.query_params)
    now = datetime.utcnow()

    # 打印日志
    print(f"[PROXY] {now.isoformat()} {ip} {request.method} {target_url} UA={ua[:80]}")

    # 保存请求日志到数据库
    try:
        log_entry = CollectedData(
            device_uuid=f"proxy_{ip}_{now.strftime('%Y%m%d%H%M%S')}",
            category="proxy_access",
            data_key=target_url,
            payload={
                "ip": ip,
                "method": request.method,
                "url": target_url,
                "path": path,
                "user_agent": ua[:500],
                "headers": {k: v for k, v in headers.items() if k.lower() not in ("cookie", "authorization")},
                "query_params": query,
            },
            source="proxy",
            collected_at=now,
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"[PROXY] DB log error: {e}")

    # 推送到 SSE
    try:
        await sse_manager.publish("proxy", {
            "ip": ip,
            "method": request.method,
            "url": target_url,
            "user_agent": ua[:200],
            "timestamp": now.isoformat()
        })
    except Exception:
        pass

    # 读取请求体
    body = None
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()

    # 构造转发请求头（排除 host 等）
    forward_headers = {
        k: v for k, v in headers.items()
        if k.lower() not in ("host", "content-length", "transfer-encoding")
    }
    if "user-agent" not in {k.lower() for k in forward_headers}:
        forward_headers["User-Agent"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)"

    try:
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=forward_headers,
            params=query,
            content=body,
        )

        # 如果是 HTML，替换相对路径为代理路径
        content = resp.content
        content_type = resp.headers.get("content-type", "")
        if "text/html" in content_type:
            text = content.decode("utf-8", errors="replace")
            # 替换相对引用为代理路径
            text = text.replace('src="', f'src="{PROXY_PREFIX}/')
            text = text.replace("src='", f"src='{PROXY_PREFIX}/")
            text = text.replace('href="', f'href="{PROXY_PREFIX}/')
            text = text.replace("href='", f"href='{PROXY_PREFIX}/")
            content = text.encode("utf-8")

        # 构造响应
        response_headers = {}
        for k, v in resp.headers.items():
            if k.lower() not in ("content-encoding", "transfer-encoding", "content-length", "connection", "alt-svc"):
                response_headers[k] = v

        return Response(
            content=content,
            status_code=resp.status_code,
            headers=response_headers,
        )

    except Exception as e:
        print(f"[PROXY] Error: {e}")
        return Response(
            content=f"<h1>Proxy Error</h1><p>{e}</p>",
            status_code=502,
            media_type="text/html",
        )
