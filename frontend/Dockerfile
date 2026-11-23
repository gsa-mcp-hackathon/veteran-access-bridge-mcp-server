# IBM Code Engine: compile Lovable's TanStack Start app as a standalone Node server.
# Build output is server + static assets, NOT a static-only Vite site.
FROM oven/bun:1.3 AS build
WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .
ENV VAB_DEPLOY_TARGET=code-engine
ENV NITRO_PRESET=node-server
ARG VITE_ENABLE_LATENCY_PROBE=false
ENV VITE_ENABLE_LATENCY_PROBE=$VITE_ENABLE_LATENCY_PROBE
RUN bun run build && test -f .output/server/index.mjs

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=8080
COPY --from=build /app/.output ./.output

USER node
EXPOSE 8080
CMD ["node", ".output/server/index.mjs"]
