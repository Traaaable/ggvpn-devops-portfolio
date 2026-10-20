FROM nginx:1.30.6-alpine-slim@sha256:3028fc1419f99b95c1c69f844bbaf49dc1b881750c51b497fc721ac4f02a14e6
COPY charts/ggvpn-web/files/nginx.conf /etc/nginx/nginx.conf
COPY docker/web/index.html /usr/share/nginx/html/index.html
USER 101:101
EXPOSE 8080
STOPSIGNAL SIGQUIT
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO /dev/null http://127.0.0.1:8080/readyz || exit 1
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
