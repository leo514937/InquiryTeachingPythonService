# 新增工作流与全新子 Agent 体系开发指南

本文说明如何在当前“主流程 agent + 阶段子 agent”框架上，新增一个完全不同的教学流程，并开发一套新的子 Agent 角色体系。

这份指南分成两种情况：

1. **新增工作流，但仍复用现有 agent**
2. **新增工作流，同时开发一套全新的 agent 角色体系**

本文重点讲第二种情况，因为它改动更大，也更容易漏文件。

---

## 一、先理解当前架构

当前项目不是“一个流程配一个单独服务”，而是由下面几层组成：

- **流程层**：定义一个教学流程有哪些阶段
- **角色层**：定义每个阶段由哪个 agent 负责
- **提示词层**：定义每个 agent 在这一阶段应该怎么说
- **记忆层**：定义会话历史、阶段草稿、agent conversation_id 怎么保存
- **路由层**：定义当前对话到底走主流程还是走子 agent
- **前端层**：展示流程、阶段、草稿、消息和切换开关

因此，新增一个“全新的子 Agent 体系”，并不只是多加几个 prompt，而是要把流程、角色、提示词和路由一起改。

---

## 二、当前代码里关键职责分别在哪里

### 1. `app/workflow/flows.py`

这个文件负责定义流程模板。

它决定：

- 当前系统有几个工作流
- 每个工作流有哪些阶段
- 每个阶段叫什么
- 每个阶段由哪个 `agent_id` 负责
- 每个阶段的专业能力说明 `direction` 是什么

核心结构是 `FLOW_TEMPLATES`。

如果你新增流程，首先就是在这里加一个新的流程条目。

### 2. `app/core/config.py`

这个文件负责定义“系统里有哪些阶段 agent”。

`dify_stage_agents()` 相当于 agent 注册表：

- agent 的 `id`
- 绑定的 `stage_id`
- 对外 `name`
- `description`
- `command`
- 适用哪些流程 `flow_names`

如果你的新流程使用了新的 agent 角色，就必须在这里新增对应配置。

### 3. `app/services/prompt_service.py`

这个文件负责构造提示词。

当前有几个关键入口：

- `build_stage_agent_prompt()`
- `build_main_agent_prompt()`
- `opening_message()`

它决定了：

- 阶段子 agent 如何理解自己的职责
- 主流程 agent 如何整合阶段专家意见
- 每次进入新阶段时，主导师如何引导教师

如果你的新 agent 角色定义完全不同，这里通常要重写。

### 4. `app/api/chat.py`

这个文件负责聊天路由与 SSE 流式输出。

它决定：

- 当前消息属于主流程模式还是子 agent 模式
- 当前阶段该调用哪个 agent
- 结果如何写入数据库
- 草稿如何生成并推送给前端

如果新体系不再是“阶段专家 + 主教学导师”的双层结构，这里基本必改。

### 5. `app/services/context_service.py`

这个文件负责整理历史上下文。

它决定：

- 从数据库里读哪些消息
- 如何把消息转成对话历史
- 如何把消息转成 LLM history
- 如何构建当前阶段的文档输入

如果新 agent 需要新的上下文结构，这里也要一起改。

---

## 三、如果只新增工作流，但复用现有 agent，要改什么

如果只是想新增一个新的流程节点结构，但角色能力还沿用现有 agent，那么通常只需要：

### 1. 改 `app/workflow/flows.py`

在 `FLOW_TEMPLATES` 中新增一个流程定义。

每个阶段至少要写：

- `id`
- `name`
- `expert`
- `agent_id`
- `direction_key`

### 2. 确保 `STAGE_DIRECTIONS` 有对应说明

`stage_item(...)` 会用 `direction_key` 去查 `STAGE_DIRECTIONS`。

所以如果你新增了新的阶段语义，就要同步补充 `STAGE_DIRECTIONS`。

### 3. 前端通常不用改

前端会自动从 `/api/flows` 读取流程列表。

只要后端新增流程，前端下拉框会自动出现。

---

## 四、如果要做“全新的子 Agent 角色体系”，要改什么

这才是本文重点。

所谓“全新的子 Agent 角色体系”，指的是：

- 不再沿用现有的“情境探寻专家 / 问题提炼导师 / 头脑风暴教练”等角色
- 每个阶段的专家职责完全不同
- 提示词逻辑也不再适配原有科学探究框架
- 可能连阶段命名、阶段顺序、输出形式都不一样

这种情况下，建议按下面顺序改。

---

## 五、必须改的文件

### 1. `app/workflow/flows.py`

这是新增流程的第一入口。

你需要做两件事：

#### 1) 新增流程模板

在 `FLOW_TEMPLATES` 里增加一个新的流程 key，例如：

- `new_custom_flow`

然后定义：

- `name`
- `display_name`
- `description`
- `stages`

#### 2) 为每个 stage 定义新的角色映射

如果你的角色体系完全不同，建议每个 stage 都明确写：

- `id`
- `name`
- `expert`
- `agent_id`
- `direction_key`

其中：

- `id` 是流程内部阶段标识
- `name` 是展示给用户看的阶段名
- `expert` 是这个阶段的专家角色名
- `agent_id` 是真正调用的 agent id
- `direction_key` 是该阶段的能力说明 key

#### 3) 重写 `STAGE_DIRECTIONS`

如果你的流程阶段语义与现有七阶段探究完全不同，`STAGE_DIRECTIONS` 也应该重写或扩充。

因为现在阶段提示词依赖的不是简单的阶段名称，而是这一段详细的能力说明。

---

### 2. `app/core/config.py`

如果你不复用现有 agent，就要在这里注册新的 agent。

#### 要新增什么

在 `dify_stage_agents()` 里新增多个 `DifyAgentConfig`：

- 新的 `id`
- 新的 `stage_id`
- 新的 `command`
- 新的 `name`
- 新的 `description`
- 新的 `flow_names`

#### 这里的作用

这个函数相当于“系统可用 agent 总目录”。

后端在执行聊天时，会根据当前阶段的 `agent_id` 去这里找对应配置。

#### 什么时候必须改

如果你新增的流程里出现以下任何一种情况，就必须改：

- 新的 agent id
- 新的专家名称
- 新的职责描述
- 新的流程适配范围

---

### 3. `app/services/prompt_service.py`

如果角色定义完全变了，这里通常要重写得最彻底。

#### 你要关注的几个方法

##### `build_stage_agent_prompt()`

这是阶段子 agent 的系统提示词。

如果你要做新的子 agent 体系，这个提示词要重新写清楚：

- 这个 agent 是谁
- 它在当前阶段的目标是什么
- 它允许做什么、不允许做什么
- 它应该如何回应教师
- 它应该输出什么格式

##### `build_main_agent_prompt()`

这是主流程 agent 的提示词。

如果你的主流程从“探究式教案导师”变成别的角色，比如：

- 课程设计总控
- 教学编排导演
- 项目式学习总编辑

那这里就要重写。

##### `opening_message()`

这是切换阶段时的引导语。

如果新流程的切换方式、引导风格、阶段语气都变了，这里也要改。

#### 建议

如果新体系差异很大，不要只做“小修小补”。

更稳妥的方式是把 prompt builder 拆成：

- 一个主流程 prompt builder
- 一组阶段/角色专用 prompt builder

这样以后再新增角色会更清晰。

---

### 4. `app/api/chat.py`

这个文件决定“消息到底走谁”。

如果新体系完全不同，这里要重点检查以下几个问题：

#### 1) 现在是否还需要双层结构

当前逻辑是：

- 主流程模式：只走主导师
- 子 agent 模式：只走阶段专家

如果新体系不是这样，比如：

- 某些阶段要先子 agent，再主 agent
- 某些阶段只调用一个 agent
- 某些阶段要并行多个 agent

那这里必须重构。

#### 2) 记忆写回是否还按当前方式

当前保存逻辑会写：

- `messages`
- `chat_turns`
- `stage_outputs`
- `agent_conversations`

如果新体系不是“阶段草稿”模式，`save_chat_result()` 也要改。

#### 3) 草稿解析规则是否还适用

当前主流程会通过 `DraftService.extract_draft()` 解析草稿块。

如果新体系不再输出这种结构化草稿块，而是改成：

- Markdown 小节
- JSON
- 表格
- 固定模板段落

那这里的解析逻辑也要一起变。

---

## 六、通常也要改的文件

### 1. `app/services/context_service.py`

如果新 agent 需要不同的历史输入格式，你就要调整这里。

常见变更包括：

- 调整历史截断窗口
- 改变角色标签
- 增加某些上下文来源
- 只保留某类消息

比如：

- 子 agent 只看当前阶段消息
- 主 agent 看全部阶段历史
- 某些新 agent 需要单独的摘要记忆

这时就不能沿用现在这套简单的历史拼接方式。

### 2. `app/services/draft_service.py`

如果新体系的草稿结构不同，这里也要改。

比如你希望草稿是：

- 标题 + 三级标题 + 列表
- 特定的 markdown 小节
- 直接以 JSON 字段生成

那么草稿提取和清理逻辑都要换。

### 3. 前端文件

如果新增流程和 agent 角色完全不同，前端通常也要跟着调：

- `frontend/src/types.ts`
- `frontend/src/App.vue`
- `frontend/src/api.ts`
- `frontend/src/style.css`

原因是前端展示里有：

- 流程名
- 阶段名
- 专家名
- 当前阶段状态
- 草案展示方式
- 对话模式开关

如果这些都变了，前端就不能完全不动。

### 4. 测试文件

`tests/test_day3.py` 这类回归测试也要改。

因为测试里默认了当前这套 agent 结构和消息顺序。

---

## 七、推荐的开发顺序

如果你要做一套全新的子 agent 体系，建议按这个顺序开发：

### 第 1 步：先定流程

先在 `flows.py` 写出流程节点。

你要先回答这些问题：

- 这个流程有几个阶段
- 每个阶段的目标是什么
- 每个阶段的输出是什么
- 阶段之间怎么衔接

### 第 2 步：再定角色

然后在 `config.py` 里注册新 agent。

你要明确：

- 每个阶段是谁负责
- 每个角色的职责边界是什么
- 哪些角色只在一个流程里用
- 哪些角色会被多个流程复用

### 第 3 步：再写提示词

然后改 `prompt_service.py`。

这一步要把“角色定义”变成“可执行的 prompt”。

### 第 4 步：再接聊天路由

最后改 `chat.py`。

让它知道：

- 什么时候调用谁
- 怎么传上下文
- 怎么保存结果

### 第 5 步：再调前端和测试

前端负责展示和交互，测试负责保证不会改坏。

---

## 八、一个实用判断标准

你可以用下面这张判断表来决定改哪些文件：

### 只新增流程，不新增角色

通常改：

- `app/workflow/flows.py`
- `STAGE_DIRECTIONS`

### 新增流程，同时新增角色

通常改：

- `app/workflow/flows.py`
- `app/core/config.py`
- `app/services/prompt_service.py`
- `app/api/chat.py`

### 新增流程 + 新角色 + 新输出格式

通常还要改：

- `app/services/context_service.py`
- `app/services/draft_service.py`
- 前端相关文件
- 测试文件

---

## 九、建议的设计原则

如果你打算长期维护多套 agent 体系，建议遵循下面几个原则：

### 1. 让流程定义和角色定义分离

不要把阶段顺序和角色职责揉成一坨。

### 2. 每个角色只做一件事

一个 agent 的职责越单一，后面越容易维护。

### 3. 提示词和流程模板不要硬编码在多个地方

最好统一收口在：

- `flows.py`
- `config.py`
- `prompt_service.py`

### 4. 草稿格式要提前定

如果草稿输出格式一开始不统一，后面会很难解析。

### 5. 先保留兼容，再逐步替换

如果你要从旧探究流迁移到新 agent 体系，建议先并存：

- 新流程先加到 `FLOW_TEMPLATES`
- 新 agent 先加到 `dify_stage_agents()`
- 新 prompt 先单独接

等稳定后，再考虑替换旧流程。

---

## 十、最小修改清单

如果你现在就要开始做一套全新的子 agent 体系，最小修改清单通常是：

1. 在 `app/workflow/flows.py` 新增 `FLOW_TEMPLATES` 条目
2. 为新流程重写 `STAGE_DIRECTIONS`
3. 在 `app/core/config.py` 的 `dify_stage_agents()` 里注册新 agent
4. 在 `app/services/prompt_service.py` 重写主流程与阶段 prompt
5. 在 `app/api/chat.py` 接入新的路由和写回逻辑
6. 根据需要调整 `context_service.py` 和 `draft_service.py`
7. 更新前端展示和测试用例

---

## 十一、结论

如果你要做“完全不同的一套子 agent 角色体系”，不是单独改一个文件就行，而是要把：

- **流程定义**
- **角色注册**
- **提示词**
- **消息路由**
- **上下文记忆**
- **草稿结构**

这几层一起改。

最核心的三个文件是：

- `app/workflow/flows.py`
- `app/core/config.py`
- `app/services/prompt_service.py`

而 `app/api/chat.py` 是把这些层真正串起来的地方。
