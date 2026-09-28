## 目录

- `app/`：FastAPI 后端
- `frontend/`：Vue 3 + Vite 前端工作台
- `docs/`：day1-day7 开发任务文档
- `bootstrap.py`：SQLite 初始化与本地启动引导

## 启动

Windows 一键启动（已有依赖时）：

```powershell
.\start.bat
```

首次启动或依赖缺失时：

```powershell
.\start.bat -Install
```

默认启动后端 `http://127.0.0.1:8010` 和前端 `http://127.0.0.1:5173`，成功后自动打开浏览器。脚本会复用已经健康运行的服务；端口被其他程序占用时会报错并暂停窗口，不会直接结束对方进程。确需重启本项目时可运行 `.\start.bat -Restart`；不希望自动打开页面时可增加 `-NoBrowser`，日志保存在 `.logs/`。

手动启动方式：

```bash
cd \InquiryTeachingPythonService
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

首次访问前端后请先注册用户名和密码。登录后只能看到和操作当前账号创建的会话。

登录页提供“普通用户”和“管理员”两个入口。管理员账号可自由注册，并可在登录后的工作台维护全局课标知识库；普通用户只能查看课标列表。可通过 `ADMIN_REGISTRATION_ENABLED=false` 关闭新增管理员注册，已有管理员仍可登录。

当前 HTTP 部署地址：`http://152.136.39.252:5173/`。

## 主导师与领域专家

教学流程始终由 `main_tutor` 主导师推进。教师也可以在每次提问前临时选择一位领域专家；专家只回答当前这一轮，完成后自动回到主导师。第一版包含昆虫、自然生态、数学数据、安全伦理和物理探究五位专家，均通过独立角色提示词划分能力边界，共用现有 OpenAI 兼容模型配置：

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
POST /api/auth/register
POST /api/auth/login
POST /api/auth/admin/register
POST /api/auth/admin/login
POST /api/auth/logout
GET  /api/auth/me
GET  /health
GET  /api/flows
GET  /api/experts
GET  /api/curriculum/files
POST /api/curriculum/files
PUT  /api/curriculum/files/permissions
DELETE /api/curriculum/files?source={source}
GET  /api/curriculum/status
POST /api/curriculum/vector/rebuild
GET  /api/curriculum/retrievals
GET  /api/curriculum/export
POST /api/curriculum/import

GET    /api/knowledge/sources
GET    /api/knowledge/sources/{id}
GET    /api/knowledge/sources/{id}/chunks
POST   /api/knowledge/sources
PATCH  /api/knowledge/sources/{id}
POST   /api/knowledge/sources/{id}/review
DELETE /api/knowledge/sources/{id}
GET    /api/knowledge/sources/export
POST   /api/knowledge/sources/import
POST /api/sessions
GET  /api/sessions/{session_id}
GET  /api/sessions/{session_id}/messages
GET  /api/sessions/{session_id}/files
POST /api/sessions/{session_id}/files
DELETE /api/sessions/{session_id}/files/{file_id}
POST /api/sessions/{session_id}/select_flow
POST /api/sessions/{session_id}/chat
POST /api/sessions/{session_id}/chat/{request_id}/cancel
POST /api/sessions/{session_id}/rollback
PUT  /api/sessions/{session_id}/stages/{stage_id}/draft
GET  /api/sessions/{session_id}/export
```

会话参考资料支持 `PDF`、`DOCX`、`TXT` 和 `MD`。上传成功后，系统会提取全文并加入当前会话后续的主导师、领域专家和草案上下文。默认限制为单文件 20 MB、每个会话 10 个文件、可用正文总计 50,000 字符；扫描版 PDF 暂不支持 OCR。

## 本地课标混合 RAG

将权威课标文件放入 `data/curriculum/`，支持 `MD`、`TXT`、`PDF` 和 `DOCX`。扫描版 PDF 暂不支持 OCR。执行以下命令导入：

管理员可以在工作台上传、替换或删除课标，并在文件解析、切片和向量化完成后单独配置哪些专家可以查询该文件。新文件默认未授权；一个文件可以授权给多位专家，权限变更在下一轮咨询中立即生效。普通用户只能查看文件与授权结果。命令行方式保留用于批量导入：

```powershell
cd E:\InquiryTeachingPythonService
.\.venv\Scripts\python.exe scripts\ingest_curriculum.py data\curriculum
```

导入命令会递归读取目录、切分正文并写入本地 `curriculum_chunks` 表。同一路径的文件重复导入时会替换旧片段。只有教师显式选择的专家会查询课程知识库：系统先读取 `curriculum_source_agent_permissions`，然后在获权文件范围内执行 BM25 和本地 BGE Embedding 召回。主导师、草案能力和未被选择的专家不会查询课程库。完整命中、专家 ID、授权来源及各路分数保存在 `rag_records` 中。

首次部署或模型缺失时执行一次初始化脚本。脚本会下载或验证模型，并根据 `curriculum_chunks` 重建 Chroma 索引：

```powershell
cd E:\InquiryTeachingPythonService
.\.venv\Scripts\python.exe scripts\setup_curriculum_rag.py
```

离线服务器可先把模型放入 `data/models/bge-small-zh-v1.5/`，再添加 `--skip-download`。所有网页用户共用后端模型，无需在个人电脑下载。

默认配置如下，可在 `.env` 中覆盖：

```text
CURRICULUM_DIR=./data/curriculum
CURRICULUM_RAG_ENABLED=true
CURRICULUM_TOP_K=4
CURRICULUM_CANDIDATE_K=16
CURRICULUM_CHUNK_SIZE=512
CURRICULUM_CHUNK_OVERLAP=64
CURRICULUM_RERANK_ENABLED=true
CURRICULUM_VECTOR_ENABLED=true
CURRICULUM_VECTOR_REQUIRED=false
CURRICULUM_VECTOR_MIN_SIMILARITY=0.5
CURRICULUM_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
CURRICULUM_EMBEDDING_MODEL_DIR=./data/models/bge-small-zh-v1.5
CURRICULUM_EMBEDDING_DEVICE=cpu
CURRICULUM_VECTOR_DIR=./data/curriculum_vector
CURRICULUM_VECTOR_COLLECTION=curriculum_chunks
CURRICULUM_HYBRID_VECTOR_WEIGHT=0.65
CURRICULUM_HYBRID_BM25_WEIGHT=0.35
```

`app.db` 中的 `curriculum_chunks` 是课标正文事实来源，`data/curriculum_vector/` 仅保存可重建的 Chroma 向量索引。模型、索引、快照、`.venv` 和 `.env` 均不提交到 Git。Embedding 或 Chroma 不可用时会自动退回 BM25；仅当 `CURRICULUM_VECTOR_REQUIRED=true` 时才把向量失败视为必须处理的错误。

## 北京乡村振兴四层知识库

`rural_revitalization` 资料按基础法规、年度任务、乡村 CEO 与人才、基层合规四层管理。乡村资料上传后默认进入草稿，补齐来源、地域、效力、资料性质和主题等元数据，经提交审核和发布后才对普通用户可见。法规和任务文件按章、条、编号任务切片，条款内部可继续拆分，但不会跨条款拼接召回上下文。

首批可导入包位于 `data/knowledge_seeds/rural_revitalization-v1.zip`，内含 `knowledge.json`、`review-manifest.json` 和 19 份官网原文或官网正文快照。重新核验并构建种子包可运行：

```powershell
.\.venv\Scripts\python.exe scripts\build_rural_revitalization_seed.py
```

新接口导出 v4、导入兼容 v1—v4；旧 `/api/curriculum` 接口继续导出 v3，并保留旧客户端响应结构。

## 生态资料自动建图

分类为 `ecology` 的知识文件会自动进入串行 LightRAG 抽取队列。LightRAG 只负责候选实体和关系抽取；正式问答仍使用现有 SQL 图谱、片段证据、Chroma 与 BM25。只有原文片段同时出现双方实体（名称或别名）和受控关系词时，关系才会发布到正式图谱。

自动关系支持取食、访花、授粉、栖息、产卵、危害、捕食和寄生。管理员可以在“知识图谱与证据连接”中查看同步进度、手工覆盖或屏蔽自动关系，也可以恢复自动管理。上传、替换和删除生态资料会自动创建增量任务；课程课标和乡村振兴资料不会进入 LightRAG。

```text
ECOLOGY_GRAPH_AUTO_SYNC_ENABLED=true
ECOLOGY_LIGHTRAG_DIR=./data/lightrag/ecology
ECOLOGY_GRAPH_WORKER_POLL_SECONDS=2
ECOLOGY_GRAPH_JOB_MAX_ATTEMPTS=3
ECOLOGY_GRAPH_EXTRACT_MODEL=deepseek/deepseek-v4-flash
```

同步接口（管理员）：

```text
POST /api/knowledge/ecology-graph/sync
GET  /api/knowledge/ecology-graph/sync
POST /api/knowledge/graph/relations/{relation_id}/restore-auto
```

## GloBI 结构化生态关系导入

管理员可在“图谱管理 → GloBI 导入”上传 GloBI CSV、TSV、GZIP 或 ZIP 稳定数据，也可以填写受信任的 GloBI/Zenodo HTTPS 下载地址。系统先按 `Insecta`、`Plantae` 分类路径和受控关系类型生成预览，再将昆虫—植物与昆虫—昆虫关系直接写入 SQL 图谱，不经过 LightRAG 和向量化。

导入会保留外部分类 ID、学名、原始关系、研究引用、数据集引用和地域字段。同一三元组只发布一条正式关系，多条 GloBI 记录作为外部证据关联；只有 GloBI 证据的关系会标记为“全球关系”，问答时不得表述为九龙山或门头沟本地观察。重复导入保持幂等，并支持按导入批次回滚；手工覆盖和其他来源证据不会被回滚删除。

接口（管理员，使用 `multipart/form-data`）：

```text
POST /api/knowledge/globi/import/preview
POST /api/knowledge/globi/import
GET  /api/knowledge/globi/import
GET  /api/knowledge/globi/import/{run_id}/summary
POST /api/knowledge/globi/import/{run_id}/retry
POST /api/knowledge/globi/import/{run_id}/rollback
```

支持的首批关系包括 `eats`、`preysOn`、`pollinates`、`pollinatedBy`、`visitsFlowersOf`、`flowersVisitedBy`、`hasHabitat`、`parasiteOf` 及其受控反向关系。不明确的“相关”“共现”等关系不会自动发布。

```text
GLOBI_IMPORT_WORKER_ENABLED=true
GLOBI_IMPORT_WORKER_POLL_SECONDS=2
```

### GloBI 对话实时查询（不落库）

当教师选择昆虫 Agent 或自然 Agent 时，系统会从本轮问题提取最多 3 个昆虫或植物实体，使用规范学名双向查询 GloBI API，并把受控关系作为临时图谱通过聊天 SSE 返回。临时节点和关系使用 `globi_runtime_*` ID，只保存在后端进程内的 TTL 缓存中，不创建或修改 `knowledge_entities`、`knowledge_relations`、`globi_interactions` 或导入任务记录，也不会出现在全量图谱、导出文件和管理员编辑列表中。

聊天与手动刷新都会流式返回 `graph_progress` 阶段（本地匹配、物种规范化、双向查询、去重建图）。前端将本地知识图谱和 GloBI 全球关系绘制在两张独立画布中，避免混淆本地证据与全球参考。GloBI 请求按方向并发执行，瞬时超时和 429/5xx 会有限重试；单个方向失败时保留其他方向的有效结果，超大响应也会保留已完整接收的 CSV 记录，再按关系类型去重、均衡筛选后绘制。

回答引用实时结果时会明确标注为 GloBI 全球数据库关系，不把它当作九龙山或门头沟的本地观察。服务重启或缓存过期后，旧的临时图谱选择失效，需要重新查询。

```text
GLOBI_RUNTIME_ENABLED=true
GLOBI_RUNTIME_CACHE_SECONDS=86400
GLOBI_RUNTIME_TIMEOUT_SECONDS=10
GLOBI_RUNTIME_MAX_ENTITIES=3
GLOBI_RUNTIME_RESULT_LIMIT=250
GLOBI_RUNTIME_RELATION_LIMIT=40
GLOBI_RUNTIME_CONCURRENCY=2
GLOBI_RUNTIME_MAX_RESPONSE_BYTES=8388608
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

主导师对话：

```bash
curl -N -X POST http://localhost:8010/api/sessions/{session_id}/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"type\":\"chat\",\"request_id\":\"chat_demo_001\",\"message\":\"我想从生活中的镜子反光现象开始导入\"}"
```

流式生成过程中可用同一个 `request_id` 发送取消请求；后端会停止当前模型流，且中断的半截回答不会落库：

```bash
curl -X POST http://localhost:8010/api/sessions/{session_id}/chat/chat_demo_001/cancel
```

临时咨询物理专家时，在同一请求中传入 `expert_id`。本轮只返回专家建议，不修改草案，下一轮不传时自动由主导师继续：

```bash
curl -N -X POST http://localhost:8010/api/sessions/{session_id}/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"type\":\"chat\",\"message\":\"怎样控制实验变量？\",\"expert_id\":\"physics_teacher_agent\"}"
```

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

## Agent 配置

Agent 采用 YAML 注册表和独立 Markdown 角色提示词：

```text
app/agents/config/agents.yaml
app/agents/prompts/main_tutor.md
app/agents/prompts/experts/*.md
AGENT_CONFIG_PATH=./app/agents/config/agents.yaml
```

配置会校验唯一 ID、`main`/`expert` 角色、可选择状态和提示词文件。知识文件权限不写入 YAML，而由数据库中的文件级授权关系管理。

## 前端事件约定

`POST /api/sessions/{session_id}/chat` 返回 `text/event-stream`：

```text
event: stage
event: agent    # 本轮主导师或显式选择的领域专家
event: delta    # main_tutor 或 expert_advice 回复
event: status   # 主导师引导或草案状态
event: draft    # 主导师内部草案能力的流式内容
event: interrupted  # 本轮被前端或后端中断，不会落库
event: done
```

新增回复统一保存为 `main_tutor` 或 `expert_advice`；历史 `stage_expert` 消息仍可读取。未配置 LLM 密钥时继续使用本地 Mock 回复。
