# 项目结构说明（PROJECT_STRUCTURE）

> 本文档描述 **AI 教师探究式教学指导 Python Service** 的代码结构与文件职责。
>
> - 应用版本：`0.1.0`（`app/main.py`）
> - 最新提交：`6af3b25`（`main` 分支，2026-08-28）
> - 仓库：`https://github.com/edison-ai-519/InquiryTeachingPythonService`

---

## 1. 项目概述

这是一个帮助教师设计「探究式科学课堂」的多智能体教学系统：

- **后端**：FastAPI + SQLAlchemy + SQLite，提供 REST + SSE 流式接口
- **前端**：Vue 3 + Vite + TypeScript 工作台
- **核心架构**：`主流程 Agent + 阶段子 Agent + 草案 Agent` 三层协作
- **知识增强**：会话级文件上传（PDF/DOCX/TXT/MD）提取全文 + 可选 Dify Dataset 检索
- **多用户**：注册/登录（Cookie 会话）+ 会话按用户隔离

### 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI、Uvicorn |
| ORM / DB | SQLAlchemy 2.x、SQLite（WAL 模式） |
| 数据校验 | Pydantic v2 |
| LLM 调用 | httpx（OpenAI 兼容接口，默认 OpenRouter） |
| 文件解析 | pypdf、python-docx |
| 前端 | Vue 3.5、Vite 7、TypeScript 5.8、lucide-vue-next |
| 流式协议 | SSE（`text/event-stream`） |

---

## 2. 顶层目录结构

```
InquiryTeachingPythonService/
├── app/                     # FastAPI 后端
│   ├── main.py              # 应用入口，装配中间件与路由
│   ├── schemas.py           # Pydantic 请求/响应模型
│   ├── api/                 # HTTP 路由层（按资源拆分）
│   ├── core/                # 配置、鉴权、SSE 工具
│   ├── db/                  # 数据库引擎、ORM 模型、迁移
│   ├── services/            # 业务逻辑层
│   └── workflow/            # 教学流程模板定义
├── frontend/                # Vue 3 前端工作台
│   └── src/
│       ├── main.ts          # 前端入口
│       ├── App.vue          # 主界面（单文件，核心组件）
│       ├── api.ts           # HTTP/SSE 请求封装
│       ├── types.ts         # 前端类型定义
│       ├── style.css        # 全局样式
│       ├── env.d.ts         # 环境类型声明
│       ├── components/
│       │   └── AuthPanel.vue# 登录/注册面板
│       └── utils/
│           └── markdown.ts  # Markdown 渲染工具
├── docs/                    # 架构指南与开发计划
│   ├── new_agent_architecture_guide.md
│   ├── yumo_master_dify_agent_showcase.html
│   └── superpowers/plans/   # 实现计划
├── done/                    # day1–day7 分阶段开发任务清单
├── tests/                   # 测试（test_day3.py）
├── database/                # 数据库 schema 参考（schema.sql）
├── data/uploads/            # 会话文件存储目录（运行时生成）
├── outputs/                 # 导出产物、截图、演示材料
├── .logs/                   # 运行日志
├── .env / .env.example      # 环境配置（.env 不入库）
├── bootstrap.py             # 一键初始化（建 .env + SQLite 表）
├── requirements.txt         # Python 依赖
├── start-dev.ps1            # Windows 启动脚本
├── start-direct.sh          # Linux 启动脚本
├── project-intro.html       # 项目介绍页
└── app.db / app.db-wal / app.db-shm   # SQLite 数据库文件
```

---

## 3. 后端模块详解

### 3.1 `app/api/` — 路由层

| 文件 | 前缀 | 职责 |
|------|------|------|
| `main.py`（不在 api 下） | — | 装配 CORS、挂载所有 router |
| `health.py` | `/health` | 健康检查 |
| `auth.py` | `/api/auth` | 注册/登录/登出/当前用户 |
| `flows.py` | `/api/flows` | 教学流程列表 |
| `settings.py` | `/api/settings` | 用户聊天模式（main/subagent） |
| `sessions.py` | `/api/sessions` | 会话 CRUD、消息、阶段、草案、回滚 |
| `session_files.py` | `/api/sessions` | 会话文件上传/解析/删除 |
| `chat.py` | `/api/sessions` | 核心对话 SSE 流、取消（约 800 行） |
| `export.py` | `/api/sessions` | Markdown 教案导出 |

### 3.2 `app/core/` — 基础设施

| 文件 | 职责 |
|------|------|
| `config.py` | `Settings` 配置类（从 `.env` 读取）、`DifyAgentConfig`、`get_settings()`；内置七个阶段 Agent 默认注册表 |
| `auth.py` | `get_current_user` 依赖，解析 Cookie token 并返回用户 |
| `sse.py` | `format_sse(event, data)` SSE 事件格式化 |

### 3.3 `app/db/` — 数据层

| 文件 | 职责 |
|------|------|
| `database.py` | 创建 `engine`、`SessionLocal`、`Base`、`get_db()`；SQLite 启用 WAL + busy_timeout |
| `models.py` | 11 个 ORM 模型（见第 5 节） |
| `migrations.py` | `ensure_schema_compatibility()` 轻量增量迁移（补列 + 建索引） |

### 3.4 `app/services/` — 业务逻辑层

| 文件 | 职责 |
|------|------|
| `auth_service.py` | 密码哈希/校验、token 签发/解析/吊销、Cookie 设置 |
| `app_settings_service.py` | 全局与用户的 `chat_mode` 读写（`SUBAGENT_MODE` 常量） |
| `chat_interrupt_service.py` | 流式中断注册表：`ChatInterrupted`、`ActiveChat`、`ChatInterruptRegistry` |
| `context_service.py` | 消息加载、对话历史格式化、LLM 历史转换、文档输入组装、上传参考注入 |
| `dify_agent_service.py` | 阶段专家查找与流式调用（`DifyAgentError`、`DifyAgentService`） |
| `draft_service.py` | 草案标记清理（`strip_draft_markers`） |
| `draft_generate_service.py` | 流式生成候选草案 |
| `draft_edit_service.py` | 选中文本的局部草案编辑 |
| `draft_target_resolver.py` | 选区定位（`DraftTarget`、`DraftTargetResolver`） |
| `draft_proposal_service.py` | diff 提案：创建、序列化、accept/reject、reject_pending |
| `export_service.py` | `MarkdownExportService.compile_lesson_plan` 导出教案 |
| `llm_service.py` | OpenAI 兼容流式调用 + 无 key/异常时 mock 降级（`guide/draft_generate/draft_edit/draft_target` 四种 mock） |
| `prompt_service.py` | 各角色（主导师/阶段专家/草案）提示词组装 |
| `rag_service.py` | Dify Dataset 检索 + mock 教参降级 |
| `session_access_service.py` | `get_owned_session` 会话归属校验 |
| `session_file_service.py` | 文件存储路径、文本提取（PDF/DOCX/TXT/MD） |

### 3.5 `app/workflow/flows.py` — 流程定义

`FLOW_TEMPLATES` 定义三条流程，每条流程包含多个阶段，每个阶段绑定 `agent_id`、`expert`、`direction`（专业能力说明）：

| flow_name | display_name | 阶段数 |
|-----------|--------------|--------|
| `inquiry_7_stage` | 七阶段科学探究流 | 7 |
| `three_step_inquiry` | 三步快速探究流 | 3 |
| `steam_project` | STEAM 项目化探究流 | 4 |

七阶段：`observation_start`（观察起点）→ `question_refine`（循疑问题）→ `hypothesis`（可能的猜想）→ `experiment_design`（实验设计）→ `new_questions`（实验中的新问题）→ `conclusion`（可能的结论）→ `extension`（延伸与新问题）。

对外函数：`list_flows()`、`get_flow(name)`、`get_stage(name, index)`。

---

## 4. 数据模型（SQLite 表）

| 表 | 对应模型 | 用途 |
|----|----------|------|
| `users` | `UserModel` | 用户（用户名唯一、密码哈希、chat_mode） |
| `auth_sessions` | `AuthSessionModel` | 登录会话 token（哈希存储） |
| `app_settings` | `AppSettingModel` | 全局设置键值对 |
| `sessions` | `SessionModel` | 教学会话（话题、流程、当前阶段、草案模式开关） |
| `stage_outputs` | `StageOutputModel` | 每个阶段的草稿/定稿内容（`session_id + stage_id` 唯一） |
| `messages` | `MessageModel` | 会话消息（用户/专家/主导师/草案） |
| `chat_turns` | `ChatTurnModel` | 一轮对话的聚合记录（含草稿 before/after） |
| `session_files` | `SessionFileModel` | 上传文件（提取文本、状态） |
| `draft_proposals` | `DraftProposalModel` | 草案 diff 提案（base/candidate/diff_json） |
| `rag_records` | `RagRecordModel` | 检索记录 |
| `agent_conversations` | `AgentConversationModel` | 阶段专家 conversation_id 记忆（`session_id + agent_id` 唯一） |

---

## 5. API 接口清单

### 认证 `/api/auth`
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/register` | 注册 |
| POST | `/login` | 登录 |
| POST | `/logout` | 登出 |
| GET | `/me` | 当前用户 |

### 流程与设置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/flows` | 流程列表 |
| GET / PUT | `/api/settings/chat-mode` | 读取/切换聊天模式 |

### 会话 `/api/sessions`
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `` | 创建会话 |
| GET | `` | 会话列表 |
| GET | `/{session_id}` | 会话详情 |
| DELETE | `/{session_id}` | 删除会话（级联清理） |
| GET | `/{session_id}/messages` | 消息列表 |
| POST | `/{session_id}/select_flow` | 切换流程（当前固定返回 409，需新建会话） |
| POST | `/{session_id}/confirm-stage` | 确认阶段并推进 |
| PUT | `/{session_id}/draft-mode` | 开关草案模式 |
| GET | `/{session_id}/draft-proposal` | 获取活动草案提案 |
| POST | `/{session_id}/draft-proposals/{proposal_id}/actions` | 接受/拒绝提案 hunk |
| POST | `/{session_id}/rollback` | 回滚最近对话/阶段 |
| PUT | `/{session_id}/stages/{stage_id}/draft` | 保存阶段草稿 |
| GET | `/{session_id}/dify_agents` | 列出阶段专家 |
| GET/POST/DELETE | `/{session_id}/files[/{file_id}]` | 会话文件管理 |
| POST | `/{session_id}/chat` | 核心对话（SSE） |
| POST | `/{session_id}/chat/{request_id}/cancel` | 取消流式生成 |
| GET | `/{session_id}/export` | 导出 Markdown 教案 |

### SSE 事件类型（`/chat`）

```text
event: stage       # 当前阶段
event: agent       # 当前发言 Agent
event: status      # 状态（guide/draft 的 start/done/error）
event: delta       # 正文增量
event: draft       # 草案增量（右侧工作台）
event: proposal    # 草案 diff 提案
event: warning     # 专家不可用等提示
event: interrupted # 被取消，不落库
event: done        # 本轮结束
```

---

## 6. 前端结构

| 文件 | 说明 |
|------|------|
| `main.ts` | 挂载 Vue 应用 |
| `App.vue` | **主界面单文件组件（约 74 KB）**：会话管理、聊天流、草案工作台、阶段推进、导出、文件上传、聊天模式切换、SSE 事件消费 |
| `api.ts` | `fetch` 封装（`credentials: include`）+ SSE 流解析（`streamChat`） |
| `types.ts` | 前端类型：`FlowInfo`、`SessionDetail`、`DraftProposal`、`MessageItem` 等 |
| `components/AuthPanel.vue` | 登录/注册面板 |
| `utils/markdown.ts` | Markdown 渲染工具 |

> 注意：`App.vue` 是当前唯一的大组件，承载了几乎全部交互逻辑，后续可考虑按「会话列表 / 聊天区 / 草案工作台 / 文件面板」拆分。

### 前端环境变量

- `VITE_API_BASE`：后端地址，默认 `http://127.0.0.1:8010`（`api.ts`）

---

## 7. 核心请求生命周期（一次 `/chat`）

```
前端 streamChat()
  → POST /api/sessions/{id}/chat
  → chat.py 校验会话归属 + 加载上下文（ContextService）
  → 根据 draft_mode_enabled / chat_mode 分支：
       ├─ 草案模式 → DraftGenerateService / DraftEditService 流式生成候选
       │             → DraftProposalService 生成 diff 提案
       ├─ subagent → DifyAgentService 直接调阶段专家
       └─ main     → PromptService 组装提示词 → LLMService 流式输出引导
  → save_chat_result() 落库（用户/专家/主导师消息 + chat_turns + 草稿）
  → SSE: stage → agent → status/delta/draft/proposal → done
```

---

## 8. 配置项（`.env`，参考 `.env.example`）

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | 数据库连接（默认 `sqlite:///./app.db`） |
| `FRONTEND_ORIGIN` | CORS 允许来源（逗号分隔） |
| `AUTH_SESSION_DAYS` / `AUTH_COOKIE_SECURE` | 登录有效期 / Cookie 安全标志 |
| `UPLOAD_DIR` / `UPLOAD_MAX_FILE_BYTES` / `UPLOAD_MAX_FILES_PER_SESSION` / `UPLOAD_MAX_TOTAL_CHARS` | 文件上传限制 |
| `LLM_API_KEY` / `LLM_API_BASE` / `LLM_MODEL` / `LLM_REASONING_ENABLED` / `LLM_HTTP_REFERER` / `LLM_APP_TITLE` | 主导师模型（OpenRouter 兼容） |
| `DIFY_DATASET_API_URL` / `DIFY_DATASET_ID` / `DIFY_DATASET_API_KEY` | 可选 RAG 检索 |
| `DIFY_STAGE_AGENT_MODE` | 阶段专家模式：`mock` / `live` |
| `DIFY_STAGE_AGENTS_JSON` | 阶段 Agent 配置（为空则用内置注册表） |
| `REQUEST_TIMEOUT_SECONDS` | 外部请求超时 |

---

## 9. 启动方式

```bash
# 后端
python bootstrap.py                       # 初始化 .env + SQLite 表
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload

# 前端
cd frontend && npm install && npm run dev  # http://localhost:5173
```

或使用 `start-dev.ps1`（Windows）/ `start-direct.sh`（Linux）一键启动。

---

## 10. 已知约定与注意点

- `select_flow` 当前被固定为返回 409（流程创建后不可修改，需新建会话）。
- LLM 无 key 或调用失败时自动降级到 `mock` 流式输出，保证离线联调。
- 阶段专家默认 `mock` 模式，接真实 Dify 时切换 `live` 并配置 `DIFY_STAGE_AGENTS_JSON`。
- 回滚逻辑对 `chat_turns` 缺失的旧数据有 legacy 兜底。
