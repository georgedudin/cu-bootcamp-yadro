# Build context is the REPO ROOT — see infra/docker-compose.yml.
# FRIEND B: when the React SPA lands, add a node build stage here and COPY
# its dist/ into /usr/share/nginx/html instead of frontend/public.
FROM nginx:1.27-alpine
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/public /usr/share/nginx/html
