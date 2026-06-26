# 🔮 Vision Bridge — 视觉模型桥接工具

让无多模态能力的 AI Agent（如 DeepSeek）通过中转站调用 **Claude / GPT / Gemini** 等视觉模型来识别图片。

> 主 Agent 用 DeepSeek 写代码，开子 Agent 调用视觉模型看图——各取所长。

---

## 背景

主 Agent 使用 DeepSeek（无多模态），需要看图能力时受阻。解决方案：

1. 通过中转站 API 调用 Claude / GPT / Gemini 视觉模型
2. 视觉模型返回图片的文字描述
3. 主 Agent 基于描述继续处理

本项目将此流程抽象为**可配置、可复用**的工具，支持可视化配置多 Provider。

---

## 文件结构

```
vision-bridge/
├── SKILL.md                # Claude Code Skill 定义
├── config.json             # Provider 配置（⚠️ 含 API Key，已 .gitignore）
├── config.example.json     # Provider 配置示例（不含真实 Key）
├── config-panel.html       # 可视化配置面板
├── server.py               # 配置面板后端服务器
├── vision_bridge.py        # 核心 CLI 脚本
├── start.bat               # 双击启动配置面板
└── README.md               # 本文件
```

---

## 快速开始

### 1. 配置 Provider

**方式一：可视化配置面板（推荐）**

```bash
# 双击 start.bat，或执行：
python server.py
```

浏览器打开 http://localhost:8081

在面板中添加你的中转站 Provider：

| 字段 | 说明 | 示例 |
|------|------|------|
| 名称 | 自定义标识 | `Claude中转站` |
| Base URL | 中转站地址 | `https://mzlone.top` |
| API Key | 中转站密钥 | `sk-xxx` |
| Model | 模型名称 | `claude-opus-4-6` |
| API 格式 | Anthropic / OpenAI / Gemini | `anthropic` |

**方式二：直接编辑 config.json**

```json
{
  "providers": [
    {
      "name": "Claude中转站",
      "base_url": "https://mzlone.top",
      "api_key": "sk-xxx",
      "model": "claude-opus-4-6",
      "api_format": "anthropic"
    }
  ]
}
```

### 2. 识图

```bash
python vision_bridge.py \
  --image "设计图.png" \
  --prompt "详细描述这张UI设计稿的布局、颜色和文字" \
  --provider "Claude中转站"
```

可选参数：

| 参数 | 说明 |
|------|------|
| `--image` | 图片路径（必填） |
| `--prompt` | 分析指令（必填） |
| `--provider` | Provider 名称，不指定则用第一个 |
| `--max-tokens` | 最大输出 tokens，默认 8192 |
| `--list` | 列出所有 Provider |

---

## 支持的中转站 API 格式

| 格式 | 端点 | 适用模型 |
|------|------|---------|
| `anthropic` | `POST /v1/messages` | Claude（Opus / Sonnet / Haiku） |
| `openai` | `POST /v1/chat/completions` | GPT-4o、GPT-4-vision 等 |
| `gemini` | `POST /v1/models/{model}:generateContent` | Gemini 2.0 Flash、Gemini Pro Vision |

---

## 作为 Claude Code Skill 使用

将 `vision-bridge/` 放到 `~/.claude/skills/` 目录下，Claude Code 会自动识别。

在对话中说：
- "分析这张图"
- "识别这个设计稿"
- "帮我看看这个图片"

Agent 会自动调用 `vision_bridge.py` 完成识图。

---

## 技术细节

- **调用方式**：Python subprocess → curl（避免 Python HTTP 库被 Cloudflare 拦截）
- **图片编码**：自动 base64 编码，支持 PNG / JPG / WebP / GIF
- **超时控制**：默认 600 秒，可调
- **零数据落地**：API Key 不写日志，临时文件自动清理

---

## License

MIT
