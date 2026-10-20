FROM golang:1.26.2-alpine@sha256:f85330846cde1e57ca9ec309382da3b8e6ae3ab943d2739500e08c86393a21b1 AS builder
ARG DNSTT_VERSION=v1.20260501.0
# A bounded compiler keeps this example usable on small build runners.
RUN CGO_ENABLED=0 GOMAXPROCS=1 GOMEMLIMIT=128MiB \
    go install -p=1 -trimpath www.bamsoftware.com/git/dnstt.git/dnstt-server@${DNSTT_VERSION}

FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates dante-server tini \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /go/bin/dnstt-server /usr/local/bin/dnstt-server
COPY danted.conf /etc/danted.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh
ENV DNSTT_DATA_DIR=/data/dnstt \
    DNSTT_DOMAIN=dnstt.example.test \
    DNSTT_LISTEN=:5300 \
    DNSTT_UPSTREAM=127.0.0.1:1080 \
    DNSTT_MTU=1232
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
