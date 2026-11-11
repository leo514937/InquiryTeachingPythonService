# Repository Agent Instructions

本文件适用于整个仓库。`MUST` / `MUST NOT` 表示强制要求，`SHOULD` 表示有充分理由时可例外，并在总结中说明。这里的目标约束不代表现有代码已全部满足；修改前 MUST 阅读相关实现和测试。用户明确指令与本文件冲突时，应说明冲突并提出兼容方案；遵循适用的更高优先级指令。

## Project Mission

维护探究式教学服务，让教师既能使用原有 Dialogue Mode，也能使用独立的 Inquiry Workspace。两种模式 MUST 长期共存；优先保护教师内容、权限和已有用户体验。

## Repository Architecture

以下是代码导航，不是功能完整性保证：

- `app/main.py`、`app/core/config.py`：FastAPI、配置、路由及生命周期；Workspace 通过 `inquiry_workspace_enabled` 接入。
- `app/api/`、`app/agents/`、`app/workflow/flows.py`：原有会话、主导师与专家、固定教学阶段；`app/services/draft_*`、`app/services/export_service.py` 负责草案及导出相关逻辑。
- `app/services/rag_service.py`、`app/services/curriculum_permission_service.py`、`app/services/knowledge_graph_service.py`：知识检索、文件级专家授权和知识图谱；`app/db/models.py`、`app/db/migrations.py` 管理旧数据。
- `app/workspace/api.py`、`models.py`、`migrations.py`：Workspace API、独立 SQLAlchemy metadata 和增量建表迁移。`capabilities/` 是注册表及内置能力；`orchestrator/` 是规划与评估；`runtime/` 是执行、事件、图投影和局部重编排；`artifacts/`、`reports/`、`integrations/` 分别处理对象、报告、LLM 与 RAG 适配。
- `frontend/src/App.vue` 与 `frontend/src/components/` 包含原有界面；`frontend/src/workspace/` 包含 Workspace 页面、API、画布、实验、报告、DAG 与状态逻辑。`frontend/src/style.css` 和 `frontend/src/workspace/workspace.css` 是现有样式入口。
- `tests/` 是后端测试；`frontend/tests/` 是前端单元及 Playwright 测试。`todo/inquiry_workspace_dag_prototype.html` 是视觉和交互参考，数据、计时器和运行状态均为演示，不是产品实现。

当前代码已有结构化计划校验、并行执行、重试、租约恢复、取消、审核、事件和对象版本等实现，但能力元数据、通用类型编辑、导出等仍需按具体代码核实。Workspace 报告当前有快照、DOCX 和打印视图；不要假定存在独立的服务端 PDF 导出。新设计或 `docs/` 中的计划不能作为已实现事实。

## Non-Destructive Development Rules

- MUST 保留旧对话模式、主导师、领域专家、固定阶段、会话和草案机制；MUST NOT 为新功能删除或替换它们，也不得将两套工作流混为一体。
- SHOULD 通过独立模块和明确的适配器扩展，公共入口只做必要的增量接线。新模块故障 MUST 与旧模块隔离；检查启动、迁移及后台任务失败的影响。
- MUST 保持旧 API 请求和响应兼容，采用非破坏性数据库迁移，保留已有数据与用户未提交的工作；MUST NOT 进行未经要求的大规模重构。
- 每次修改 MUST 按影响范围回归相关旧功能，包括新模块关闭时的行为。

## Agent & DAG Architecture

职责 MUST 分离：**Planner → Plan Validator → DAG Scheduler → Capability Executor → Evaluator → Replanner**。现有职责分布在 `app/workspace/orchestrator/` 和 `app/workspace/runtime/`，不要求它们必须是同名独立类。

- Planner MUST 根据任务和允许能力动态选择节点并输出结构化计划；执行前 MUST 确定性验证 schema、能力白名单、唯一 ID、依赖存在性、无环、规模和权限等。不得把固定节点顺序包装成动态规划。
- Scheduler MUST 管理依赖顺序、可并行执行、受限重试、超时、持久化状态、取消与故障恢复；Evaluator 检查结果及审核需求，Replanner 基于影响范围进行局部重编排。
- Agent MUST NOT 执行任意代码、扩大工具权限或直接决定数据库写入；模型输出必须经 schema、权限、业务规则和事务边界验证后由受控代码执行。
- 执行 DAG 描述运行节点依赖；Artifact 依赖图描述教学对象和字段影响；教学知识图谱描述领域知识关系。三者 MUST 保持独立，不得互相替代。

## Atomic Capability Contracts

新增能力 MUST 在 `app/workspace/capabilities/` 接入统一协议并提供：唯一 ID 与版本、单一职责、Pydantic 输入输出 schema、前置依赖、权限、超时和重试策略、幂等语义、副作用声明、错误处理、可观测性及有意义的测试。现有 `Capability` 数据类只覆盖其中部分字段；缺失的契约 MUST 在实现及其调用边界明确并验证，不得假定注册即自动执行所有策略。

MUST NOT 将固定教学阶段简单包装成原子节点，或将无关任务塞入巨大能力。确定性任务 SHOULD 优先使用确定性 Python，而非强制调用 LLM。对于有副作用或重试的能力，MUST 防止重复写入并明确失败后的恢复方式。

## Artifact & Dependency Management

- 教学内容 MUST 优先使用结构化 Artifact；对象应具备 ID、类型、内容、版本、来源、依赖、审核状态、创建及修改记录。现有数据分布在 `app/workspace/models.py` 的对象、版本与依赖表中；新增能力不得假定所有元数据已齐备。
- 修改 MUST 创建可追溯的新版本并使用乐观并发检查；冲突应明确反馈，教师锁定内容 MUST NOT 被 Agent 覆盖。保留历史版本和恢复路径。
- 局部重编排 MUST 根据依赖影响确定目标，仅更新受影响且允许修改的对象；删除或替换前 MUST 检查并提示下游引用，不能静默破坏依赖。

## RAG & Permission Boundaries

- MUST 复用现有文件级专家授权。管理员配置 Workspace 可用专家；每次检索以实际用户和专家身份实时校验。多专家检索 MUST 逐个验证权限，不得通过合并权限扩大范围。
- MUST 保留来源追踪和检索审计；未授权或无法验证时明确拒绝或安全降级。缓存、运行详情、历史对象、报告快照及导出 MUST 在读取时防止泄露已撤销授权的内容。
- 参见 `app/workspace/integrations/rag.py`、`app/services/curriculum_permission_service.py` 和相关权限测试。不得绕过文件级过滤，或将知识图谱当作授权依据。

## Report Generation Rules

报告管线 MUST 遵循 **Artifact → Validation → Report Projection → Snapshot → Export**。教学对象是主要内容来源；章节 MUST 映射到明确对象及版本，不得维护互相独立且冲突的正文。对象修改后，相关投影 MUST 反映新版本；历史快照保持可追溯。Word 和 PDF 或打印输出 MUST 基于同一指定版本快照。新增格式前先核实现有实现。

缺少可靠知识依据时 MUST 明示，MUST NOT 编造课标来源；MUST NOT 让最后一个 LLM 无约束地重写全部上游成果。参见 `app/workspace/reports/service.py` 和 `app/workspace/api.py`。

## Frontend Architecture

沿用 Vue 3 + TypeScript。MUST 分离页面 Shell、业务组件和状态逻辑，统一通过现有 API 封装访问后端，避免继续将业务逻辑堆入 `frontend/src/workspace/WorkspaceView.vue`。组件保持单一职责；重要交互 MUST 提供加载、成功、失败、空状态和必要的冲突处理。

教师默认操作教学对象而非底层节点；类型化对象 SHOULD 使用适合其领域的编辑组件。保持画布、报告、实验和执行详情间的连续导航，UI 改造不得删除既有交互。

## UI/UX Design System

以 `todo/inquiry_workspace_dag_prototype.html` 的设计 token、布局、字体层级及交互为视觉参考，采用浅色专业工作台：背景参考 `#F5F8F6`、文字 `#183A33`、强调色 `#27816C`、边框 `#D5E4DC`、卡片 `#FFFFFF`，具体以原型 token 和现有样式为准。中央教学画布是核心，左侧导航清晰，右侧面板按需展示。

MUST 检查视觉一致性、响应式与 `prefers-reduced-motion`；避免密集后台表单、过度渐变、装饰性发光和无意义动画。MUST NOT 随意引入新 UI 框架或为视觉效果牺牲业务正确性。

## DAG Visualization Rules

节点 MUST 来自真实 Planner 计划，边来自真实 `depends_on`，状态来自持久化 Scheduler / Runtime；SSE 用于同步并处理断线、重连和权限撤销。MUST NOT 把原型模拟进度、硬编码九节点或前端定时器生成的成功状态当成真实运行。

展示 MUST 正确处理并行、失败、重试、取消、审核暂停、恢复及历史 DAG；状态变化不应使图布局频繁跳动。动画只能表现已有状态。现有依赖包括 Vue Flow 与 Dagre；选择方案时核实 `frontend/package.json` 和实际性能。

## Database & API Compatibility

数据库变更 MUST 保持旧数据可读、可迁移、可回归；新增 Workspace 表遵循独立 metadata、命名和迁移隔离，检查现有数据库升级及重复执行。API 变更 MUST 验证鉴权、归属和旧请求响应兼容性，必要时采用增量版本化；不得信任客户端提供的用户或专家身份。

## Development Workflow

MUST 按 **代码审计 → 影响分析 → 最小改动 → 实现 → 测试 → 回归 → 总结** 工作：先读相关源码、测试和已有规范，识别新增与修改文件及新旧模块影响；不覆盖用户工作，不做无关重构。架构发生实质变化时 MUST 评估是否同步更新本文件。

新增能力遵守能力契约；新增 Workspace 页面遵守统一 UI 规范；新增表遵守隔离和迁移要求；新增 Agent MUST 明确职责、权限与状态管理。MUST NOT 为完成单个任务擅自降低既有约束。修改本规范时，在开发总结中说明原因。

## Testing & Acceptance Gates

按改动选择并运行有意义的测试，覆盖计划校验、运行状态、权限及越权、对象版本与依赖、并发和旧功能回归；涉及前端时检查构建及相关交互。可从仓库根目录使用 `python -m pytest tests/` 或选择相关 `tests/test_*.py`；在 `frontend/` 使用 `npm run build`、`npm run test:auth`，相关 TypeScript 测试可用 `node --experimental-strip-types --test tests/<文件名>.test.ts`，端到端使用 `npm run test:e2e`。运行前核实环境、依赖及测试配置；不要假定外部模型或服务可用。

MUST 报告实际执行的命令及结果、未运行项目和原因；MUST NOT 声称未执行的测试通过。对于文档等低风险改动，检查结构、路径和准确性，按影响选择必要验证。

## Forbidden Practices

- MUST NOT 删除旧模块，混合新旧工作流，或破坏旧 API、数据库和会话。
- MUST NOT 绕过权限、用模拟数据冒充真实运行、硬编码动态 DAG 的执行结果。
- MUST NOT 未校验就执行 Planner 计划，让 LLM 直接决定数据库写入，或随意覆盖教师编辑和锁定内容。
- MUST NOT 维护互相冲突的报告数据、进行无关大规模重构，或为了 UI 效果牺牲业务正确性。
- MUST NOT 未测试就声称功能完成，也不得把设计文档或原型当作已实现功能。

## Definition of Done

交付前 MUST 核实需求、兼容性、权限、相关测试与回归，并检查实际改动范围。最终总结列出修改文件、实现内容、测试结果、未验证事项和剩余风险；涉及规范变更时说明原因。

## 通用教学任务约束

- Inquiry Workspace 的教学上下文 MUST 由同一次运行统一持久化并传递给规划和能力；学科、年级、时长、语言水平、资源与安全条件缺失时应明确标注，不得把猜测当作教师输入。
- 通用能力和报告 MUST 保持学科中立；专用交互组件仅在适用时显式选择，未注册组件不得替代通用活动。`light_reflection_v1` 是可选专业组件，不是所有实验的默认值。
- 新主题默认创建独立工作空间；追加现有空间必须有明确语义。历史、手工、锁定对象和版本不得在生成时静默删除或覆盖。
- 多学科测试 MUST 区分隔离测试替身与真实模型结果，且测试数据库、知识资料和上传目录必须隔离于用户数据。
