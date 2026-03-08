# 抖音 MCP Server

[![PyPI version](https://badge.fury.io/py/douyin-mcp-server.svg)](https://badge.fury.io/py/douyin-mcp-server)
[![Python version](https://img.shields.io/pypi/pyversions/douyin-mcp-server.svg)](https://pypi.org/project/douyin-mcp-server/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

当前分支是精简后的 **streamable-http 版抖音 MCP 服务**，主实现以 `docker/server.py` 为准。

它提供的核心能力包括：从抖音分享文本中提取链接、解析真实 `video_id`、获取无水印视频地址、调用阿里云百炼 ASR 提取文本，并通过 `FastMCP` 以 `streamable-http` 方式对外暴露 MCP 能力。

## 当前实现范围

当前仓库文档与运行方式均以以下入口为准：

- `docker/server.py`：当前分支唯一主服务入口
- `docker/Dockerfile`：容器镜像构建方式
- `docker/docker-compose.yml`：本地 Docker Compose 启动方式

本分支不再以旧版页面入口、CLI 脚本或历史入口作为主要使用方式。

## 核心能力

- 从抖音分享文本中提取可用链接
- 跟随短链接跳转并解析真实 `video_id`
- 请求分享页并从 `window._ROUTER_DATA` 提取视频或图集数据
- 生成无水印视频播放地址（将 `playwm` 替换为 `play`）
- 调用阿里云百炼 ASR 接口，直接基于视频 URL 进行转录
- 通过 `streamable-http` 暴露 MCP tools、resource 和 prompt

## 关键文件

- `README.md`：当前项目说明
- `docker/server.py`：服务实现与 MCP 能力定义
- `docker/Dockerfile`：Docker 镜像构建文件
- `docker/docker-compose.yml`：Docker Compose 配置
- `pyproject.toml`：项目元数据与 Python 依赖声明
- `LICENSE`：许可证文本

## 环境要求

- Python `>=3.10`（见 `pyproject.toml`）
- 推荐使用 `uv` 管理本地依赖
- Docker 运行方式会在镜像内安装所需依赖

## 本地运行

安装依赖：

```bash
uv sync
```

启动 MCP 服务：

```bash
uv run python docker/server.py
```

自定义端口：

```bash
PORT=8000 uv run python docker/server.py
```

提供阿里云百炼 API Key：

```bash
API_KEY="your_api_key" uv run python docker/server.py
```

默认监听配置来自 `docker/server.py`：

- `HOST=0.0.0.0`
- `PORT=8000`

## Docker 运行

构建镜像：

```bash
docker build -f docker/Dockerfile -t douyin-mcp-server .
```

启动容器：

```bash
docker run --rm -p 8000:8000 -e API_KEY="your_api_key" douyin-mcp-server
```

使用 Docker Compose：

```bash
docker compose -f docker/docker-compose.yml up --build
```

`docker/docker-compose.yml` 默认注入并暴露以下配置：

- `API_KEY`
- `HOST=0.0.0.0`
- `PORT=8000`
- 端口映射：`8000:8000`

## MCP 暴露能力

以下名称应与 `docker/server.py` 中定义保持一致。

### Tools

- `get_douyin_download_link`：获取抖音视频的无水印下载链接
- `extract_douyin_text`：从抖音分享链接提取视频文本内容，需要 `API_KEY`
- `parse_douyin_video_info`：解析抖音分享链接并返回基础信息

### Resource

- `douyin://video/{video_id}`：根据视频 ID 返回视频详细信息

### Prompt

- `douyin_text_extraction_guide`：内置使用说明

## 处理流程

当前实现的主要处理流程如下：

1. 从分享文本中通过正则提取 URL
2. 请求短链接并跟随跳转，解析真实 `video_id`
3. 请求 `https://www.iesdouyin.com/share/video/{video_id}`
4. 从 HTML 中提取 `window._ROUTER_DATA`
5. 从 `loaderData` 中兼容读取视频页或图集页
6. 从 `video.play_addr.url_list[0]` 读取播放地址，并将 `playwm` 替换为 `play`
7. 调用阿里云百炼 `dashscope.audio.asr.Transcription`，直接基于视频 URL 做转录
8. 通过 `FastMCP` 以 `streamable-http` 方式对外提供服务

## 使用说明

- 如果只需要解析视频标题、`video_id` 和无水印地址，可直接调用 `parse_douyin_video_info` 或 `get_douyin_download_link`
- 如果需要提取视频语音文本，必须先配置环境变量 `API_KEY`
- 服务启动后使用 `streamable-http` 传输方式对外提供 MCP 能力，监听地址由 `HOST` 和 `PORT` 控制

## 免责声明

- 本项目仅供学习和研究使用
- 使用者需遵守相关法律法规与平台条款
- 禁止用于侵犯知识产权或其他非法用途
- 作者不对使用本项目产生的损失承担责任

## 许可证

本项目采用 **Apache License 2.0**，以仓库根目录 `LICENSE` 文件为准。

## 说明

当前仓库的 `pyproject.toml` 仍声明为 MIT，但仓库根目录 `LICENSE` 为 Apache License 2.0。本文档已按 `LICENSE` 文件进行说明，建议后续同步修正项目元数据以消除不一致。