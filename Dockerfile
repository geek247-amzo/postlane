FROM node:24-bookworm-slim AS web
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.13-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="Postlane" org.opencontainers.image.vendor="CloudMonkey" org.opencontainers.image.description="Private email workspace. Created by CloudMonkey."
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home postlane
COPY --chown=postlane:postlane backend ./backend
COPY --from=web --chown=postlane:postlane /build/dist ./dist
RUN mkdir /app/data && chown postlane:postlane /app/data
USER postlane
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
