# 抖音MCP服务器 Docker 部署指南

本目录包含用于部署抖音MCP服务器的Docker配置文件，支持HTTP传输模式。

## 文件说明

- `Dockerfile`: 定义了如何构建抖音MCP服务器的Docker镜像
- `docker-compose.yml`: 用于启动和管理服务的Docker Compose配置
- `.env.example`: 环境变量示例文件

## 快速开始

### 1. 准备环境变量

复制环境变量示例文件并填入您的API密钥：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置阿里云百炼 API 密钥：

```
# 阿里云百炼 API 密钥（必需）
API_KEY=your-dashscope-api-key-here

# 语音识别模型（可选，默认为 paraformer-v2）
MODEL=paraformer-v2
```

### 2. 构建并启动服务

使用Docker Compose构建并启动服务：

```bash
docker-compose up -d --build
```

### 3. 验证服务

服务启动后，可以通过以下方式验证：

1. 检查服务状态：
   ```bash
   docker-compose ps
   ```

2. 查看服务日志：
   ```bash
   docker-compose logs -f
   ```

3. 访问健康检查端点：
   ```bash
   curl http://localhost:8000/health
   ```

## 服务配置

服务默认配置：
- 端口：8000
- 传输协议：HTTP (Streamable HTTP)
- 监听地址：0.0.0.0（允许外部访问）

## 使用服务

服务启动后，您可以通过以下方式使用：

1. **直接HTTP请求**：
   向 `http://localhost:8000/mcp` 发送MCP协议请求

2. **Claude Desktop配置**：
   在Claude Desktop的配置文件中添加：
   ```json
   {
     "mcpServers": {
       "douyin-mcp-docker": {
         "url": "http://localhost:8000/mcp"
       }
     }
   }
   ```

## 常用命令

- 停止服务：
  ```bash
  docker-compose down
  ```

- 重新构建并启动：
  ```bash
  docker-compose up -d --build
  ```

- 查看实时日志：
  ```bash
  docker-compose logs -f
  ```

## 注意事项

1. 确保您的系统已安装Docker和Docker Compose
2. 必须设置 `API_KEY` 环境变量（阿里云百炼API密钥）才能使用文本提取功能
3. 获取视频下载链接不需要API密钥
4. 服务会自动处理临时文件的清理

## 故障排除

如果遇到问题，请检查：

1. 确保端口8000未被其他服务占用
2. 检查 `.env` 文件中 `API_KEY` 是否正确设置
3. 查看服务日志获取详细错误信息：
   ```bash
   docker-compose logs douyin-mcp-server
   ```

## GitHub Actions 自动构建

本项目配置了GitHub Actions工作流，可以自动构建和推送Docker镜像：

### 触发条件
- 推送到 `streamable-http` 分支
- 手动触发 (`workflow_dispatch`)

### 镜像标签
- `ghcr.io/<owner>/douyin-mcp-server:streamable-http`
- `ghcr.io/<owner>/douyin-mcp-server:sha-<shortsha>`

### 使用自动构建的镜像

1. **直接使用镜像**：
   ```bash
   docker run -d \
     --name douyin-mcp-server \
     -p 8000:8000 \
     -e API_KEY=your-api-key \
     ghcr.io/<owner>/douyin-mcp-server:streamable-http
   ```

2. **更新docker-compose.yml**：
   ```yaml
   services:
     douyin-mcp:
       image: ghcr.io/<owner>/douyin-mcp-server:streamable-http
       ports:
         - "8000:8000"
       environment:
         - API_KEY=${API_KEY}
       restart: unless-stopped
   ```
