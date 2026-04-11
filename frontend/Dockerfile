# Dockerfile for Frontend (React + Vite)

ARG NODE_VERSION=22
ARG NGINX_VERSION=1.28-alpine

# =========================================================================
# STAGE 1: BUILD - Build the application
# =========================================================================
FROM node:${NODE_VERSION}-alpine as builder

WORKDIR /app

# Copy package files
COPY package*.json ./
RUN npm ci

# Copy source code
COPY . .

# Build production bundle
RUN npm run build

# =========================================================================
# STAGE 2: RUNTIME - Serve with nginx
# =========================================================================
FROM nginx:${NGINX_VERSION}

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf
COPY default.conf /etc/nginx/conf.d/default.conf

# Copy built app from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Use the built-in nginx user available in nginx:alpine.
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx

USER nginx

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:80/ || exit 1

# Expose port
EXPOSE 80

# Default command
CMD ["nginx", "-g", "daemon off;"]
