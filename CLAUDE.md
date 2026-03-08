# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

这个分支是精简后的 **streamable-http 版抖音 MCP 服务**。

当前代码重点在 Docker 运行形态：

- `docker/server.py`：基于 `FastMCP` 的服务实现
- `docker/Dockerfile`：容器镜像构建方式
- `docker/docker-compose.yml`：本地容器启动方式

核心能力：

- 从抖音分享文本中提取链接
- 解析分享页，提取 `video_id`、标题和无水印视频地址
- 调用语音识别 API，从视频 URL 提取文本
- 通过 `streamable-http` 暴露 MCP 工具、resource 和 prompt

## 常用命令

### 依赖与环境

- Python 要求：`>=3.10`
- 本地开发安装依赖：`uv sync`
- Docker 运行时镜像内会安装所需 Python 依赖

### 本地运行

- 启动 MCP 服务：`uv run python docker/server.py`
- 自定义端口：`PORT=8000 uv run python docker/server.py`
- 提供 API Key：`API_KEY="..." uv run python docker/server.py`

### Docker

- 构建镜像：`docker build -f docker/Dockerfile -t douyin-mcp-server .`
- 启动服务：`docker compose -f docker/docker-compose.yml up --build`

## 架构与代码组织

### 1. 当前分支的主实现

当前分支应优先以 `docker/server.py` 为准。它是一个独立、可直接运行的 MCP 服务实现，不依赖仓库中其他旧入口。

服务由 `FastMCP("Douyin MCP Server")` 创建，并在 `main()` 中以 `streamable-http` 启动。

### 2. 核心处理流程

`docker/server.py` 中的主流程是：

1. 从分享文本中用正则提取 URL
2. 请求短链接并跟随跳转，得到真实 `video_id`
3. 请求 `https://www.iesdouyin.com/share/video/{video_id}`
4. 从 HTML 中提取 `window._ROUTER_DATA`
5. 从 `loaderData` 中兼容读取视频页或图集页
6. 从 `video.play_addr.url_list[0]` 读取播放地址，并将 `playwm` 替换为 `play`
7. 调用 `dashscope.audio.asr.Transcription`，直接基于视频 URL 做转录
8. 返回工具结果或转录文本

### 3. MCP 暴露能力

当前服务暴露：

- `get_douyin_download_link`：返回无水印下载链接
- `extract_douyin_text`：提取视频文本
- `parse_douyin_video_info`：返回视频基础信息
- `douyin://video/{video_id}`：根据视频 ID 查询详情
- `douyin_text_extraction_guide`：内置使用说明 prompt

### 4. Docker 运行方式

`docker/Dockerfile`：

- 基于 `python:3.11-slim`
- 安装 `ffmpeg`
- 安装 `fastmcp`、`requests`、`dashscope`
- 只复制 `docker/server.py`
- 默认暴露 `8000`

`docker/docker-compose.yml`：

- 将 `API_KEY`、`HOST`、`PORT` 注入容器
- 默认映射 `8000:8000`
- 服务名为 `douyin-mcp`

## 重要文件

- `README.md`：项目说明与历史使用方式
- `pyproject.toml`：项目元数据与依赖定义
- `docker/server.py`：当前分支最重要的服务实现
- `docker/Dockerfile`：容器镜像构建方式
- `docker/docker-compose.yml`：容器启动配置

## 当前仓库约定与注意点

- 这个分支已经删除了与当前 streamable-http 方案无关的旧文件；分析和修改时优先依据 `docker/` 目录中的现状，不要默认旧的 Web/CLI/MCP 入口仍然存在。
- 当前仓库未发现项目级 `CLAUDE.md`、`.cursorrules`、`.cursor/rules/` 或 `.github/copilot-instructions.md`。
- 当前仓库没有可见的测试目录或测试命令；不要假设存在 pytest、nox、tox 或 CI 测试入口。
- 若要修改服务行为，优先检查 `docker/server.py`；若要修改部署方式，再看 `docker/Dockerfile` 和 `docker/docker-compose.yml`。
