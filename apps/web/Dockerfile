FROM node:22.22.0-bookworm-slim AS builder
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
RUN pnpm install --frozen-lockfile
COPY apps/web apps/web
COPY packages/api-client packages/api-client
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
RUN pnpm --filter @hibi/web build

FROM node:22.22.0-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
RUN useradd --create-home --uid 10001 hibi
COPY --from=builder --chown=hibi:hibi /app/apps/web/.next/standalone ./
COPY --from=builder --chown=hibi:hibi /app/apps/web/.next/static ./apps/web/.next/static
USER hibi
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
