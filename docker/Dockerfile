FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# 安装运行依赖（含 ffmpeg，便于后续扩展音视频处理）
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY docker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 复制 Docker 版服务文件和健康检查脚本
COPY docker/server.py /app/server.py
COPY docker/healthcheck.py /app/healthcheck.py

EXPOSE 8000

CMD ["python", "/app/server.py"]