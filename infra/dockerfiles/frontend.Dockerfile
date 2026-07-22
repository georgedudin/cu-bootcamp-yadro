# Build context is the REPO ROOT — see infra/docker-compose.yml.
# /repo mirrors the on-disk layout so the SPA's ../contracts/generated import
# (the @contracts alias) resolves exactly as it does locally.
FROM node:22-alpine AS build
WORKDIR /repo/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY contracts/generated/ /repo/contracts/generated/
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/frontend/dist /usr/share/nginx/html
