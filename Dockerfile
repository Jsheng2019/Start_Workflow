# Multi-stage build for Start_Workflow Node.js app
# Supports linux/amd64 and linux/arm64

# ---- Stage 1: Build -------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci && mkdir -p node_modules
COPY src/ ./src/
RUN mkdir -p dist && node src/index.js > dist/output.txt

# ---- Stage 2: Runtime ------------------------------------------------------
FROM node:20-alpine
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json ./
COPY src/ ./src/
USER app
CMD ["node", "src/index.js"]
