#!/usr/bin/env python3
"""
抖音 MCP 服务器（FastMCP 官方最佳实践）

该服务器提供以下功能：
1. 解析抖音分享链接获取无水印视频链接
2. 从视频 URL 提取文本
3. 提供视频信息查询资源与使用提示
"""

import os
import re
import json
import time
import logging
from typing import Optional, Dict, Any, List
from enum import Enum
from fastmcp import FastMCP, Context
from fastmcp.server.lifespan import lifespan
from starlette.responses import JSONResponse
from urllib import request
from http import HTTPStatus

import httpx
import dashscope
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ============================================================
# 常量配置
# ============================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1"
}

DEFAULT_MODEL = "paraformer-v2"
REQUEST_TIMEOUT = 15.0
ASR_WAIT_WARN_SECONDS = 20

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
# Pydantic 模型定义
# ============================================================

class ResponseFormat(str, Enum):
    """输出格式枚举"""
    JSON = "json"
    MARKDOWN = "markdown"


class ProcessVideoInput(BaseModel):
    """处理抖音视频的输入参数"""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    share_link: str = Field(
        ...,
        description="抖音分享链接或包含链接的分享文本",
        min_length=1,
    )
    model: Optional[str] = Field(
        default=None,
        description="阿里云百炼 ASR 模型名称（默认: paraformer-v2）",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.JSON,
        description="输出格式: json（机器可读）或 markdown（人类可读）",
    )

    @field_validator("share_link")
    @classmethod
    def validate_share_link(cls, v: str) -> str:
        """验证分享链接格式"""
        if not v.strip():
            raise ValueError("分享链接不能为空")
        # 检查是否包含 http(s) 链接或短链格式
        if "http" not in v and "v.douyin" not in v:
            raise ValueError("分享文本中未找到有效的抖音链接")
        return v


class VideoInfo(BaseModel):
    """视频信息数据结构"""
    video_id: str = Field(description="抖音视频 ID")
    title: str = Field(description="视频标题/描述")
    download_url: str = Field(description="无水印下载链接")


class ProcessVideoOutput(BaseModel):
    """处理抖音视频的输出结果"""
    status: str = Field(description="处理状态: success, partial_success, error")
    video_id: Optional[str] = Field(default=None, description="视频 ID")
    title: Optional[str] = Field(default=None, description="视频标题")
    download_url: Optional[str] = Field(default=None, description="无水印下载链接")
    text_content: Optional[str] = Field(default=None, description="提取的文本内容")
    text_extracted: bool = Field(default=False, description="文本是否提取成功")
    errors: List[str] = Field(default_factory=list, description="错误信息列表")


class GetVideoInfoInput(BaseModel):
    """获取视频信息的输入参数"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    video_id: str = Field(..., description="抖音视频 ID", min_length=1)


# ============================================================
# 生命周期管理
# ============================================================

@lifespan
async def server_lifespan(server):
    """服务器生命周期管理 - 初始化和清理资源"""
    logger.info("初始化抖音 MCP 服务器...")
    
    # 初始化 dashscope API key
    api_key = os.getenv("API_KEY")
    if api_key:
        dashscope.api_key = api_key
        logger.info("API_KEY 已配置，启用文本提取功能")
    else:
        logger.warning("API_KEY 未设置，文本提取功能将不可用")
    
    yield  # 服务器运行中
    
    logger.info("抖音 MCP 服务器已关闭")


# 创建 MCP 服务器实例（带生命周期管理）
mcp = FastMCP(
    "douyin_mcp",
    lifespan=server_lifespan,
)


# ============================================================
# 健康检查端点
# ============================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """健康检查端点"""
    return JSONResponse({"status": "healthy", "service": "douyin_mcp"})


# ============================================================
# 共享工具函数
# ============================================================

def _extract_url_from_text(text: str) -> str:
    """从分享文本中提取第一个 URL"""
    urls = re.findall(
        r"https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
        text,
    )
    if not urls:
        # 尝试匹配抖音短链
        short_urls = re.findall(r"https?://[^\s]*v\.douyin\.com[^\s]*", text)
        if short_urls:
            return short_urls[0]
        raise ValueError("未找到有效的分享链接")
    return urls[0]


def _handle_error(error: Exception, context: Optional[str] = None) -> str:
    """统一的错误处理格式化"""
    error_type = type(error).__name__
    error_msg = str(error)
    
    if context:
        message = f"{context}: {error_type}: {error_msg}"
    else:
        message = f"{error_type}: {error_msg}"
    
    logger.exception("错误发生: %s", message)
    return message


def _format_markdown_response(video_info: VideoInfo, text_content: Optional[str] = None) -> str:
    """格式化 Markdown 响应"""
    lines = [
        f"# 🎬 抖音视频信息",
        "",
        f"**视频ID**: `{video_info.video_id}`",
        f"**标题**: {video_info.title}",
        "",
        f"## 📥 下载链接",
        "",
        f"[点击下载视频]({video_info.download_url})",
        "",
    ]
    
    if text_content:
        lines.extend([
            f"## 📝 视频文本内容",
            "",
            text_content,
            "",
        ])
    
    return "\n".join(lines)


# ============================================================
# 核心业务逻辑类
# ============================================================

class DouyinProcessor:
    """抖音视频处理器（异步版本）"""

    def __init__(self, api_key: str, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        if api_key:
            dashscope.api_key = api_key

    async def parse_share_url(self, share_text: str) -> VideoInfo:
        """从分享文本中提取无水印视频链接（异步）"""
        started_at = time.perf_counter()
        
        share_url = _extract_url_from_text(share_text)
        logger.info("开始解析分享链接: %s", share_url)

        async with httpx.AsyncClient(follow_redirects=True, timeout=REQUEST_TIMEOUT) as client:
            # 跟随短链跳转，获取真实 video_id
            redirect_started_at = time.perf_counter()
            response = await client.get(share_url, headers=HEADERS)
            redirect_elapsed = time.perf_counter() - redirect_started_at
            # httpx 返回的是 URL 对象，需要转换为字符串
            video_id = str(response.url).split("?")[0].strip("/").split("/")[-1]
            logger.info("短链跳转完成: video_id=%s, elapsed=%.2fs", video_id, redirect_elapsed)

            # 请求分享页
            share_url = f"https://www.iesdouyin.com/share/video/{video_id}"
            page_started_at = time.perf_counter()
            response = await client.get(share_url, headers=HEADERS)
            response.raise_for_status()
            page_elapsed = time.perf_counter() - page_started_at
            logger.info("视频页请求完成: status=%s, elapsed=%.2fs", response.status_code, page_elapsed)

        # 解析 HTML
        pattern = re.compile(
            pattern=r"window\._ROUTER_DATA\s*=\s*(.*?)</script>",
            flags=re.DOTALL,
        )
        find_res = pattern.search(response.text)

        if not find_res or not find_res.group(1):
            raise ValueError("从HTML中解析视频信息失败")

        json_data = json.loads(find_res.group(1).strip())
        video_key = "video_(id)/page"
        note_key = "note_(id)/page"

        if video_key in json_data["loaderData"]:
            original_video_info = json_data["loaderData"][video_key]["videoInfoRes"]
        elif note_key in json_data["loaderData"]:
            original_video_info = json_data["loaderData"][note_key]["videoInfoRes"]
        else:
            raise RuntimeError("无法从JSON中解析视频或图集信息")

        data = original_video_info["item_list"][0]
        video_url = data["video"]["play_addr"]["url_list"][0].replace("playwm", "play")
        desc = data.get("desc", "").strip() or f"douyin_{video_id}"
        desc = re.sub(r'[\\/:*?"<>|]', "_", desc)
        
        total_elapsed = time.perf_counter() - started_at
        logger.info("分享链接解析完成: video_id=%s, total_elapsed=%.2fs", video_id, total_elapsed)

        return VideoInfo(
            video_id=video_id,
            title=desc,
            download_url=video_url,
        )

    async def extract_text_from_video_url(self, video_url: str) -> str:
        """从视频URL中提取文字（使用阿里云百炼API）"""
        if not self.api_key:
            raise RuntimeError("未设置环境变量 API_KEY，无法提取文本")

        started_at = time.perf_counter()
        task_id = None
        try:
            logger.info("开始提交 ASR 任务: model=%s", self.model)
            submit_started_at = time.perf_counter()
            task_response = dashscope.audio.asr.Transcription.async_call(
                model=self.model,
                file_urls=[video_url],
                language_hints=["zh", "en"],
            )
            submit_elapsed = time.perf_counter() - submit_started_at

            task_id = task_response.output.task_id
            logger.info("ASR 任务提交完成: task_id=%s, elapsed=%.2fs", task_id, submit_elapsed)

            wait_started_at = time.perf_counter()
            transcription_response = dashscope.audio.asr.Transcription.wait(task=task_id)
            wait_elapsed = time.perf_counter() - wait_started_at
            if wait_elapsed >= ASR_WAIT_WARN_SECONDS:
                logger.warning("ASR 任务等待完成: task_id=%s, elapsed=%.2fs", task_id, wait_elapsed)
            else:
                logger.info("ASR 任务等待完成: task_id=%s, elapsed=%.2fs", task_id, wait_elapsed)

            if transcription_response.status_code == HTTPStatus.OK:
                for transcription in transcription_response.output["results"]:
                    url = transcription["transcription_url"]
                    logger.info("开始下载转录结果: task_id=%s", task_id)
                    result_fetch_started_at = time.perf_counter()
                    result = json.loads(
                        request.urlopen(url, timeout=int(REQUEST_TIMEOUT)).read().decode("utf8")
                    )
                    result_fetch_elapsed = time.perf_counter() - result_fetch_started_at
                    logger.info("转录结果下载完成: task_id=%s, elapsed=%.2fs", task_id, result_fetch_elapsed)

                    if "transcripts" in result and len(result["transcripts"]) > 0:
                        total_elapsed = time.perf_counter() - started_at
                        logger.info("文本提取完成: task_id=%s, total_elapsed=%.2fs", task_id, total_elapsed)
                        return result["transcripts"][0]["text"]
                raise RuntimeError(f"转录结果为空: task_id={task_id}")

            message = getattr(transcription_response.output, "message", "")
            raise RuntimeError(
                f"转录失败: status_code={transcription_response.status_code}, task_id={task_id}, message={message}"
            )
        except Exception as e:
            total_elapsed = time.perf_counter() - started_at
            logger.exception("extract_text_from_video_url 失败: task_id=%s, elapsed=%.2fs", task_id, total_elapsed)
            raise RuntimeError(
                f"提取文字时出错: video_url={video_url}, model={self.model}, task_id={task_id}, error={type(e).__name__}: {str(e)}"
            ) from e


# ============================================================
# MCP 工具定义
# ============================================================

@mcp.tool(
    name="douyin_process_video",
    annotations={
        "title": "处理抖音视频",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def process_douyin_video(
    params: ProcessVideoInput,
    ctx: Context,
) -> str:
    """处理抖音视频：解析视频信息、获取无水印链接、提取文本内容

    Args:
        params (ProcessVideoInput): 包含以下字段:
            - share_link (str): 抖音分享链接或包含链接的分享文本
            - model (Optional[str]): 阿里云百炼 ASR 模型名称
            - response_format (ResponseFormat): 输出格式 (json/markdown)

    Returns:
        str: JSON 或 Markdown 格式的处理结果

    Examples:
        - 使用方式: 传入分享链接，自动解析视频信息和下载链接
        - 配合 API_KEY 使用: 自动提取视频语音文本
        - 不使用 API_KEY: 仅返回视频信息和下载链接
    """
    started_at = time.perf_counter()
    
    try:
        # 获取 API_KEY
        api_key = os.getenv("API_KEY")
        processor = DouyinProcessor(api_key or "", params.model)

        # 解析视频信息
        await ctx.report_progress(0.2, "正在解析抖音分享链接...")
        await ctx.log_info(f"开始处理分享链接: {params.share_link[:50]}...")
        video_info = await processor.parse_share_url(params.share_link)
        await ctx.report_progress(0.5, "视频信息解析完成")

        # 构建结果
        result = ProcessVideoOutput(
            status="success",
            video_id=video_info.video_id,
            title=video_info.title,
            download_url=video_info.download_url,
            text_extracted=False,
        )

        # 尝试提取文本（需要API_KEY）
        if api_key:
            try:
                await ctx.report_progress(0.6, "正在从视频中提取文本...")
                await ctx.log_info("开始提取视频文本...")
                text_content = await processor.extract_text_from_video_url(video_info.download_url)
                result.text_content = text_content
                result.text_extracted = True
                await ctx.report_progress(1.0, "处理完成")
            except Exception as text_error:
                error_msg = _handle_error(text_error, "文本提取失败")
                result.errors.append(error_msg)
                await ctx.log_error(f"文本提取失败: {error_msg}")
        else:
            result.errors.append("未设置环境变量 API_KEY，无法提取文本")
            await ctx.log_warning("API_KEY 未设置，跳过文本提取")

        # 更新状态
        if result.errors:
            result.status = "partial_success"

        total_elapsed = time.perf_counter() - started_at
        await ctx.log_info(f"处理完成: video_id={video_info.video_id}, elapsed={total_elapsed:.2f}s")
        
        # 根据格式返回
        if params.response_format == ResponseFormat.MARKDOWN:
            return _format_markdown_response(
                video_info,
                result.text_content if result.text_extracted else None
            )
        else:
            return result.model_dump_json(ensure_ascii=False, indent=2)

    except Exception as e:
        total_elapsed = time.perf_counter() - started_at
        error_message = _handle_error(e, "处理抖音视频失败")
        await ctx.log_error(f"处理失败: {error_message}, elapsed={total_elapsed:.2f}s")
        
        error_output = ProcessVideoOutput(
            status="error",
            errors=[error_message],
        )
        return error_output.model_dump_json(ensure_ascii=False, indent=2)


# ============================================================
# MCP 资源定义
# ============================================================

@mcp.resource("douyin://video/{video_id}")
async def get_video_info(video_id: str, ctx: Context) -> str:
    """获取指定视频ID的详细信息

    Args:
        video_id (str): 抖音视频 ID
        ctx (Context): MCP 上下文

    Returns:
        str: JSON 格式的视频信息
    """
    await ctx.log_info(f"获取视频信息: video_id={video_id}")
    
    try:
        processor = DouyinProcessor("")
        video_info = await processor.parse_share_url(
            f"https://www.iesdouyin.com/share/video/{video_id}"
        )
        return video_info.model_dump_json(ensure_ascii=False, indent=2)
    except Exception as e:
        error_message = _handle_error(e, f"获取视频信息失败: {video_id}")
        await ctx.log_error(error_message)
        return json.dumps(
            {"status": "error", "error": error_message},
            ensure_ascii=False,
            indent=2,
        )


@mcp.resource("douyin://guide")
async def get_guide() -> str:
    """获取抖音 MCP 服务器使用指南"""
    return """
# 🎬 抖音 MCP 服务器使用指南

## 功能说明
这个 MCP 服务器可以从抖音分享链接中提取视频的文本内容，以及获取无水印下载链接。

## 环境变量配置
请确保设置了以下环境变量：
- `API_KEY`: 阿里云百炼 API 密钥（可选，用于文本提取）

## 可用工具

### douyin_process_video
处理抖音视频，返回视频信息、无水印下载链接，以及（如果配置了 API_KEY）提取的文本内容。

参数：
- `share_link`: 抖音分享链接或包含链接的分享文本
- `model`: ASR 模型名称（可选，默认 paraformer-v2）
- `response_format`: 输出格式 (json/markdown)

## 可用资源

### douyin://video/{video_id}
根据视频 ID 返回视频详细信息

### douyin://guide
返回本使用指南
"""


# ============================================================
# MCP 提示定义
# ============================================================

@mcp.prompt()
def douyin_text_extraction_guide() -> str:
    """抖音视频文本提取使用指南"""
    return """
# 抖音视频文本提取使用指南

## 功能说明
这个 MCP 服务器可以从抖音分享链接中提取视频的文本内容，以及获取无水印下载链接。

## 环境变量配置
请确保设置了以下环境变量：
- `API_KEY`: 阿里云百炼 API 密钥（可选）

## 工具说明
- `douyin_process_video`: 处理抖音视频，返回视频信息、无水印下载链接，以及（如果配置了 API_KEY）提取的文本内容
- `douyin://video/{video_id}`: 获取指定视频的详细信息
"""


# ============================================================
# 入口函数
# ============================================================

def main():
    """启动 MCP 服务器（streamable-http 传输）"""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    logger.info("启动抖音 MCP 服务: host=%s, port=%s", host, port)
    
    mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()
