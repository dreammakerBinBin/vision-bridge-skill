---
name: vision-bridge
description: 当需要识图、分析图片、视觉识别、设计稿分析、PSD转代码时使用。用视觉模型（Claude/GPT/Gemini）分析图片，返回文本描述供后续处理。
---

# Vision Bridge — 视觉模型桥接

## 概述

将图片发送给视觉模型（Claude / GPT / Gemini）分析，获取纯文本描述。适用于主 agent 缺乏多模态能力时的图片理解任务。

## 触发场景

- 用户提到"识别这张图""分析图片""看图""这个图是什么"
- PSD / 设计稿 → 前端代码（先用本 skill 提取规格）
- 截图 → 文本描述
- 图表 / 表格 / 文档扫描件 → 结构化数据

## 核心原则

1. **视觉模型只输出描述，不生成代码**。代码生成由主 agent 完成。
2. 必须指定 --prompt，明确告诉模型要从图片中提取什么。
3. 不可辨认的内容写"留空"，禁止编造。

## 使用方式

```bash
python "C:\Users\admin\.claude\skills\vision-bridge\vision_bridge.py" \
  --image "<图片路径>" \
  --prompt "<分析指令>" \
  --provider "<Provider名称>" \
  --max-tokens 8192
```

参数说明：
| 参数 | 必填 | 说明 |
|------|------|------|
| --image | ✅ | 图片文件路径（PNG/JPG/WebP） |
| --prompt | ✅ | 发给视觉模型的指令 |
| --provider | ❌ | Provider 名称，不指定则用 config.json 第一个 |
| --max-tokens | ❌ | 最大输出 tokens，默认 8192 |

列出所有 Provider：
```bash
python "C:\Users\admin\.claude\skills\vision-bridge\vision_bridge.py" --list
```

## 执行流程

### 步骤 1：确认图片存在
用 Read 工具或 Glob 确认图片文件存在。如为 PSD，先用 `psd-tools` 导出预览图：
```python
from psd_tools import PSDImage
psd = PSDImage.open("path.psd")
psd.composite().save("preview.jpg")
```

### 步骤 2：确定 Provider
如果用户指定了模型偏好（如"用 Claude""用 GPT"），匹配对应的 Provider。否则用默认（config.json 第一个）。

### 步骤 3：构造 Prompt
根据用户需求构造清晰的 prompt，告诉视觉模型要提取什么。典型模板：
- 设计稿还原：列尺寸、颜色、文字、布局、装饰元素
- 通用识图："详细描述这张图片的内容，包括物体、文字、颜色、布局"

### 步骤 4：调用脚本
用 Bash 工具执行 vision_bridge.py，结果输出到 stdout，通过临时文件传给主 agent 读取。

### 步骤 5：读结果
用 Read 工具读取脚本 stdout 输出（agent 的 Bash 工具直接返回 stdout 内容）。

## 配置管理

启动可视化配置面板：
```bash
python "C:\Users\admin\.claude\skills\vision-bridge\server.py"
# 或直接双击 start.bat
```
浏览器打开 http://localhost:8081 添加/编辑 Provider。

配置文件：`C:\Users\admin\.claude\skills\vision-bridge\config.json`

## 支持的中转站 API 格式

| 格式 | 适用模型 |
|------|---------|
| `anthropic` | Claude (Opus/Sonnet/Haiku) |
| `openai` | GPT-4o, GPT-4-vision 等 |
| `gemini` | Gemini 2.0 Flash, Gemini Pro Vision 等 |

## 注意事项

- 脚本用 curl subprocess 调用 API，绕过部分中转站的 Cloudflare 拦截。
- 图片过大时会自动 base64 编码传输，超时 600 秒。
- 如果调用失败，先检查 Provider 配置是否正确（用配置面板的"测试连接"按钮验证）。
- 不要将脚本的输出当作最终代码，它只是视觉描述，代码还需主 agent 生成。
