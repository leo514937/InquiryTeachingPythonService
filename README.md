## 目录

- `app/`：FastAPI 后端
- `frontend/`：Vue 3 + Vite 前端工作台
- `docs/`：day1-day7 开发任务文档
- `bootstrap.py`：SQLite 初始化与本地启动引导

## 启动

```bash
cd \InquiryTeachingPythonService
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
cd \InquiryTeachingPythonService\frontend
npm install
npm run dev
```

一键初始化：

```bash
cd \InquiryTeachingPythonService
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
