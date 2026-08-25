# syntax=docker/dockerfile:1
# The web console. Dev server rather than a production build: this is a
# local tool you iterate on, and `next dev` picks up edits to web/ through
# the bind mount without a rebuild.
FROM node:22-slim

WORKDIR /app

# Lockfile layer first so a source edit doesn't reinstall node_modules, and
# a cache mount on npm's store so a dependency change re-links from disk
# rather than re-fetching the registry.
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY web/ ./

ENV NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]
