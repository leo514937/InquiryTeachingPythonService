# AI 教师探究式教学指导 Python Service

这是一个新建的、可独立运行的 Python 服务项目，放在 `YBG0915` 工作区下面，但它本身不是 `YBG0915` 里所有内容的“统一入口”。

## 它和 `YBG0915` 的关系

`YBG0915` 是当前这个本地工作区的总目录，里面放着多个历史项目、参考实现、数据备份和说明文档，例如：

- `EduGate_20251201`：原有的教育平台后端
- `GoMAown_20251201`：可参考的流程与专家路由实现
- `GUI_20251201`：原有前端项目
- `Data`：数据备份与样例资料
- `easy(1).txt`：本次新项目的源文档

`InquiryTeachingPythonService` 则是基于 `easy(1).txt` 重新新建出来的独立项目目录。它的职责是把“7 阶段探究式教学流 + RAG + SSE + 草稿导出”这条链路单独做成一个新的可运行服务。

## 它和 `YBG0915` 里其他项目的区别

- `YBG0915` 更像一个“项目资料仓库”或“工作区总目录”，里面装着多个彼此独立的项目、旧代码和数据。
- `InquiryTeachingPythonService` 是一个“单独的新应用”，拥有自己的后端、前端、数据库、启动脚本和日常任务文档。
- `YBG0915` 里的其他子目录主要承担参考、对照、迁移或历史保留的作用。
- `InquiryTeachingPythonService` 里的代码是本次要实际运行和交付的主体，不依赖修改外层其他项目即可独立启动。

## 本项目参考来源

服务参考了 `GoMAown_20251201` 的主链路思想：

- 会话内保存当前 `flow_name`，类似 `GoMAown` 的 `FlowName`
- `select_flow` 切换流程后重置阶段输出与专家会话
- 主教学导师贯穿整个教学流，并按当前阶段整合专家意见
- 七个阶段自动绑定七个独立 Dify Agent，每个专家维护独立 `conversation_id`
- SSE 流式输出 `stage`、`agent`、`delta`、`draft`、`done`
- 使用 `===DRAFT_START===` / `===DRAFT_END===` 自动同步右侧草案
- 支持回滚最近对话和导出 Markdown 教案

## 本项目边界

- 本项目的代码都集中在 `InquiryTeachingPythonService/` 下。
- `EduGate_20251201`、`GoMAown_20251201`、`GUI_20251201` 等目录保留为参考实现，不需要为了运行本项目而改动。
- 本项目自己的运行状态、数据库和前端构建产物都在 `InquiryTeachingPythonService/` 内部维护。

## 目录

- `app/`：FastAPI 后端
- `frontend/`：Vue 3 + Vite 前端工作台
- `docs/`：day1-day7 开发任务文档
- `bootstrap.py`：SQLite 初始化与本地启动引导

## 启动

```bash
cd C:\Users\aidis\Desktop\YBG0915\YBG0915\InquiryTeachingPythonService
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

默认没有登录校验，接口可直接访问。

## 主导师模型

主教学导师通过 OpenRouter 的 OpenAI 兼容接口调用：

```text
LLM_API_BASE=https://openrouter.ai/api/v1
LLM_MODEL=deepseek/deepseek-v4-flash
LLM_REASONING_ENABLED=false
LLM_API_KEY=在本地 .env 中配置
```

`LLM_REASONING_ENABLED=false` 用于保证教学对话优先产生可流式展示的正文。`.env` 已加入 `.gitignore`，密钥不会进入版本控制。

前端启动：

```bash
cd C:\Users\aidis\Desktop\YBG0915\YBG0915\InquiryTeachingPythonService\frontend
npm install
npm run dev
```

一键初始化：

```bash
cd C:\Users\aidis\Desktop\YBG0915\YBG0915\InquiryTeachingPythonService
python bootstrap.py
```

## 主要接口

```text
GET  /health
GET  /api/flows
POST /api/sessions
GET  /api/sessions/{session_id}
GET  /api/sessions/{session_id}/messages
POST /api/sessions/{session_id}/select_flow
POST /api/sessions/{session_id}/chat
POST /api/sessions/{session_id}/rollback
GET  /api/sessions/{session_id}/dify_agents
PUT  /api/sessions/{session_id}/stages/{stage_id}/draft
GET  /api/sessions/{session_id}/export
```

## 快速请求示例

创建会话：

```bash
curl -X POST http://localhost:8010/api/sessions ^
  -H "Content-Type: application/json" ^
  -d "{\"topic\":\"光的反射\",\"flow_name\":\"inquiry_7_stage\"}"
```

切换流程：

```bash
curl -X POST http://localhost:8010/api/sessions/{session_id}/select_flow ^
  -H "Content-Type: application/json" ^
  -d "{\"flow_name\":\"three_step_inquiry\",\"clear_messages\":true}"
```

主导师与当前阶段专家协同对话：

```bash
curl -N -X POST http://localhost:8010/api/sessions/{session_id}/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"type\":\"chat\",\"message\":\"我想从生活中的镜子反光现象开始导入\"}"
```

后端会自动调用当前阶段绑定的 Dify 专家，再由 `main_agent` 整合为主导师回复，无需前端手动选择专家。

推进阶段：

```bash
curl -N -X POST http://localhost:8010/api/sessions/{session_id}/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"type\":\"sys_action\",\"action\":\"next_stage\",\"final_content\":\"本阶段定稿内容\"}"
```

回滚最近一轮对话：

```bash
curl -X POST http://localhost:8010/api/sessions/{session_id}/rollback ^
  -H "Content-Type: application/json" ^
  -d "{\"steps\":1,\"stage_back\":false}"
```

## 七阶段 Dify Agent 配置

默认使用 `mock` 模式暴露七个阶段专家，方便离线联调。接真实 Dify 时把模式改为 `live`，并配置 `.env` 或环境变量：

```text
DIFY_STAGE_AGENT_MODE=live
DIFY_STAGE_AGENTS_JSON=[
  {
    "id": "stage_observation_start",
    "stage_id": "observation_start",
    "name": "情境探寻专家",
    "description": "设计观察起点",
    "api_url": "http://49.233.10.4/v1/chat-messages",
    "api_key": "app-xxx",
    "flow_names": ["inquiry_7_stage", "three_step_inquiry"]
  }
]
```

## 前端事件约定

`POST /api/sessions/{session_id}/chat` 返回 `text/event-stream`：

```text
event: stage
event: agent    # 当前阶段专家
event: delta    # 阶段专家回复
event: warning  # 专家不可用时可选
event: agent    # main_agent
event: delta    # 主导师整合回复
event: draft    # 仅由主导师更新草稿
event: done
```

每轮正常对话会保存教师、阶段专家、主导师三条消息。Dify 不可用时会发送 `warning`，主导师继续完成本轮回答并在 `done` 中返回 `degraded=true`。
