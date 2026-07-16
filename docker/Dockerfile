FROM node:22-bookworm-slim

WORKDIR /opt/code-automations

COPY package.json package-lock.json ./

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN npm ci --omit=dev

ENV PATH="/opt/code-automations/node_modules/.bin:${PATH}"

ENTRYPOINT ["codex"]
