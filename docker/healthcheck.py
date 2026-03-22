#!/usr/bin/env python3
"""
MCP 服务器健康检查脚本

检查 /health 端点是否正常响应。
与 server.py 保持一致的端口和路径配置。
"""

import os
import sys
import logging
from http import HTTPStatus

import requests


logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# 超时时间（秒）
TIMEOUT = 5

# 读取与 server.py 一致的配置
HOST = os.getenv("HEALTHCHECK_HOST", "localhost")
PORT = int(os.getenv("PORT", "8000"))
HEALTH_PATH = "/health"
HEALTH_URL = f"http://{HOST}:{PORT}{HEALTH_PATH}"


def check_health() -> bool:
    """
    检查服务健康状态
    
    直接请求 /health 端点，响应 2xx 即为健康。
    
    Returns:
        bool: 健康返回 True，否则返回 False
    """
    try:
        response = requests.get(HEALTH_URL, timeout=TIMEOUT)
        
        # 2xx 状态码表示健康
        if HTTPStatus.OK <= response.status_code < HTTPStatus.MULTIPLE_CHOICES:
            return True
        
        logger.error("健康检查失败: status=%d", response.status_code)
        return False
        
    except requests.exceptions.ConnectionError:
        logger.error("无法连接到 %s", HEALTH_URL)
        return False
    except requests.exceptions.Timeout:
        logger.error("健康检查超时: %s", HEALTH_URL)
        return False
    except requests.exceptions.RequestException as e:
        logger.error("健康检查请求失败: %s", e)
        return False


if __name__ == "__main__":
    sys.exit(0 if check_health() else 1)
