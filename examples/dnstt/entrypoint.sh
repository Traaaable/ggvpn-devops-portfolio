#!/bin/sh
set -eu

DATA_DIR="${DNSTT_DATA_DIR:-/data/dnstt}"
DOMAIN="${DNSTT_DOMAIN:-dnstt.example.test}"
LISTEN="${DNSTT_LISTEN:-:5300}"
UPSTREAM="${DNSTT_UPSTREAM:-127.0.0.1:1080}"
MTU="${DNSTT_MTU:-1232}"
ROTATION_DAYS="${DNSTT_KEY_ROTATION_DAYS:-14}"

mkdir -p "$DATA_DIR"

generate_key() {
    dnstt-server -gen-key \
        -privkey-file "$DATA_DIR/server.key" \
        -pubkey-file "$DATA_DIR/server.pub"
    chmod 600 "$DATA_DIR/server.key"
    chmod 644 "$DATA_DIR/server.pub"
    date +%s > "$DATA_DIR/server.rotated_at"
}

rotate_key_if_due() {
    if [ ! -s "$DATA_DIR/server.key" ] || [ ! -s "$DATA_DIR/server.pub" ]; then
        generate_key
        return
    fi

    if [ "$ROTATION_DAYS" -le 0 ] 2>/dev/null; then
        return
    fi

    now="$(date +%s)"
    rotated_at="$(cat "$DATA_DIR/server.rotated_at" 2>/dev/null || stat -c %Y "$DATA_DIR/server.key" 2>/dev/null || echo "$now")"
    max_age=$((ROTATION_DAYS * 86400))
    age=$((now - rotated_at))
    if [ "$age" -lt "$max_age" ]; then
        return
    fi

    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    [ ! -s "$DATA_DIR/server.key" ] || cp "$DATA_DIR/server.key" "$DATA_DIR/server.key.$stamp.bak"
    [ ! -s "$DATA_DIR/server.pub" ] || cp "$DATA_DIR/server.pub" "$DATA_DIR/server.pub.$stamp.bak"
    generate_key
}

start_dnstt() {
    dnstt-server \
        -udp "$LISTEN" \
        -mtu "$MTU" \
        -privkey-file "$DATA_DIR/server.key" \
        "$DOMAIN" \
        "$UPSTREAM" &
    DNSTT_PID="$!"
}

stop_dnstt() {
    if [ -n "${DNSTT_PID:-}" ] && kill -0 "$DNSTT_PID" 2>/dev/null; then
        kill "$DNSTT_PID" 2>/dev/null || true
        wait "$DNSTT_PID" 2>/dev/null || true
    fi
}

shutdown() {
    stop_dnstt
    exit 0
}

trap shutdown INT TERM

rotate_key_if_due

danted -f /etc/danted.conf -D
LAST_ROTATED_AT="$(cat "$DATA_DIR/server.rotated_at" 2>/dev/null || true)"

while :; do
    start_dnstt
    while kill -0 "$DNSTT_PID" 2>/dev/null; do
        sleep 3600 &
        wait "$!" || true
        rotate_key_if_due
        current_rotated_at="$(cat "$DATA_DIR/server.rotated_at" 2>/dev/null || true)"
        if [ "${LAST_ROTATED_AT:-}" != "$current_rotated_at" ]; then
            LAST_ROTATED_AT="$current_rotated_at"
            stop_dnstt
            break
        fi
    done
    wait "$DNSTT_PID" 2>/dev/null || true
    sleep 1
done
