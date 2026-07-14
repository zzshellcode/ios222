# Coruna iOS Exploit Toolkit

> ⚠️ **免责声明**：此项目仅用于授权的安全研究和教育目的。未经授权使用可能违反法律，请确保在合法环境中使用。作者不对任何滥用行为负责。

🌐 [English Version](README.md) | 中文版本

---

## 项目概述

Coruna 是一个完整的 iOS 恶意攻击工具包，从真实攻击中捕获并完全解密还原。该工具包包含完整的 0-day 攻击链，可实现从 Web 端到 iOS 设备的远程代码执行、权限提升和数据窃取。

### 来源信息

| 属性 | 说明 |
|------|------|
| 来源 | 从 `sadjd.mijieqi.cn` 恶意网站捕获 |
| 威胁级别 | 完整的 iOS 0-day 攻击链（RCE + 权限提升 + 数据窃取） |
| C2 状态 | 已关闭（无实际危害） |
| 用途 | 安全研究、教育、漏洞分析 |

---

## 技术架构

攻击链分为三个主要阶段，由 `group.html` 入口页面协调：

```
group.html  ← 入口页面
    ↓
1️⃣ Stage 1（WebKit 漏洞利用）
   - jacurutu    → iOS 15.2-15.5
   - bluebird    → iOS 15.6-16.1.2
   - terrorbird  → iOS 16.2-16.5.1
   - cassowary   → iOS 16.6-17.2.1
   ↓ 获得 WASM R/W 原语
2️⃣ Stage 2（PAC 绕过）
   - breezy15 / seedbell / seedbell_pre
   ↓ 绕过指针认证
3️⃣ Stage 3（沙箱逃逸 + Payload）
   - VariantA / VariantB
   ↓ 加载恶意 dylib
4️⃣ 数据窃取
   - 钥匙串、WiFi 密码、iCloud 文件等
```

---

## 支持的 iOS 版本

| iOS 版本 | Stage 1 | Stage 2 | Stage 3 |
|---------|---------|---------|---------|
| 13.0-14.x | buffout | breezy | VariantA/B |
| 15.0-15.1.1 | buffout | breezy15 | VariantA/B |
| 15.2-15.5 | jacurutu | breezy15 | VariantB |
| 15.6-16.1.2 | bluebird | breezy15 | VariantB |
| 16.2-16.5.1 | terrorbird | seedbell | VariantB |
| 16.3-16.5.1 | terrorbird | seedbell | VariantB |
| 16.6-16.7.12 | cassowary | seedbell | VariantB |
| 17.0-17.2.1 | cassowary | seedbell_pre + seedbell_17 | VariantB |

### iOS 18+ 版本支持

对于 iOS 18.4-18.7 版本的完整支持，请访问我们的专业版本：

👉 [DarkSword-Pro](https://github.com/adoemwanmei/DarkSword-Pro)

---

## 目录结构

```
Coruna/
├── group.html                 # 主入口（攻击页面）
├── platform_module.js         # 平台检测 + 密钥派生
├── utility_module.js          # 加密工具、Int64、LZW 解压
├── Stage1_*.js                # WebKit 漏洞利用（4 个版本）
├── Stage2_*.js                # PAC 绕过（5 个版本）
├── Stage3_VariantB.js         # 沙箱逃逸 + Payload 构建器
├── downloaded/                # 混淆后的加密 payload（17 个）
├── extracted/                 # 提取的二进制文件
├── payloads/                  # 解密后的 Mach-O dylib
│   ├── bootstrap.dylib        # 启动加载器
│   ├── manifest.json          # Payload 清单
│   └── <hash>/               # 19 个不同 iOS 版本的 payload
│       ├── entry0_type0x08.dylib  # 主植入物（powerd）
│       ├── entry1_type0x09.dylib  # 内核漏洞利用
│       ├── entry2_type0x0f.dylib  # 持久化模块
│       └── ...
├── other/                     # 额外资源和备用版本
├── backend/                   # C2 后端管理系统
│   ├── main.py               # FastAPI 主应用
│   ├── api/                  # API 路由
│   └── ...
├── frontend/                  # 管理面板前端
├── SpringBoardTweak/          # iOS SpringBoard Tweak 示例（测试弹窗）
├── start.sh                   # Linux/Mac 启动脚本
├── start.bat                  # Windows 启动脚本
├── ANALYSIS.md               # 加密机制分析文档
├── DEPLOYMENT.md             # 部署指南
├── test_system.py            # 系统测试脚本
└── coruna_c2.db              # SQLite 数据库
```

---

## 加密机制

Payload 采用多层加密机制：

```
[原始 payload]
    ↓ ChaCha20（每文件独立密钥，nonce=0）
    ↓ LZMA/XZ 压缩
    ↓ F00DBEEF 容器格式
[Mach-O dylib]（arm64/arm64e）
```

**关键发现**：
- ChaCha20 密钥从 `group.html` 派生
- 每个 iOS 版本有独立密钥
- 支持 iOS 13-17（arm64 和 arm64e）

详细分析见 [ANALYSIS.md](ANALYSIS.md)。

---

## 窃取的数据类型

| 类别 | 示例 |
|------|------|
| 通讯 | SMS、通讯录、通话记录 |
| 凭证 | WiFi 密码、钥匙串、Keybag |
| 浏览器 | Safari 历史、书签、Cookie |
| 位置 | 位置历史、定位服务缓存 |
| 个人 | 笔记、日历、健康数据、照片 |
| 设备 | IMEI、序列号、配置描述文件 |
| 加密货币 | 钱包 App 检测（Ledger、Coinbase、Metamask 等） |

---

## 快速开始

### 方式一：纯静态 Web 服务器

```bash
cd Coruna
python -m http.server 8080
```

然后在 iOS Safari 中访问 `http://IP:8080/group.html`

### 方式二：完整 C2 管理系统

**环境要求**：
- Python 3.8+
- SQLite3
- 现代浏览器

**启动步骤**：

Windows:
```bash
start.bat
```

Linux/Mac:
```bash
chmod +x start.sh
./start.sh
```

**访问管理面板**：
- 地址：`http://localhost:8782`
- 默认用户名：`admin`
- 默认密码：`admin123`

> ⚠️ **重要**：首次使用后请修改默认密码！

---

## 界面截图

![仪表盘](demo/1.png)

![设备管理](demo/2.png)

![任务管理](demo/3.png)

---

## 部署说明

> 🌐 [English Deployment Guide](DEPLOYMENT.md)

详细部署步骤见 [DEPLOYMENT_CN.md](DEPLOYMENT_CN.md)，包含：
- Nginx/Apache 配置
- HTTPS 配置
- 防火墙设置
- 安全建议

---

## 技术分析

### Payload 类型说明

| 类型 | 描述 | 典型大小 |
|------|------|---------|
| 0x08 | 主植入物 dylib（目标 `powerd`，HTTP C2） | ~196-228 KB |
| 0x09 | 内核/沙箱逃逸 dylib（权限提升） | ~230-334 KB |
| 0x0f | 持久化 dylib（挂钩 `launchd`、`powerd`） | ~191-192 KB |
| 0x0a | 额外漏洞利用/持久化模块（新版 iOS） | ~50-68 KB |
| 0x05 | 数据 blob（内核偏移/gadgets） | ~24 KB |
| 0x07 | 小型配置/元数据 blob | 44 或 468 字节 |

### C2 地址修改

C2 地址存储在 Mach-O dylib 的二进制数据中，位于 `payloads/*/entry0_type0x08.dylib`。修改步骤：

1. 在 Mach-O dylib 中搜索字符串
2. 用十六进制编辑器修改
3. 重新签名（iOS 需要代码签名）

详细说明见 [1.Coruna 项目完整分析.md](1.Coruna%20项目完整分析.md)。

---

## 安全研究价值

| 方面 | 说明 |
|------|------|
| 完整性 | ✅ 完整攻击链（Web→RCE→提权→窃密） |
| 可用性 | ✅ C2 已关闭，无法实际使用 |
| 研究价值 | ✅ 极高（包含真实的 iOS 漏洞利用和内核漏洞） |
| 法律风险 | ⚠️ 仅供授权研究，禁止非法使用 |

---

## 文件说明

| 文件 | 描述 |
|------|------|
| `group.html` | 攻击入口页面，协调整个攻击链 |
| `platform_module.js` | 平台检测和密钥派生逻辑 |
| `utility_module.js` | 加密工具、Int64 运算、LZW 解压 |
| `Stage1_*.js` | WebKit 漏洞利用（不同 iOS 版本） |
| `Stage2_*.js` | PAC 指针认证绕过 |
| `Stage3_VariantB.js` | 沙箱逃逸和 Payload 构建器 |
| `bootstrap.dylib` | 启动加载器，验证并加载其他 dylib |
| `payloads/manifest.json` | Payload 清单文件 |
| `test_system.py` | 系统测试脚本 |
| `SpringBoardTweak/` | iOS SpringBoard Tweak 示例，用于测试越狱环境 |

---

## 注意事项

1. **仅供研究**：此工具仅用于安全研究和教育目的
2. **合法授权**：使用前必须获得明确的书面授权
3. **C2 已关闭**：原始 C2 服务器已关闭，工具无法实际使用
4. **数据安全**：请勿在生产环境或真实设备上测试
5. **法律风险**：未经授权使用可能违反计算机相关法律法规

---

## 相关文档

- [ANALYSIS.md](ANALYSIS.md) - Payload 解密机制详细分析
- [DEPLOYMENT.md](DEPLOYMENT.md) - 部署指南
- [1.Coruna 项目完整分析.md](1.Coruna%20项目完整分析.md) - 项目完整分析报告
- [backend/README.md](backend/README.md) - C2 后端管理系统文档

---

## 联系方式

获取完整项目及技术支持：

- **Telegram**：[https://t.me/Jeequan](https://t.me/Jeequan)
- **技术支持**：5000U（不免费提供）

---

**最后更新**：2026-06-26  
**版本**：1.0