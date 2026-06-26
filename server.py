# -*- coding: utf-8 -*-
"""
Vision Bridge 配置面板后端

启动：
  python server.py             # 默认端口 8081
  python server.py --port 9090 # 自定义端口

功能：
  GET  /            → 返回 config-panel.html
  GET  /api/config  → 返回 config.json
  POST /api/config  → 保存 config.json
  POST /api/test    → 测试 Provider 连通性
"""

import json
import subprocess
import sys
import tempfile
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = SCRIPT_DIR / "config.json"
HTML_PATH = SCRIPT_DIR / "config-panel.html"
DEFAULT_PORT = 8081


class VisionBridgeHandler(SimpleHTTPRequestHandler):
    """自定义 Handler：路由 + API"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SCRIPT_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_html()
        elif path == "/api/config":
            self._serve_config()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"

        if path == "/api/config":
            self._save_config(body)
        elif path == "/api/test":
            self._test_provider(body)
        else:
            self._json_response(404, {"error": "not found"})

    def _serve_html(self):
        if not HTML_PATH.exists():
            self._json_response(404, {"error": "config-panel.html 不存在"})
            return
        html = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _serve_config(self):
        if CONFIG_PATH.exists():
            data = CONFIG_PATH.read_text(encoding="utf-8")
        else:
            data = json.dumps({"providers": []}, ensure_ascii=False)
        self._json_response(200, json.loads(data))

    def _save_config(self, body):
        try:
            data = json.loads(body)
            CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._json_response(200, {"ok": True})
        except json.JSONDecodeError as e:
            self._json_response(400, {"error": f"JSON 格式错误: {e}"})

    def _test_provider(self, body):
        """测试指定 Provider 能否连通（发一个简单的纯文本请求）"""
        try:
            provider = json.loads(body)
        except json.JSONDecodeError as e:
            self._json_response(400, {"error": f"JSON 格式错误: {e}"})
            return

        base = provider.get("base_url", "").rstrip("/")
        api_key = provider.get("api_key", "")
        api_format = provider.get("api_format", "anthropic").lower()
        model = provider.get("model", "")

        if not base or not api_key or not model:
            self._json_response(400, {"error": "缺少必填字段: base_url, api_key, model"})
            return

        # 构建测试请求
        if api_format == "anthropic":
            endpoint = f"{base}/v1/messages"
            payload = {
                "model": model,
                "max_tokens": 20,
                "messages": [{"role": "user", "content": "回复一个字：通"}],
            }
            headers = ["Content-Type: application/json",
                       f"x-api-key: {api_key}",
                       "anthropic-version: 2023-06-01"]
        elif api_format == "openai":
            endpoint = f"{base}/v1/chat/completions"
            payload = {
                "model": model,
                "max_tokens": 20,
                "messages": [{"role": "user", "content": "回复一个字：通"}],
            }
            headers = ["Content-Type: application/json",
                       f"Authorization: Bearer {api_key}"]
        elif api_format == "gemini":
            endpoint = f"{base}/v1/models/{model}:generateContent"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": "回复一个字：通"}]}],
                "generationConfig": {"maxOutputTokens": 20},
            }
            headers = ["Content-Type: application/json",
                       f"x-goog-api-key: {api_key}"]
        else:
            self._json_response(400, {"error": f"不支持的 api_format: {api_format}"})
            return

        # curl 调用
        payload_json = json.dumps(payload, ensure_ascii=False)
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
                "--max-time", "30", "--connect-timeout", "10",
                "-X", "POST", endpoint,
            ]
            for h in headers:
                cmd += ["-H", h]
            cmd += ["-d", f"@{input_path}", "-o", str(output_path)]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
            stdout = result.stdout.strip()
            lines = stdout.split("\n")
            http_code = lines[-1] if lines else ""

            if http_code == "200":
                self._json_response(200, {"ok": True, "message": "连接成功 ✓"})
            else:
                body = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
                self._json_response(200, {"ok": False, "message": f"HTTP {http_code}: {body[:200]}"})

        except subprocess.TimeoutExpired:
            self._json_response(200, {"ok": False, "message": "连接超时"})
        except Exception as e:
            self._json_response(200, {"ok": False, "message": str(e)})
        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)

    def _json_response(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        # 精简日志
        print(f"[{self.log_date_time_string()}] {args[0]}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Vision Bridge 配置面板服务器")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"端口（默认 {DEFAULT_PORT}）")
    args = ap.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), VisionBridgeHandler)
    print(f"Vision Bridge 配置面板已启动: http://localhost:{args.port}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
