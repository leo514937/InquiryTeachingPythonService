# 草案工作台状态引导实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让草案模式只在右侧教案文档区完成撰写、修改和差异审阅，同时左侧主对话框只显示主流程 Agent 输出的状态型引导文案。

**Architecture:** 草案模式继续复用现有提案与 diff 审阅能力，但将草案正文从左侧聊天流中剥离。后端草案分支只负责流式生成候选草案、发出开始/完成/失败状态事件；前端根据这些状态事件在主对话区创建短状态消息，并将草案内容只渲染到右侧工作台。

**Tech Stack:** FastAPI SSE、Vue 3、TypeScript、SQLite、Markdown 渲染、现有 DraftProposalService。

---

### Task 1: 后端草案分支改成状态驱动

**Files:**
- Modify: `app/api/chat.py`
- Modify: `app/services/prompt_service.py`

- [ ] **Step 1: 记录草案编辑开始、完成、失败的状态事件**

```python
yield format_sse("status", {"phase": "draft", "state": "start", "text": "正在编辑草案..."})
```

- [ ] **Step 2: 草案生成成功后发出完成事件**

```python
yield format_sse("status", {"phase": "draft", "state": "done", "text": "草案编辑完毕"})
```

- [ ] **Step 3: 草案生成异常时发出失败事件并保留旧草案**

```python
except Exception as exc:
    yield format_sse("status", {"phase": "draft", "state": "error", "text": "草案编辑失败"})
    raise
```

- [ ] **Step 4: 保持草案候选内容仍通过 `draft` 和 `proposal` 事件发送给右侧面板**

```python
yield format_sse("draft", {"content": draft_text, "message_type": "draft_tutor"})
```

- [ ] **Step 5: 用当前草案上下文生成更短的状态化草案提示词**

```python
def build_draft_mode_prompt(...):
    return "你是草案修订Agent，只输出 Markdown 草案正文。"
```

### Task 2: 前端主对话改成状态气泡

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 草案模式下不再把 draft 事件追加成左侧聊天消息**

```ts
draft: () => {
  // 只更新右侧草案区，不新增左侧聊天正文
}
```

- [ ] **Step 2: 在 status 事件里创建或更新一个主流程状态消息**

```ts
status: (data) => {
  if (requestMode === "draft") {
    // 显示“正在编辑草案 / 草案编辑完毕 / 草案编辑失败”
  }
}
```

- [ ] **Step 3: 保留右侧草案 diff 审阅、接受、拒绝和直接编辑**

```ts
draftProposal.value = data.proposal || null;
```

- [ ] **Step 4: 草案完成后刷新右侧提案，但不在左侧塞入草案正文**

```ts
await refreshDraftProposal();
```

### Task 3: 验证

**Files:**
- Test: `frontend/src/App.vue`
- Test: `app/api/chat.py`

- [ ] **Step 1: 运行后端语法检查**

```powershell
C:\Users\14011\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile app\api\chat.py
```

- [ ] **Step 2: 运行前端构建**

```powershell
C:\Users\14011\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe node_modules\vite\bin\vite.js build
```

- [ ] **Step 3: 手工验证草案模式交互**

```text
进入草案模式后发送一句话：
1. 左侧只出现状态型主流程消息
2. 右侧出现草案候选和 diff
3. 失败时保留原草案
```
