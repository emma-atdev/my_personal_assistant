FROM python:3.13-slim

WORKDIR /app

# 시스템 패키지 (psycopg2 빌드에 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
RUN pip install uv

# 의존성 파일 복사 및 설치
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# 소스 복사
COPY . .

# /app을 Python 경로에 추가 (storage, tools, agent 등 로컬 패키지 인식)
ENV PYTHONPATH=/app

EXPOSE 8000

CMD [".venv/bin/uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
