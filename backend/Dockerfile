FROM node:24-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/pyproject.toml backend/requirements.lock /app/backend/
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/owed /app/backend/owed
COPY --from=frontend /build/backend/owed/static /app/backend/owed/static
RUN pip install --no-cache-dir --no-deps .
COPY backend/models /app/backend/models
COPY docs /app/docs
RUN useradd --create-home owed && chown -R owed:owed /app
USER owed
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "owed.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--timeout-graceful-shutdown", "5"]
