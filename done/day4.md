# Day 4 - RAG 与提示词

## 分工

- RAG 检索：Dify Dataset 适配、离线 Mock 降级、审计记录
- 提示词：按阶段拼装导师提示词，约束 Human-in-the-loop

## 目标

把本地教参检索和阶段提示词组装起来，让主导师回复具备明确教学支撑。

## 开发任务

- 封装 Dify Dataset API 的检索逻辑。
- 设计离线 Mock 检索降级，保证没配外部服务也能联调。
- 根据阶段、课题和草稿拼装主导师提示词。
- 记录每次 RAG 检索审计信息，方便排查。

## 产物

- `app/services/rag_service.py`
- `app/services/prompt_service.py`

## 验收标准

- 没有 Dify 配置时，系统仍能返回稳定回答。
- 配置 Dify 后，可替换为真实教参检索结果。
- 每次检索都有可追踪的记录。
