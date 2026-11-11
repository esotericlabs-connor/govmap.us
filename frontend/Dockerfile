# All stages pin the same base digest so a rebuild is reproducible and a
# re-pushed tag can't change what ships; Dependabot proposes digest bumps.
# --- deps: install node_modules ---
FROM node:24-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9 AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- builder: compile the Next.js standalone bundle ---
FROM node:24-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9 AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* values are inlined into the client bundle at BUILD time, so
# they must be the real production URLs here, not injected at runtime.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_APP_URL
ARG NEXT_PUBLIC_MARKETING_URL
ARG NEXT_PUBLIC_TURNSTILE_SITE_KEY
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL \
    NEXT_PUBLIC_MARKETING_URL=$NEXT_PUBLIC_MARKETING_URL \
    NEXT_PUBLIC_TURNSTILE_SITE_KEY=$NEXT_PUBLIC_TURNSTILE_SITE_KEY

RUN npm run build

# --- runner: minimal runtime image ---
FROM node:24-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9 AS runner
WORKDIR /app
ARG SOURCE_COMMIT=unknown
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    APP_COMMIT_SHA=$SOURCE_COMMIT

RUN node -e "if (!/^(unknown|[a-f0-9]{40})$/.test(process.env.APP_COMMIT_SHA)) { throw new Error('SOURCE_COMMIT must be a full Git SHA or unknown'); }"

# The standalone server needs only `node`; drop the bundled package managers
# so they aren't shipped (or patched) in production.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack /opt/yarn-v* \
    /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/yarnpkg

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER node
EXPOSE 3000
CMD ["node", "server.js"]
