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

# 安装 Python 依赖
RUN pip install --no-cache-dir \
    fastmcp \
    requests \
    dashscope

# 复制 Docker 版服务文件
COPY docker/server.py /app/server.py

EXPOSE 8000

CMD ["python", "/app/server.py"]
