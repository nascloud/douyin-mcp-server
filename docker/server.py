#!/usr/bin/env python3
"""
Docker 版抖音 MCP 服务器（官方 FastMCP + Streamable HTTP）

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
import requests
from typing import Optional
from urllib import request
from http import HTTPStatus

import dashscope
import uvicorn
from fastmcp import FastMCP, Context
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse


# 创建 MCP 服务器实例（官方 FastMCP）
mcp = FastMCP("Douyin MCP Server")

# 请求头，模拟移动端访问
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1"
}

# 默认 API 配置
DEFAULT_MODEL = "paraformer-v2"
REQUEST_TIMEOUT = 15
ASR_WAIT_WARN_SECONDS = 20

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class DouyinProcessor:
    """抖音视频处理器"""

    def __init__(self, api_key: str, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        if api_key:
            dashscope.api_key = api_key

    def parse_share_url(self, share_text: str) -> dict:
        """从分享文本中提取无水印视频链接"""
        started_at = time.perf_counter()
        urls = re.findall(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            share_text,
        )
        if not urls:
            raise ValueError("未找到有效的分享链接")

        share_url = urls[0]
        logger.info("开始解析分享链接: %s", share_url)

        redirect_started_at = time.perf_counter()
        share_response = requests.get(share_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        redirect_elapsed = time.perf_counter() - redirect_started_at
        video_id = share_response.url.split("?")[0].strip("/").split("/")[-1]
        logger.info("短链跳转完成: video_id=%s, elapsed=%.2fs", video_id, redirect_elapsed)

        share_url = f"https://www.iesdouyin.com/share/video/{video_id}"
        page_started_at = time.perf_counter()
        response = requests.get(share_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        page_elapsed = time.perf_counter() - page_started_at
        logger.info("视频页请求完成: status=%s, elapsed=%.2fs", response.status_code, page_elapsed)

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

        return {
            "url": video_url,
            "title": desc,
            "video_id": video_id,
        }

    def extract_text_from_video_url(self, video_url: str) -> str:
        """从视频URL中提取文字（使用阿里云百炼API）"""
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
                        request.urlopen(url, timeout=REQUEST_TIMEOUT).read().decode("utf8")
                    )
                    result_fetch_elapsed = time.perf_counter() - result_fetch_started_at
                    logger.info("转录结果下载完成: task_id=%s, elapsed=%.2fs", task_id, result_fetch_elapsed)

                    if "transcripts" in result and len(result["transcripts"]) > 0:
                        total_elapsed = time.perf_counter() - started_at
                        logger.info("文本提取完成: task_id=%s, total_elapsed=%.2fs", task_id, total_elapsed)
                        return result["transcripts"][0]["text"]
                    return "未识别到文本内容"
                raise RuntimeError(f"转录结果为空: task_id={task_id}")

            message = getattr(transcription_response.output, "message", "")
            raise RuntimeError(
                f"转录失败: status_code={transcription_response.status_code}, task_id={task_id}, message={message}"
            )
        except Exception as e:
            logger.exception("extract_text_from_video_url 失败: task_id=%s", task_id)
            raise RuntimeError(
                f"提取文字时出错: video_url={video_url}, model={self.model}, task_id={task_id}, error={type(e).__name__}: {str(e)}"
            ) from e



@mcp.tool()
async def process_douyin_video(
    share_link: str,
    model: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """处理抖音视频：解析视频信息、获取无水印链接、提取文本内容"""
    started_at = time.perf_counter()
    try:
        # 获取 API_KEY 环境变量
        api_key = os.getenv("API_KEY")
        processor = DouyinProcessor(api_key or "", model)

        # 解析视频信息
        if ctx:
            ctx.info("正在解析抖音分享链接...")
        video_info = processor.parse_share_url(share_link)

        result = {
            "status": "success",
            "video_id": video_info["video_id"],
            "title": video_info["title"],
            "download_url": video_info["url"],
            "text_content": None,
            "text_extracted": False,
            "errors": [],
        }

        # 尝试提取文本（需要API_KEY）
        if api_key:
            try:
                if ctx:
                    ctx.info("正在从视频中提取文本...")
                text_content = processor.extract_text_from_video_url(video_info["url"])
                result["text_content"] = text_content
                result["text_extracted"] = True
            except Exception as text_error:
                result["errors"].append(f"文本提取失败: {type(text_error).__name__}: {str(text_error)}")
        else:
            result["errors"].append("未设置环境变量 API_KEY，无法提取文本")
            logger.warning("未设置环境变量 API_KEY，跳过文本提取")

        total_elapsed = time.perf_counter() - started_at
        logger.info(
            "process_douyin_video 调用完成: video_id=%s, total_elapsed=%.2fs",
            video_info["video_id"],
            total_elapsed,
        )

        if ctx:
            ctx.info("处理完成!")

        # 如果有错误，更新状态为 partial_success
        if result["errors"]:
            result["status"] = "partial_success"
        
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        total_elapsed = time.perf_counter() - started_at
        error_message = f"处理抖音视频失败: {type(e).__name__}: {str(e)}"
        logger.exception("process_douyin_video 调用失败: elapsed=%.2fs", total_elapsed)
        if ctx:
            ctx.error(error_message)
        return json.dumps(
            {
                "status": "error",
                "errors": [error_message],
            },
            ensure_ascii=False,
            indent=2,
        )


@mcp.resource("douyin://video/{video_id}")
def get_video_info(video_id: str) -> str:
    """获取指定视频ID的详细信息"""
    share_url = f"https://www.iesdouyin.com/share/video/{video_id}"
    try:
        processor = DouyinProcessor("")
        video_info = processor.parse_share_url(share_url)
        return json.dumps(video_info, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取视频信息失败: {type(e).__name__}: {str(e)}"


@mcp.prompt()
def douyin_text_extraction_guide() -> str:
    """抖音视频文本提取使用指南"""
    return """
# 抖音视频文本提取使用指南

## 功能说明
这个MCP服务器可以从抖音分享链接中提取视频的文本内容，以及获取无水印下载链接。

## 环境变量配置
请确保设置了以下环境变量：
- `API_KEY`: 阿里云百炼API密钥

## 工具说明
- `process_douyin_video`: 处理抖音视频，返回视频信息、无水印下载链接，以及（如果配置了API_KEY）提取的文本内容
- `douyin://video/{video_id}`: 获取指定视频的详细信息
"""


async def health_check(request):
    """健康检查端点"""
    return JSONResponse({"status": "healthy", "service": "douyin-mcp-server"})


def main():
    """启动 MCP 服务器（streamable-http 传输 + 健康检查）"""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    logger.info("启动 MCP 服务: host=%s, port=%s, request_timeout=%ss", host, port, REQUEST_TIMEOUT)
    
    # 获取 FastMCP 的 ASGI 应用
    mcp_app = mcp.streamable_http_app()
    
    # 创建 Starlette 应用，包含 MCP 路由和健康检查端点
    starlette_app = Starlette(
        routes=[
            Route("/health", health_check),
            Mount("/mcp", app=mcp_app),
        ]
    )
    
    # 使用 uvicorn 运行
    uvicorn.run(starlette_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
