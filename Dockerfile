FROM node:22-bookworm-slim AS node

FROM python:3.12-slim-bookworm
ARG WITH_TEX=1
ARG CLAUDE_CODE_VERSION=2.1.310
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
RUN apt-get update && apt-get install -y --no-install-recommends \
      git openssh-client rsync zip poppler-utils pandoc ca-certificates curl sudo tini \
 && if [ "$WITH_TEX" = "1" ]; then apt-get install -y --no-install-recommends \
      latexmk texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-bibtex-extra biber; fi \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" && npm cache clean --force
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# /app stays root-owned and read-only for everyone else. The server runs as `bonrs`; each user's jobs run as
# uid 20000+<user id> through the root helper, which sudo lets `bonrs` call and nothing else.
RUN install -m 0755 -o root -g root tools/bonrs-sandbox /usr/local/sbin/bonrs-sandbox \
 && useradd -m -u 1000 bonrs && mkdir -p /data && chown bonrs:bonrs /data && chmod 0711 /data \
 && printf 'Defaults:bonrs env_reset, !requiretty\nbonrs ALL=(root) NOPASSWD: /usr/local/sbin/bonrs-sandbox\n' > /etc/sudoers.d/bonrs \
 && chmod 0440 /etc/sudoers.d/bonrs && visudo -cf /etc/sudoers.d/bonrs \
 && chown -R root:root /app && chmod -R a+rX,go-w /app
USER bonrs
ENV BONRS_DATA=/data BONRS_SANDBOX=1 BONRS_SELF_URL=http://127.0.0.1:8765 PYTHONUNBUFFERED=1
EXPOSE 8765
HEALTHCHECK CMD curl -fs http://localhost:8765/ >/dev/null || exit 1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "bonrs.web:app", "--host", "0.0.0.0", "--port", "8765", "--proxy-headers"]
