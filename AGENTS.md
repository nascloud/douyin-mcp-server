# AGENTS.md - 抖音 MCP Server

本文件为在本仓库中工作的 AI 代理提供项目指南和代码风格约定。

## 项目概览

这是一个基于 Python 的抖音 MCP 服务器，使用 FastMCP 框架实现，通过 `streamable-http` 传输协议对外提供服务。

核心功能：
- 从抖音分享文本中提取链接
- 解析分享页，提取视频 ID、标题和无水印视频地址
- 调用阿里云百炼 ASR API 从视频 URL 提取文本
- 通过 `streamable-http` 暴露 MCP 工具、资源和提示

## 项目结构

```
.
├── docker/
│   ├── server.py          # 主服务实现（唯一入口）
│   ├── Dockerfile         # Docker 镜像构建文件
│   └── docker-compose.yml # Docker Compose 配置
├── pyproject.toml         # 项目元数据和依赖
├── README.md              # 项目说明
├── AGENTS.md              # 本文件
└── LICENSE                # Apache License 2.0
```

## 环境要求

- Python `>=3.10`
- 推荐使用 `uv` 进行依赖管理
- Docker 运行方式会自动安装所需依赖

## 常用命令

### 本地开发

```bash
# 安装依赖
uv sync

# 启动 MCP 服务（默认端口 8000）
uv run python docker/server.py

# 自定义端口启动
PORT=8000 uv run python docker/server.py

# 提供 API Key
API_KEY="your_api_key" uv run python docker/server.py
```

### Docker 运行

```bash
# 构建镜像
docker build -f docker/Dockerfile -t douyin-mcp-server .

# 运行容器
docker run --rm -p 8000:8000 -e API_KEY="your_api_key" douyin-mcp-server

# 使用 Docker Compose
docker compose -f docker/docker-compose.yml up --build
```

## 代码风格指南

### 导入规范

- 标准库导入在前，第三方库在后，本地模块最后
- 每组导入之间用空行分隔
- 使用绝对导入，避免相对导入

```python
# 标准库
import os
import re
import json
import time
import logging
from typing import Optional
from urllib import request
from http import HTTPStatus

# 第三方库
import requests
import dashscope
from fastmcp import FastMCP, Context
```

### 类型提示

- 所有函数参数和返回值都应有类型提示
- 使用 `Optional` 表示可选参数
- 复杂类型使用 `typing` 模块中的类型

```python
def parse_share_url(self, share_text: str) -> dict:
    ...

def __init__(self, api_key: str, model: Optional[str] = None):
    ...
```

### 命名约定

- 类名：`PascalCase`（如 `DouyinProcessor`）
- 函数/方法名：`snake_case`（如 `parse_share_url`）
- 常量：`UPPER_SNAKE_CASE`（如 `DEFAULT_MODEL`, `REQUEST_TIMEOUT`）
- 私有方法：单下划线前缀 `_method_name`（本项目未使用）

### 错误处理

- 使用具体的异常类型（`ValueError`, `RuntimeError`）
- 提供清晰的错误信息，包含上下文信息
- 使用 `raise ... from e` 保留原始异常链
- 在 MCP 工具中返回 JSON 格式的错误响应

```python
if not api_key:
    raise ValueError("未设置环境变量 API_KEY，请在配置中添加阿里云百炼API密钥")

except Exception as e:
    raise RuntimeError(
        f"提取文字时出错: video_url={video_url}, model={self.model}, task_id={task_id}, error={type(e).__name__}: {str(e)}"
    ) from e
```

### 日志记录

- 使用 `logging` 模块进行日志记录
- 日志级别通过环境变量 `LOG_LEVEL` 配置
- 记录关键操作和性能指标（耗时）

```python
logger = logging.getLogger(__name__)

logger.info("开始解析分享链接: %s", share_url)
logger.info("分享链接解析完成: video_id=%s, total_elapsed=%.2fs", video_id, total_elapsed)
logger.exception("extract_douyin_text 调用失败: elapsed=%.2fs", total_elapsed)
```

### 函数文档

- 使用 docstring 描述函数功能
- 对于 MCP 工具函数，docstring 会作为工具描述显示给用户

```python
def parse_share_url(self, share_text: str) -> dict:
    """从分享文本中提取无水印视频链接"""
```

### MCP 装饰器使用

- `@mcp.tool()`：定义 MCP 工具
- `@mcp.resource("uri_template")`：定义 MCP 资源
- `@mcp.prompt()`：定义 MCP 提示

```python
@mcp.tool()
def get_douyin_download_link(share_link: str) -> str:
    """获取抖音视频的无水印下载链接"""
    ...

@mcp.resource("douyin://video/{video_id}")
def get_video_info(video_id: str) -> str:
    ...

@mcp.prompt()
def douyin_text_extraction_guide() -> str:
    ...
```

### JSON 输出

- MCP 工具返回 JSON 字符串时，使用 `ensure_ascii=False` 和 `indent=2`
- 包含 `status` 字段标识成功或失败

```python
return json.dumps(
    {
        "status": "success",
        "video_id": video_info["video_id"],
        ...
    },
    ensure_ascii=False,
    indent=2,
)
```

## 架构要点

### 主要组件

1. **`DouyinProcessor` 类**：核心处理逻辑
   - `parse_share_url()`：解析分享链接
   - `extract_text_from_video_url()`：调用 ASR 提取文本

2. **MCP 工具函数**：
   - `process_douyin_video()`：统一处理抖音视频，返回视频信息、无水印下载链接和文本内容

3. **MCP 资源**：
   - `douyin://video/{video_id}`：根据 ID 查询视频详情

4. **MCP 提示**：
   - `douyin_text_extraction_guide()`：使用说明

### 依赖关系

- `fastmcp==3.1.0`：MCP 框架
- `requests`：HTTP 请求
- `dashscope`：阿里云百炼 ASR API

## 注意事项

- 本项目没有测试套件，修改时请手动验证
- 修改 `docker/server.py` 会影响整个服务行为
- 部署相关修改看 `docker/Dockerfile` 和 `docker/docker-compose.yml`
- 环境变量 `API_KEY` 是可选的，仅文本提取功能需要
- 服务默认监听 `0.0.0.0:8000`
