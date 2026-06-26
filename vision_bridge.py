# -*- coding: utf-8 -*-
"""
Vision Bridge — 通用视觉模型桥接 CLI

用法：
  python vision_bridge.py --image <路径> --prompt <文本> [--provider <名称>] [--max-tokens <N>]

示例：
  python vision_bridge.py --image design.png --prompt "描述这张UI设计稿" --provider "Claude中转站"

从 config.json 读取 Provider 配置，调用对应 API，输出模型返回的纯文本到 stdout。
"""

import argparse
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = SCRIPT_DIR / "config.json"
MAX_TOKENS_DEFAULT = 8192
TIMEOUT_SECONDS = 600


def load_config():
    if not CONFIG_PATH.exists():
        die(f"配置文件不存在: {CONFIG_PATH}\n请先启动配置面板（start.bat）添加 Provider。")
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"配置文件格式错误: {e}")
    return cfg


def find_provider(cfg, name):
    providers = cfg.get("providers", [])
    for p in providers:
        if p.get("name") == name:
            return p
    names = [p.get("name", "?") for p in providers]
    die(f"未找到 Provider '{name}'。可用: {', '.join(names) if names else '(无)'}")


def encode_image(image_path):
    path = Path(image_path)
    if not path.exists():
        die(f"图片不存在: {image_path}")

    ext = path.suffix.lower()
    media_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".gif": "image/gif"}
    media_type = media_map.get(ext, "image/png")

    data = path.read_bytes()
    data_b64 = base64.b64encode(data).decode("ascii")
    return media_type, data_b64


def build_anthropic_payload(provider, image_b64, media_type, prompt, max_tokens):
    return {
        "model": provider["model"],
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }


def build_openai_payload(provider, image_b64, media_type, prompt, max_tokens):
    data_url = f"data:{media_type};base64,{image_b64}"
    return {
        "model": provider["model"],
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }


def build_gemini_payload(provider, image_b64, media_type, prompt, max_tokens):
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"inlineData": {"mimeType": media_type, "data": image_b64}},
                    {"text": prompt},
                ],
            }
        ],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }


def build_payload(provider, image_b64, media_type, prompt, max_tokens):
    fmt = provider.get("api_format", "anthropic").lower()
    if fmt == "anthropic":
        return "anthropic", build_anthropic_payload(provider, image_b64, media_type, prompt, max_tokens)
    elif fmt == "openai":
        return "openai", build_openai_payload(provider, image_b64, media_type, prompt, max_tokens)
    elif fmt == "gemini":
        return "gemini", build_gemini_payload(provider, image_b64, media_type, prompt, max_tokens)
    else:
        die(f"不支持的 api_format: {fmt}（支持: anthropic, openai, gemini）")


def get_endpoint(provider):
    base = provider["base_url"].rstrip("/")
    fmt = provider.get("api_format", "anthropic").lower()
    if fmt == "anthropic":
        return f"{base}/v1/messages"
    elif fmt == "openai":
        return f"{base}/v1/chat/completions"
    elif fmt == "gemini":
        model = provider["model"]
        return f"{base}/v1/models/{model}:generateContent"


def get_request_headers(provider):
    api_key = provider["api_key"]
    fmt = provider.get("api_format", "anthropic").lower()
    headers = [
        "Content-Type: application/json",
        f"Authorization: Bearer {api_key}",
    ]
    if fmt == "anthropic":
        headers.append("anthropic-version: 2023-06-01")
    elif fmt == "gemini":
        # Gemini 用 x-goog-api-key 或 query param key=，这里统一用 header
        headers.append("x-goog-api-key: " + api_key)
    return headers


def call_api(provider, api_format, payload_dict):
    """用 curl subprocess 调用 API，绕过 Cloudflare bot 检测"""
    endpoint = get_endpoint(provider)
    headers = get_request_headers(provider)
    payload_json = json.dumps(payload_dict, ensure_ascii=False)

    # 写入临时文件避免命令行转义问题
    input_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    input_file.write(payload_json)
    input_file.close()

    output_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    output_file.close()

    input_path = Path(input_file.name)
    output_path = Path(output_file.name)

    try:
        cmd = [
            "curl", "-s", "-w", "\n%{http_code}",
            "--max-time", str(TIMEOUT_SECONDS),
            "--connect-timeout", "30",
            "-X", "POST",
            endpoint,
        ]
        for h in headers:
            cmd += ["-H", h]
        cmd += ["-d", f"@{input_path}", "-o", str(output_path)]

        print(f"正在调用 {provider['name']} ({provider['model']}) ...", file=sys.stderr)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS + 20)

        stdout = result.stdout.strip()
        stderr_text = result.stderr.strip()
        if stderr_text:
            print(f"curl: {stderr_text}", file=sys.stderr)

        lines = stdout.split("\n")
        http_code = lines[-1] if lines else ""

        if not output_path.exists():
            die(f"curl 未生成响应文件")

        body = output_path.read_text(encoding="utf-8")

        if http_code != "200":
            die(f"API HTTP {http_code}:\n{body[:1000]}")

        return body

    finally:
        input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


def parse_anthropic_response(raw):
    data = json.loads(raw)
    text_parts = []
    for item in data.get("content", []):
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))
    text = "\n".join(text_parts).strip()
    if not text:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    return text


def parse_openai_response(raw):
    data = json.loads(raw)
    choices = data.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "").strip()
    return json.dumps(data, ensure_ascii=False, indent=2)


def parse_gemini_response(raw):
    data = json.loads(raw)
    candidates = data.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [p.get("text", "") for p in parts if "text" in p]
        return "\n".join(text_parts).strip()
    return json.dumps(data, ensure_ascii=False, indent=2)


def parse_response(raw, api_format):
    if api_format == "anthropic":
        return parse_anthropic_response(raw)
    elif api_format == "openai":
        return parse_openai_response(raw)
    elif api_format == "gemini":
        return parse_gemini_response(raw)
    else:
        return raw


def die(msg):
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Vision Bridge — 通用视觉模型桥接")
    parser.add_argument("--image", default=None, help="图片文件路径")
    parser.add_argument("--prompt", default=None, help="发给视觉模型的 prompt")
    parser.add_argument("--provider", default=None, help="Provider 名称（不指定则用 config 里第一个）")
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS_DEFAULT, help=f"最大输出 tokens（默认 {MAX_TOKENS_DEFAULT}）")
    parser.add_argument("--list", action="store_true", help="列出所有 Provider")
    args = parser.parse_args()

    cfg = load_config()

    if args.list:
        for p in cfg.get("providers", []):
            print(f"  {p['name']} ({p.get('api_format','anthropic')}) -> {p['model']}")
        return

    # 非 list 模式必须提供 image 和 prompt
    if not args.image:
        die("缺少 --image 参数")
    if not args.prompt:
        die("缺少 --prompt 参数")

    # 选 Provider
    provider = None
    if args.provider:
        provider = find_provider(cfg, args.provider)
    else:
        providers = cfg.get("providers", [])
        if not providers:
            die("没有配置任何 Provider，请先启动配置面板（start.bat）添加。")
        provider = providers[0]
        print(f"使用默认 Provider: {provider['name']}", file=sys.stderr)

    api_format = provider.get("api_format", "anthropic").lower()

    # 编码图片
    media_type, image_b64 = encode_image(args.image)

    # 构建请求
    api_format, payload_dict = build_payload(provider, image_b64, media_type, args.prompt, args.max_tokens)

    # 调用 API
    raw = call_api(provider, api_format, payload_dict)

    # 解析响应
    text = parse_response(raw, api_format)

    # 输出到 stdout
    print(text)


if __name__ == "__main__":
    main()
