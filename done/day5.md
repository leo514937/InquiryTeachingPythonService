# Day 5 - Dify 专家路由

## 当前状态

已完成七阶段专家接口、自动路由、独立上下文和主导师整合链路；真实 Dify 凭证待部署时配置。

## 分工

- 专家目录：Dify Agent 配置、流程可见性、专家列表接口
- 对话隔离：每个专家独立 conversation_id
- 降级兜底：真实 Dify 与 Mock 双模式

## 目标

把七个阶段专家做成自动路由，独立维护 conversation_id，并由贯穿全程的主导师统一整合回复。

## 开发任务

- 定义七阶段 Dify Agent 配置结构。
- 根据当前阶段自动选择专家，不允许前端跨阶段手动切换。
- 维护每个 `(session_id, agent_id)` 的独立 conversation_id。
- 向专家传递全局对话历史、前序定稿和当前草稿。
- 专家回复完成后，由 Python 主导师生成第二条整合回复和草稿。
- Dify 异常时发送 `warning`，主导师继续完成回答。

## 产物

- `app/services/dify_agent_service.py`
- `app/api/sessions.py` 中的 `dify_agents` 接口

## 验收标准

- 选择不同专家时不会互相污染上下文。
- 配置缺失或外部服务失败时仍能继续对话。
- 前端能分别看到阶段专家和主导师两条回复。
- 回滚一轮时同时撤销教师、专家和主导师消息。
