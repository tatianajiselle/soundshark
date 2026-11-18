FROM node:22.23.5-alpine AS explorer
WORKDIR /explorer
COPY explorer/package.json explorer/package-lock.json ./
RUN npm ci
COPY explorer/ ./
RUN npm run build

FROM caddy:2.11.7-alpine AS server
RUN setcap -r /usr/bin/caddy \
    && mkdir -p /srv/explorer /srv/map \
    && chown -R 1000:1000 /data /config
COPY web/Caddyfile /etc/caddy/Caddyfile
USER 1000:1000

FROM server
COPY --from=explorer /explorer/dist /srv/explorer
