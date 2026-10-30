# Multi-stage build for React frontend
FROM node:22-alpine AS build

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy sources and compile production bundle
COPY . .
RUN npm run build

# Production serve stage using Nginx
FROM nginx:alpine

# Copy compiled SPA assets and custom reverse-proxy configuration
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

# Health check
HEALTHCHECK --interval=5s --timeout=3s --retries=5 --start-period=3s \
    CMD wget -q --spider http://localhost:3000/ || exit 1

CMD ["nginx", "-g", "daemon off;"]

