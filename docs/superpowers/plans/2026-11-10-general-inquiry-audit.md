# 通用探究教学改造：审计与实施记录

## 审计（2026-11-10）

- 测试替身固定主题：`tests/workspace_e2e_server.py:66`、`:84`；真实模型分支不使用该替身。
- 生产提示词限定反射组件：`app/workspace/capabilities/builtin.py:82`；能力校验与绑定在 `:96`、`:136`。反射交互本身应保留为可选组件。
- 固定入口：`frontend/src/workspace/components/TeachingCanvas.vue:4`、`:18` 和 `frontend/src/workspace/WorkspaceView.vue:23`；显式添加接口与实现为 `app/workspace/api.py:410`、`app/workspace/artifacts/service.py:41`。
- 旧主题混入：`app/workspace/runtime/runs.py:300` 以新对象追加，`app/workspace/reports/service.py:26` 读取全部对象；同一空间的多轮结果未形成独立方案。
- 通用上下文缺失：`app/workspace/api.py:103` 的运行请求仅有 goal 和 mode；`app/workspace/runtime/runs.py:18` 只持久化 goal，节点各自解释需求。
- 报告类型与反射组件耦合：`app/workspace/reports/service.py:34`、`:47`；教学画布类型集中于 `frontend/src/workspace/components/TeachingCanvas.vue`。
- 规划白名单、能力注册和前端标签分别维护：`app/workspace/orchestrator/planner.py:8`、`app/workspace/capabilities/builtin.py:37`、`frontend/src/workspace/dagLayout.ts:27`。

## 增量实施

1. 在运行请求和持久化记录上新增兼容旧调用的教学上下文，统一交给 Planner 与每个能力，显式标注未知条件。
2. 去除通用提示词对特定组件的暗示，将组件约束限制在组件绑定路径；提供通用活动类型及报告投影。
3. 保留已有对象和旧接口，以显式创建新工作空间的方式隔离不同主题，保留现有追加与版本功能。
4. 调整通用画布的反射入口为可选专业组件，保留现有反射对象与交互。
5. 补充跨学科、上下文持久化、权限、迁移、旧对象和报告测试；最后运行构建及隔离回归，并如实记录真实模型结果。

## 本轮实现与验证状态（2026-11-11）

- 上下文与兼容迁移：`app/workspace/context.py:26`、`app/workspace/learner.py:16`、`app/workspace/models.py`、`app/workspace/migrations.py`；`RunInput` 的 `teaching_context` 为可选字段，旧请求和旧记录仍可使用。
- 统一能力目录与扩展：`app/workspace/capabilities/builtin.py:73`，Planner 在 `app/workspace/orchestrator/planner.py:8` 读取同一能力 ID 集合；新增文本、调查、数据三个专业能力，其他通用教学能力仍复用既有能力。
- 组件与界面：`app/workspace/artifacts/components.py:27`、`frontend/src/workspace/activityComponents.ts`，反射组件保留为显式选择；`frontend/src/workspace/components/TeachingCanvas.vue:18` 为可选入口。
- 新主题隔离：`frontend/src/workspace/WorkspaceView.vue:118` 默认新建空间，也可显式追加；受控替换和完整方案级版本尚未实现。
- 报告：`app/workspace/reports/service.py:26` 投影多种活动和学生任务，并标明未确认条件；独立学生任务单导出与连贯性自动评审仍未实现。
- 教学建议：小学低、中、高年级有结构化语言、任务、抽象程度、教师支持和合作建议；它们是年级级别建议，不是实际学情测评。
- 测试：隔离的 Workspace 后端、前端构建/单元测试与多学科浏览器测试通过；原 Workspace 浏览器回归 21 项通过。多学科隔离浏览器使用确定性测试替身，仅验证真实 API、状态和投影路径，不代表真实模型生成质量。
- 真实模型：五个学科场景的首轮验收均未通过；后续小学科学复测曾运行超过 6 分钟未完成，另一次规划未通过校验。未生成可交付的真实模型教学报告；示例文件明确标为合成对象投影。
- 仍需：真实模型 A–E 逐项完整验收；将年级或资源约束修改纳入可追溯的局部影响分析；方案替换/版本的显式受控操作；独立学生任务单；更细粒度的各活动输入输出 Schema、报告连贯性与质量测评。
- 旧工作流保护：继续使用隔离数据库运行测试；不得擅自清理此前可能写入默认数据库的测试数据。

### 当前能力与编排

- 需求、课程检索、知识分析：`requirements.analyze@1`、`knowledge.retrieve@1`、`knowledge.map@1`。
- 目标、问题、通用活动：`goals.compose@1`、`inquiry.design@1`、`activity.design@1`。
- 专业活动：`reading.design@1`、`survey.design@1`、`data.design@1`。
- 评价、质量、报告与组件：`assessment.design@1`、`quality.evaluate@1`、`report.assemble@1`、`report.narrative@1`、`component.bind@1`。
- Planner 从注册能力目录选择节点；完整教学方案验证目标、问题、活动、评价及必要的目标依赖，但没有固定节点数量或固定顺序。真实计划通过验证后由现有 Scheduler 持久化并执行。
- 学生年级建议由 `TeachingContext` 的明确学段与年级生成；年级不明确时不生成个人学情判断。教师可填写资源、安全、语言与其他条件，缺失项在报告中列明。

### 验收结果边界

- A–D 的隔离浏览器测试及未填写学科的主题测试：5 项通过；这些测试使用按主题变化的确定性模型替身。
- E 反射组件：既有独立实验交互浏览器回归通过；不是对所有真实模型输出均能正确绑定的保证。
- F 主题隔离：默认新建空间，测试确认原有手工对象仍在原空间；显式追加仍会把对象保留在同一空间。
- G 对象局部重编排：已有实验材料修改、受影响对象与报告刷新浏览器测试；年级或共享资源条件变化的最小影响重编排尚未实现。
- 真实模型首轮五个场景均未通过完整验收；后续科学任务曾全部执行节点但因目标引用及安全提示暂停审核。此后增加了计划完整性、真实目标引用检查和规划修正提示，最终真实端到端结果需要独立确认。
- 教师报告与学生任务语句已区分字段和显示；独立学生任务单输出、真正的方案级替换／版本操作，以及对所有通用能力逐一提供专用输入输出契约仍未完成。

### 继续验证（2026-11-11）

- 真实模型规划冒烟测试曾生成七节点 DAG；该测试在计划生成后主动取消，并不代表完整教学方案成功。
- 随后的真实模型小学科学完整测试生成十节点 DAG，需求分析和课程检索成功，但目标生成节点两次输出均未通过能力校验，运行失败，未生成可验收报告。诊断仅记录错误类别，无法据此断定具体 JSON 字段错误；教师审核未被自动绕过。
- 对追加生成时修改的教学条件，界面列出变化字段，明确说明当前无法推断最小影响范围，并提示可使用已有对象重编排预览；这是只读提示，不构成条件级自动重编排。
- 最新完整 Workspace 后端回归 137 项通过，前端生产构建及条件变更单元测试通过；真实模型 A–G 仍未完成最终验收。
