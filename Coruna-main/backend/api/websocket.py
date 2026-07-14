"""WebSocket 实时通信模块"""

import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session

from database import get_db
import crud, schemas
from config import get_config

config = get_config()


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # 设备UUID -> WebSocket连接
        self.device_connections: Dict[str, WebSocket] = {}
        # 管理员连接
        self.admin_connections: Set[WebSocket] = set()
    
    async def connect_device(self, websocket: WebSocket, device_uuid: str):
        """设备连接"""
        await websocket.accept()
        self.device_connections[device_uuid] = websocket
        
        # 通知所有管理员有新设备连接
        await self.broadcast_to_admins({
            "type": "device_connected",
            "device_uuid": device_uuid,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat()
        })
    
    async def connect_admin(self, websocket: WebSocket):
        """管理员连接"""
        await websocket.accept()
        self.admin_connections.add(websocket)
        
        # 发送当前在线设备列表
        online_devices = list(self.device_connections.keys())
        await websocket.send_json({
            "type": "admin_connected",
            "online_devices": online_devices,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat()
        })
    
    def disconnect_device(self, device_uuid: str):
        """设备断开连接"""
        if device_uuid in self.device_connections:
            del self.device_connections[device_uuid]
    
    def disconnect_admin(self, websocket: WebSocket):
        """管理员断开连接"""
        if websocket in self.admin_connections:
            self.admin_connections.remove(websocket)
    
    async def send_to_device(self, device_uuid: str, message: dict):
        """发送消息到指定设备"""
        if device_uuid in self.device_connections:
            websocket = self.device_connections[device_uuid]
            try:
                await websocket.send_json(message)
                return True
            except Exception as e:
                print(f"Error sending to device {device_uuid}: {e}")
                self.disconnect_device(device_uuid)
                return False
        return False
    
    async def broadcast_to_admins(self, message: dict):
        """广播消息到所有管理员"""
        disconnected = set()
        for websocket in self.admin_connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"Error sending to admin: {e}")
                disconnected.add(websocket)
        
        # 清理断开的连接
        for websocket in disconnected:
            self.disconnect_admin(websocket)
    
    async def broadcast_to_devices(self, message: dict):
        """广播消息到所有设备"""
        disconnected_devices = set()
        for device_uuid, websocket in self.device_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"Error broadcasting to device {device_uuid}: {e}")
                disconnected_devices.add(device_uuid)
        
        # 清理断开的连接
        for device_uuid in disconnected_devices:
            self.disconnect_device(device_uuid)
    
    def get_online_devices(self) -> list:
        """获取在线设备列表"""
        return list(self.device_connections.keys())
    
    def is_device_online(self, device_uuid: str) -> bool:
        """检查设备是否在线"""
        return device_uuid in self.device_connections


# 全局连接管理器
manager = ConnectionManager()


class SSEManager:
    """Server-Sent Events 管理器 - 实时推送访问事件"""

    def __init__(self):
        self._queues: Dict[int, asyncio.Queue] = {}
        self._counter = 0

    def subscribe(self) -> int:
        self._counter += 1
        self._queues[self._counter] = asyncio.Queue(maxsize=100)
        return self._counter

    def unsubscribe(self, client_id: int):
        self._queues.pop(client_id, None)

    async def publish(self, event: str, data: dict):
        payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        disconnected = []
        for cid, q in self._queues.items():
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                disconnected.append(cid)
        for cid in disconnected:
            self.unsubscribe(cid)

    async def read(self, client_id: int):
        q = self._queues.get(client_id)
        if not q:
            return None
        return await q.get()


sse_manager = SSEManager()


async def websocket_endpoint(websocket: WebSocket, device_uuid: str = None, admin: bool = False):
    """
    WebSocket 端点
    支持设备和管理员连接
    """
    try:
        if admin:
            # 管理员连接
            await manager.connect_admin(websocket)
            
            while True:
                # 接收管理员消息
                data = await websocket.receive_json()
                message_type = data.get("type")
                
                if message_type == "ping":
                    # 心跳响应
                    await websocket.send_json({"type": "pong"})
                
                elif message_type == "send_to_device":
                    # 发送消息到指定设备
                    target_device = data.get("device_uuid")
                    message = data.get("message", {})
                    success = await manager.send_to_device(target_device, message)
                    await websocket.send_json({
                        "type": "send_result",
                        "success": success,
                        "device_uuid": target_device
                    })
                
                elif message_type == "broadcast_to_devices":
                    # 广播消息到所有设备
                    message = data.get("message", {})
                    await manager.broadcast_to_devices(message)
                    await websocket.send_json({
                        "type": "broadcast_result",
                        "success": True
                    })
        
        else:
            # 设备连接
            if not device_uuid:
                await websocket.close(code=4000, reason="Device UUID required")
                return
            
            await manager.connect_device(websocket, device_uuid)
            
            while True:
                # 接收设备消息
                data = await websocket.receive_json()
                message_type = data.get("type")
                
                if message_type == "ping":
                    # 心跳
                    await websocket.send_json({"type": "pong"})
                
                elif message_type == "log":
                    # 设备日志
                    log_data = schemas.DeviceLogCreate(
                        device_uuid=device_uuid,
                        stage=data.get("stage", "unknown"),
                        status=data.get("status", "info"),
                        message=data.get("message"),
                        elapsed_ms=data.get("elapsed_ms"),
                        metadata=data.get("metadata"),
                        log_level=data.get("log_level", "INFO")
                    )
                    
                    # 保存日志到数据库
                    db = next(get_db())
                    try:
                        crud.create_device_log(db, log_data)
                    finally:
                        db.close()
                    
                    # 广播日志到管理员
                    await manager.broadcast_to_admins({
                        "type": "device_log",
                        "device_uuid": device_uuid,
                        "log": log_data.dict()
                    })
                
                elif message_type == "task_result":
                    # 任务结果
                    task_id = data.get("task_id")
                    result_status = data.get("status", "completed")
                    result_data = data.get("result")
                    error_message = data.get("error_message")
                    
                    # 更新任务状态
                    db = next(get_db())
                    try:
                        crud.update_task_status(
                            db, task_id, result_status,
                            result=result_data,
                            error_message=error_message
                        )
                    finally:
                        db.close()
                    
                    # 广播任务结果到管理员
                    await manager.broadcast_to_admins({
                        "type": "task_result",
                        "device_uuid": device_uuid,
                        "task_id": task_id,
                        "status": result_status,
                        "result": result_data,
                        "error_message": error_message
                    })
                
                elif message_type == "heartbeat":
                    # 心跳更新
                    heartbeat_data = schemas.DeviceHeartbeat(
                        device_uuid=device_uuid,
                        status=data.get("status", "online"),
                        battery_level=data.get("battery_level"),
                        exploit_stage=data.get("exploit_stage"),
                        extra=data.get("extra")
                    )
                    
                    # 更新设备心跳
                    db = next(get_db())
                    try:
                        crud.update_device_heartbeat(db, heartbeat_data)
                    finally:
                        db.close()
                    
                    # 响应心跳
                    await websocket.send_json({"type": "heartbeat_ack"})
                
                elif message_type == "location":
                    # 位置更新
                    location_data = schemas.DeviceLocationUpdate(
                        device_uuid=device_uuid,
                        latitude=data.get("latitude"),
                        longitude=data.get("longitude"),
                        altitude=data.get("altitude"),
                        accuracy=data.get("accuracy")
                    )
                    
                    # 更新设备位置
                    db = next(get_db())
                    try:
                        crud.update_device_location(db, location_data)
                    finally:
                        db.close()
                    
                    # 广播位置更新到管理员
                    await manager.broadcast_to_admins({
                        "type": "device_location",
                        "device_uuid": device_uuid,
                        "location": location_data.dict()
                    })
    
    except WebSocketDisconnect:
        if admin:
            manager.disconnect_admin(websocket)
        else:
            manager.disconnect_device(device_uuid)
            
            # 通知管理员设备断开连接
            await manager.broadcast_to_admins({
                "type": "device_disconnected",
                "device_uuid": device_uuid,
                "timestamp": __import__("datetime").datetime.utcnow().isoformat()
            })
    
    except Exception as e:
        print(f"WebSocket error: {e}")
        if admin:
            manager.disconnect_admin(websocket)
        else:
            manager.disconnect_device(device_uuid)