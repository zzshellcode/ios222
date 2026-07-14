/*
 * real_collector — freestanding one-shot for Stage3 manual map
 * No libc / no dlsym / no stack protector imports.
 * Export: process -> _process
 */

typedef unsigned int uint32_t;
typedef unsigned char uint8_t;

#define STATE_READY 3
#define STATE_EXIT  5
#define STATE_FEED  6

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
    int i;
    int n = slen(s);
    if (n > 4095) n = 4095;
    for (i = 0; i < n; i++) p[i] = (uint8_t)s[i];
    p[n] = 0;
    D[1] = (uint32_t)n;
    D[0] = STATE_READY;
}

void process(void *buffer) {
    uint32_t *D;
    uint8_t *payload;
    uint32_t st;

    if (!buffer) return;
    D = (uint32_t *)buffer;
    payload = (uint8_t *)(D + 2);
    st = D[0];

    if (st == STATE_EXIT) return;

    if (st == STATE_FEED) {
        if (payload[0] == 'c' && payload[1] == 'm' && payload[2] == 'd' && payload[3] == ':') {
            const char *cmd = (const char *)(payload + 4);
            if (scmp(cmd, "ping") == 0) {
                buffer_set(D,
                    "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"ping\","
                    "\"note\":\"freestanding_alive\"}");
                return;
            }
            if (scmp(cmd, "list_dcim") == 0) {
                buffer_set(D,
                    "{\"ok\":false,\"source\":\"real_collector\",\"cmd\":\"list_dcim\","
                    "\"error\":\"need_resolved_posix_api\"}");
                return;
            }
            if (sncmp(cmd, "list_dir:", 9) == 0) {
                buffer_set(D,
                    "{\"ok\":false,\"source\":\"real_collector\",\"cmd\":\"list_dir\","
                    "\"error\":\"need_resolved_posix_api\"}");
                return;
            }
            if (sncmp(cmd, "read_file:", 10) == 0) {
                buffer_set(D,
                    "{\"ok\":false,\"source\":\"real_collector\",\"cmd\":\"read_file\","
                    "\"error\":\"need_resolved_posix_api\"}");
                return;
            }
            if (scmp(cmd, "device_info") == 0) {
                buffer_set(D,
                    "{\"ok\":true,\"source\":\"real_collector\",\"cmd\":\"device_info\","
                    "\"mode\":\"freestanding\"}");
                return;
            }
            if (scmp(cmd, "exit") == 0) {
                D[0] = STATE_EXIT;
                D[1] = 0;
                return;
            }
            buffer_set(D,
                "{\"ok\":false,\"source\":\"real_collector\",\"error\":\"unknown_command\"}");
            return;
        }
        buffer_set(D,
            "{\"ok\":false,\"source\":\"real_collector\",\"error\":\"expected_cmd_prefix\"}");
        return;
    }

    buffer_set(D,
        "{\"ok\":true,\"source\":\"real_collector\",\"event\":\"boot\","
        "\"msg\":\"dylib_started\",\"mode\":\"freestanding\"}");
}
