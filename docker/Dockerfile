FROM alpine:3.22.3

RUN apk add --no-cache ca-certificates iptables iptables-legacy iproute2 bash openssh curl jq \
    && ln -s /usr/sbin/iptables-legacy /usr/local/bin/iptables \
    && ln -s /usr/sbin/ip6tables-legacy /usr/local/bin/ip6tables \
    && ssh-keygen -f /etc/ssh/ssh_host_rsa_key -N '' -t rsa \
    && ssh-keygen -f /etc/ssh/ssh_host_ed25519_key -N '' -t ed25519

# Instala os binarios oficiais pre-compilados da Tailscale (pkgs.tailscale.com)
# em vez de compilar do zero - evita o bug de build encontrado na imagem
# anterior (`tailscale version` reportava "1.96.3-ERR-BuildInfo", com o
# resolver interno do MagicDNS (100.100.100.100) preso em SERVFAIL para
# qualquer nome, mesmo com o node autenticado e a subnet aprovada).
ARG TAILSCALE_VERSION=1.102.3
ARG TARGETARCH

RUN set -eux; \
    case "${TARGETARCH}" in \
        arm) TS_ARCH="arm" ;; \
        arm64) TS_ARCH="arm64" ;; \
        amd64) TS_ARCH="amd64" ;; \
        *) echo "arquitetura nao suportada: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://pkgs.tailscale.com/stable/tailscale_${TAILSCALE_VERSION}_${TS_ARCH}.tgz" -o /tmp/ts.tgz; \
    tar -xzf /tmp/ts.tgz -C /tmp; \
    mv "/tmp/tailscale_${TAILSCALE_VERSION}_${TS_ARCH}/tailscale" /usr/local/bin/tailscale; \
    mv "/tmp/tailscale_${TAILSCALE_VERSION}_${TS_ARCH}/tailscaled" /usr/local/bin/tailscaled; \
    chmod +x /usr/local/bin/tailscale /usr/local/bin/tailscaled; \
    rm -rf /tmp/ts.tgz "/tmp/tailscale_${TAILSCALE_VERSION}_${TS_ARCH}"; \
    apk add --no-cache --virtual .strip-deps binutils; \
    strip -s /usr/local/bin/tailscale /usr/local/bin/tailscaled; \
    apk del .strip-deps

COPY sshd_config /etc/ssh/sshd_config
COPY tailscale.sh /usr/local/bin/tailscale.sh
RUN chmod +x /usr/local/bin/tailscale.sh

EXPOSE 22/tcp
WORKDIR /
CMD ["/usr/local/bin/tailscale.sh"]
