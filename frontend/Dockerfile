FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# nginx:alpine auto-envsubst's /etc/nginx/templates/*.template into conf.d
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
ENV API_UPSTREAM=http://api:8000
ENV PORT=80
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
