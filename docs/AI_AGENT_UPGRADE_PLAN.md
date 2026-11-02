# AI Agent 升级方案（待评估）

> 基线：`main` @ `02e0189`，备份见文末「回滚方案」。
> 本文只列方案，不改代码。评估通过后再按阶段实施。

---

## 一、现状诊断：为什么现在"呆呆的"

结论：**不是模型不行，是架构上它被"关在对话框里"了。** 六个具体原因，都能在代码里对上号。

| # | 原因 | 代码证据 |
|---|------|----------|
| 1 | **看不到平台数据** | `AGENT_PROMPTS` 里只有角色设定，没有任何公告/活动/题目/资料内容；问"这周有什么活动"只能编或让用户自己去看 |
| 2 | **没有任何工具** | `ai_service.chat()` 是单次 `requests.post`，`stream=False`，无 function calling；AI 只能输出文字，无法写入数据库 |
| 3 | **上下文无限堆叠、无摘要** | `ai_api_send` 每次把 `conversation.messages.all()` 全量重发；`max_conversation_size_mb=64`（按字节算）实际上永远触发不了，真到模型上下文上限时直接报错 |
| 4 | **输出不可结构化** | 全是自由 Markdown，无法沉淀成 `Problem` / `Announcement` / `Activity` 实体 |
| 5 | **交互体验弱** | 无流式（要等 60 秒超时上限）、无预设问题、无"重新生成"、无引用溯源；错误直接把异常字符串塞给用户（`⚠️ AI 暂时无法回复：{e}`） |
| 6 | **配额逻辑不区分场景** | 只按"每日请求数"卡（默认 5 次），聊天和"执行任务"混在一个额度里 |

另外两个结构性小问题：

- `AIConversation.AGENT_CHOICES`（模型层）和 `AGENT_PROMPTS`（服务层）是两份重复清单，新增智能体要改两处 + 做迁移；
- 没有任何"AI 写了什么东西"的审计记录，一旦开放写操作，出问题无法追溯。

**好消息**：这份代码的底子适合加工具——`forms/` 里的校验逻辑可直接复用，`views/` 里权限判断已有固定写法（`is_staff` / `== created_by` / `SUPER_ADMIN_EMAIL`），服务层 `ai_service.py` 是唯一出口。改造不需要推翻重来。

---

## 二、方案总览（四档，建议取 B 或 B+C）

| 方案 | 内容 | 新增能力 | 工时 | 风险 | 建议 |
|------|------|----------|------|------|------|
| **A 最小修补** | 平台数据注入 + 体验修补 | 回答变"懂业务"，但仍不能执行 | 0.5–1 天 | 极低 | 必做，作为底座 |
| **B 草稿工作台** | AI 输出结构化草稿 → 后端二次校验 → 人工点确认才落库 | **能发题目/公告/活动** | 1.5–2.5 天 | 低 | **推荐先做** |
| **C 工具调用 + 流式** | Function Calling 多轮、只读查询、SSE 打字机 | 能多步执行、能查数据 | +2–3 天 | 中 | 二阶段，视 B 效果 |
| **D 长期演进** | 审核流、审计、配额分档、面试状态机、RAG | 生产级运营 | 5 天+ | 中高 | 按需 |

**推荐路线：A → B → C**，D 里只先做"审计日志"（B 就应该带上）。

---

## 三、方案 A：先让它"懂业务"（0.5–1 天，无新模型、无迁移）

### A1. 平台快照注入系统提示词

在 `club/ai_service.py` 新增 `build_platform_context()`，查询少量数据拼进 system prompt：

```
【平台当前状态】（自动生成，用于回答事实性问题）
- 公告：共 3 条，最新《测试活动》(2026-09-15)；置顶 1 条
- 活动：即将开始 0 场；最近一场《测试活动》9/20 报名中
- 题库：6 道已发布题目，覆盖 5 个模块
- 资料：1 份，最新《xxx》
- 可用分类：数据结构 / 计算机组成原理 / ... / 其它
```

> 用 `django.db` 直接查，限制条数与字段，避免 token 膨胀；建议加 60 秒 `cache`，避免每次请求都查库。

### A2. 上下文裁剪与摘要

- 只带最近 **12 条**消息原文，更早的压成一段摘要（可先做"只保留最近 N 条 + 首条用户消息"的简化版，零成本）；
- `AIMessage` 增加 `summary_of` 或直接存一条 `role='system'` 的摘要消息，避免改表。

### A3. 体验修补（纯前端 + 小改动）

- 5 个智能体各自的 `description` + **4 个预设问题 chip**（点击直接发送）；
- 空会话页展示"智能体能做什么/不能做什么"，减少用户乱问；
- 生成失败时给可读提示，不外泄原始异常（`str(e)` 里可能含 API 地址/Key 片段）；
- 新增会话下拉里显示描述，而不只是名字。

### A4. 顺手修掉的 bug（与本次强相关）

- 配额日期口径统一为 `timezone.localdate()`（现在 `_enforce_ai_quota` 用 UTC 日期，凌晨 0–8 点会算错一天）；
- `AIConversation` 创建时校验 `agent_type` 合法性（现在任意字符串都能入库）。

**验收**：问"最近有什么公告""题库有多少题""这周有活动吗"，回答与首页数字一致，不再出现"请自行查看"式推脱。

---

## 四、方案 B：草稿工作台（推荐优先做，1.5–2.5 天）

### 核心思路

**AI 只负责"起草"，人负责"拍板"，服务端负责"校验"。** 三步：

```
用户：帮我出一道计算机网络的选择题，中等难度，问 TCP 三次握手，带解析
  ↓
AI：返回结构化 JSON（不是直接写库）
  ↓
后端：ModelForm 二次校验 → 存成 AIDraft(status=pending) → 前端弹"草稿卡片"
  ↓
用户：点「确认发布」→ 复用现有创建逻辑落库 → 卡片变成"已发布《...》→ 查看"
```

这样即使模型胡编字段，也只会变成"校验失败的草稿"，不会污染业务表。

### B1. 数据模型（1 个新表 + 1 次迁移）

```python
class AIDraft(TimeStampedModel):
    KIND_CHOICES = [('problem', '题目'), ('announcement', '公告'), ('activity', '活动')]
    STATUS_CHOICES = [('pending', '待确认'), ('applied', '已发布'),
                      ('discarded', '已丢弃'), ('failed', '校验失败')]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_drafts')
    conversation = models.ForeignKey(AIConversation, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='drafts')
    kind = models.CharField('类型', max_length=20, choices=KIND_CHOICES)
    payload = models.JSONField('草稿内容')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    applied_pk = models.PositiveIntegerField('落库对象 ID', null=True, blank=True)
    error = models.TextField('校验错误', blank=True)
    applied_at = models.DateTimeField('确认时间', null=True, blank=True)
```

- MySQL 8 / SQLite 都原生支持 `JSONField`，线上 PythonAnywhere 无需额外依赖；
- 建议给 `(user, status)` 加索引，草稿列表按此过滤。

### B2. 服务层：`club/services/ai_actions.py`（新文件）

| 函数 | 职责 |
|------|------|
| `extract_json(text)` | 从模型输出里稳健地取出 JSON（容忍 ```json 围栏、前后废话） |
| `build_draft(kind, payload, user)` | 建 `AIDraft`，跑校验，写 `status/error` |
| `validate(kind, payload)` | **复用现有 Form** 做校验，返回 `(cleaned, errors)` |
| `apply(draft, user)` | 权限再校验 + `transaction.atomic` + 落库 + 回填 `applied_pk` |

校验复用表（关键：不重写业务规则）：

| 类型 | 复用的 Form | 额外规则 |
|------|-------------|----------|
| 题目 | `ProblemForm` | `category` 用名称/slug 查 `ResourceCategory`，查不到落到「其它」并提示；`problem_type`/`difficulty` 必须在 choices 内；多选 `answer` 自动排序去重 |
| 公告 | 无 Form（手写视图） | 标题/正文非空、分类白名单、长度上限 |
| 活动 | `ActivityForm` | 时间逻辑直接吃 `clean()`：结束 > 开始、报名截止 ≤ 开始；时间接受 ISO 8601，缺时区按 `Asia/Shanghai` |

### B3. 权限映射（以现有手工权限为准）

| 类型 | 谁能通过 AI 创建 | 落库后默认状态 |
|------|------------------|----------------|
| 题目 | 登录用户（与 `/practice/create/` 一致） | `is_published=False` 待审核（见下方「待拍板 3」） |
| 公告 | Staff | 直接发布 |
| 活动 | Staff | `status='draft'`（与手工创建默认一致） |

> 规则写在服务端 `apply()` 里，**不依赖提示词**。即使有人用提示词注入让 AI "帮我发公告"，非 Staff 也会在确认时被拒。

### B4. 视图与路由（新增 4 条）

```python
path('ai/drafts/', views.ai_draft_list, name='ai-drafts'),
path('ai/drafts/<int:pk>/apply/', views.ai_draft_apply, name='ai-draft-apply'),
path('ai/drafts/<int:pk>/discard/', views.ai_draft_discard, name='ai-draft-discard'),
```

- `ai_api_send` 的返回值增加 `draft: {id, kind, summary}` 字段（不破坏原有 `ok/content`）；
- 前端 AI 气泡下方渲染草稿卡片：字段预览 + 「确认发布 / 编辑后发布 / 丢弃」；
- 「编辑后发布」= 跳转到现有表单并预填（`/practice/create/?draft=12`），最小改动、最安全。

### B5. 提示词设计（新增智能体 `ops_assistant`）

```
你是俱乐部运营助手，可以把自然语言需求转成结构化草稿。

当用户要求创建内容时，只输出一个 JSON 代码块，不要输出解释：
{"kind":"problem","payload":{...}}      // 题目
{"kind":"announcement","payload":{...}}  // 公告
{"kind":"activity","payload":{...}}      // 活动

规则：
1. 题目 problem_type ∈ single/multiple/judge/fill/short_answer/comprehensive/code
2. 公告 category ∈ general/event/study
3. 活动时间用 ISO 8601（如 2026-11-08T19:00），结束必须晚于开始
4. 缺关键信息时不要猜，先反问一句
5. 你不是发布者，落库需要用户确认
```

配合 few-shot 两条示例（一条成功、一条信息不足反问），可显著降低字段幻觉。

### B6. 审计（B 阶段就要有）

```python
class AIActionLog(models.Model):
    user, action（'draft.create'/'draft.apply'）, kind, target_pk,
    ok, detail（JSON：模型原始输出/校验错误）, duration_ms, created_at
```

用途：出问题能查"哪次 AI 操作、谁确认的、改了什么"；也方便后续做运营统计。

### 验收标准

1. "帮我发一条通知，说明本周六晚 7 点算法分享会，地点 A301" → 生成公告草稿 → 确认后出现在公告列表；
2. 非 Staff 说同样的话 → 草稿可生成，但点确认时报"无权发布公告"；
3. 故意给残缺信息（"帮我出个题"）→ AI 反问，而不是编一个空题；
4. 非法字段（`difficulty="地狱"`）→ 草稿标记 `failed` 并显示具体错误，不落库；
5. 所有写操作都有 `AIActionLog` 记录。

---

## 五、方案 C：工具调用 + 流式（B 之后，2–3 天）

### C1. Function Calling

- `call_deepseek(..., tools=TOOLS, tool_choice='auto')`，`ai_service` 增加多轮循环（最多 3 轮），
  每轮拿到 `tool_calls` → 服务端执行 → 以 `role='tool'` 回填；
- `AIMessage` 加 `tool_calls(JSONField)` + `tool_call_id`，前端渲染成"工具卡片"；
- 工具清单（先只读 + 草稿，**不给直接删除**）：

| 工具 | 作用 | 风险 |
|------|------|------|
| `search_activities(time_range, status)` | 回答"这周有什么活动" | 只读 |
| `search_problems(keyword, category, difficulty)` | 精确找题 | 只读 |
| `platform_stats()` | 给运营看统计 | 只读 |
| `draft_problem / draft_announcement / draft_activity` | 生成草稿（等价 B 阶段） | 需人确认 |
| `update_activity_status(id, status)` | 改活动状态 | Staff + 二次确认 |

- **配额**：一次用户请求最多 3 轮工具 = 记 1 次额度；另设"每日写操作上限"（建议 20 次）。
- **提示词注入防御**：模型只能调用白名单工具；每次调用前用 schema 校验参数；权限判断永远在服务端。

### C2. 流式输出（SSE）

- 新端点 `POST /ai/api/stream/`，`StreamingHttpResponse` + `text/event-stream`；
- `ai_service` 增加 `stream=True` 分支，逐块 `yield`；
- 前端用 `fetch` + `ReadableStream` 解析（`EventSource` 不支持 POST，别用）；
- 收益：首字延迟从"等 5–30 秒"变成 1 秒内，体感提升最大的一项；
- 注意：PythonAnywhere 上 WSGI 流式可用，但需关闭响应缓冲；失败要能回退到非流式。

### C3. 智能体注册表（消除重复）

`club/agents.py` 单一数据源：

```python
AGENTS = {
  'club_assistant': {'label': '社团助手', 'desc': '...', 'prompt': '...', 'tools': [], 'examples': [...]},
  ...
}
```

`AGENT_PROMPTS`、`AGENT_LABELS`、`AIConversation.AGENT_CHOICES` 全部由它派生（choices 用 `[(k, v['label']) for ...]`），以后加智能体只改一个文件（choices 变更仍需一次迁移，但不会再漏改）。

---

## 六、现有 5 个智能体的改造建议（逐个）

| 智能体 | 现状问题 | 改造动作 | 工作量 |
|--------|----------|----------|--------|
| **社团助手** | 只会介绍功能，不知道实际情况 | A1 平台快照 + A3 快捷问题 + 回答里带**站内链接**（"活动页：/activities/"） | 小 |
| **学习教练** | 每次重新问年级/专业，回答泛泛 | 从 `request.user.profile` 取年级/专业/技能自动注入；输出固定结构（阶段目标/周计划/资源/检验点）；v2 支持"保存为学习计划" | 小 |
| **题目答疑** | 不知道用户在看哪道题 | **在题目详情页加「AI 讲解」按钮**：带 `problem_id` 新建会话，把题干/选项/解析注入首条消息，要求"先给 1 级提示，答错再给 2 级，最后才给完整解法" | 中 |
| **代码评审** | 不知道语言，输出没结构 | prompt 要求固定三段（问题清单 + 严重级别 + 修复后代码）；自动识别语言；前端加"复制修改后代码"按钮 | 小 |
| **面试模拟** | 每轮自由发挥，没有评分沉淀 | 改造成状态机：选岗位/难度 → 逐题提问 → 每题给 1–10 分存 `AIScore` → 结束出报告；否则难以体现"面试" | 中 |

> 建议顺序：题目答疑的"讲解这题"性价比最高（一次改动、用户感知最强），其次是社团助手的数据注入。

---

## 七、需要你先拍板的 4 件事

1. **确认方式**：AI 生成后必须人工点确认（推荐），还是允许"完全自动发布"？
   - 全自动 = 需要更强的校验 + 审计 + 频率限制，风险高，不建议 v1 就开。
2. **AI 出的题目是否直接发布**：现在手工出题是"提交即发布"（`problem_create` 里写死 `is_published=True`），但模型注释/README 都说"需管理员审核"。
   - 建议：AI 出的题一律 `is_published=False` 进审核，同时**修掉**手工出题的矛盾（二选一，别两套）。
3. **给不给删除/修改权限**：建议 v1 只给"创建"，删除类操作永远人工。
4. **是否要流式**：做了体感提升明显，但涉及前端改动和新端点；如果只想要"能发东西"，可以先跳过。

---

## 八、实施顺序与工时（单人、熟悉本代码库）

| 阶段 | 内容 | 工时 | 交付物 |
|------|------|------|--------|
| 0 | 备份（已完成）+ A 阶段 | 0.5–1 天 | 提示词数据注入、快捷问题、3 个 bug 修复 |
| 1 | B 阶段：AIDraft + 运营助手 + 草稿页 + 审计 | 1.5–2.5 天 | 能通过对话发题目/公告/活动 |
| 2 | C 阶段：工具调用 + 只读查询 | 1–1.5 天 | 能查数据、多步操作 |
| 3 | C 阶段：流式输出 | 0.5–1 天 | 打字机体感 |
| 4 | 现有 5 个智能体逐个改造 | 1–1.5 天 | 见第六节 |

**最小可用组合：0 + 1（约 2–3 天）**，就能实现你想要的"描述需求 → 自动发题目/公告/活动"，且全程有人工确认兜底。

---

## 九、风险与对策

| 风险 | 对策 |
|------|------|
| 模型输出非法 JSON | `extract_json` + 一次自动重试 + 失败降级为"跳转预填表单" |
| 字段幻觉（分类、题型不存在） | 服务端白名单校验，非法即拒绝，不"猜" |
| 提示词注入绕过权限 | 权限只在服务端判断，AI 输出视为不可信输入 |
| 误发布/误删除 | 强制人工确认；v1 无删除能力；审计留痕 |
| Token 成本上升 | 上下文裁剪 + 快照缓存 + 单次请求轮数上限 |
| 线上迁移出错 | 本地先 `makemigrations` 生成迁移文件，服务器上 `migrate` 前先备份数据库 |

---

## 十、回滚方案（已执行）

- **代码快照**：`D:\PyCharm_IDEA\project\management_system_backups\management_system_code_20261102_211144.tar.gz`
  （1.24 MB / 747 个条目；包含 `club`、`templates`、`static`、`management_system`、`.env`、`db.sqlite3`；
  已做"解压 + SHA256 比对"校验，与当前工作区完全一致；`media`（227 MB 上传文件）未打包）
- **Git 标签**：`backup/pre-agent-20261102_211144`（指向 `02e0189`）
- 恢复方式：
  ```powershell
  # 方式一：只回滚代码
  tar -xzf D:\PyCharm_IDEA\project\management_system_backups\management_system_code_20261102_211144.tar.gz -C D:\PyCharm_IDEA\project
  # 方式二：用 git 回到基线（会丢弃之后的所有提交）
  git -C D:\PyCharm_IDEA\project\management_system checkout backup/pre-agent-20261102_211144
  ```
- 注意：`media/` 只有 `demo.txt` 等少量文件，且不含代码，回滚时无需还原。

---

## 十一、实施记录（A + B 已落地）

> 按决定执行：**所有发布都必须人工审核，审核权限 = 当前登录用户自己确认**。

### 已完成

| 计划项 | 落地内容 | 主要文件 |
|--------|----------|----------|
| A1 平台快照 | 公告 / 活动 / 题库 / 资料 / 分类 + 当前时间，60 秒缓存 | `club/services/platform_context.py` |
| A2 上下文裁剪 | 只发最近 12 条消息（`AI_HISTORY_LIMIT`） | `club/views/ai.py` |
| A3 体验 | 6 张智能体卡片、示例问题预填、错误提示不泄露异常 | `templates/club/ai_chat.html` |
| A4 修 bug | 配额日期统一 `localdate()`；agent_type 白名单校验 | `club/views/ai.py` |
| B1 模型 | `AIDraft` + `AIActionLog` + 迁移 0012 | `club/models/ai_actions.py` |
| B2 服务层 | JSON 提取、三类校验（复用 ModelForm）、落库、审计 | `club/services/ai_actions.py` |
| B3 权限 | 服务端判断，确认时二次校验 | 同上 |
| B4 视图 | 草稿箱 / 确认 / 丢弃 + AJAX | `club/views/ai.py`、`club/urls.py` |
| B5 提示词 | `ops_assistant` 只输出 JSON，信息不足就反问 | `club/agents.py` |
| B6 审计 | 生成 / 确认 / 丢弃全部落 `AIActionLog` | `club/services/ai_actions.py` |
| 注册表 | `AGENT_REGISTRY` 单一数据源，choices 由它派生 | `club/agents.py` |

### 与最初方案的差异

1. **题目不再走管理员审核**：本人确认即发布（按你的决定）。
2. **公告 / 活动仍要求管理员**（与手工入口一致）：普通成员让 AI 起草公告会收到"只有管理员可以发布"的提示。
   要放开只需把 `ai_actions.can_publish()` 里的 `ADMIN_ONLY_KINDS` 清空 / 改判断。
3. **未做"编辑后发布"**：当前只有「确认发布 / 丢弃」，要改内容就再跟 AI 说一句生成新草稿。
4. **C 阶段未做**：工具调用、流式输出、只读查询仍待评估。

### 验证结果

- `python manage.py check` → 0 issues
- `python manage.py makemigrations --check` → No changes detected
- `python manage.py test club.tests` → **34 passed**
- 迁移 `0012_ai_drafts_and_ops_assistant.py` 含 2 张新表 + 历史字段元数据对齐（后者只改 verbose_name/help_text，DB 层无实际变更）

### 上线步骤（PythonAnywhere）

```bash
git pull
python manage.py migrate        # 新增 club_aidraft / club_aiactionlog
# 重启 Web 应用
```

> 迁移只新增两张表，不改动已有表的数据；如需回滚，`migrate club 0011` 会删掉这两张表（草稿与日志会丢，业务数据不受影响）。

---

## 十二、C 阶段实施记录（工具调用 + 流式）

### 已完成

| 计划项 | 落地内容 | 主要文件 |
|--------|----------|----------|
| C1 Function calling | 运营助手最多 3 轮工具调用，`role=tool` 回填结果 | `club/services/agent_runner.py` |
| C1 工具集 | 7 个工具：4 个只读 + 3 个建稿 | `club/services/ai_tools.py` |
| C1 参数校验 | JSON Schema 约束 + 服务端归一化，非法参数不落库 | 同上 |
| C1 权限 | 建稿工具复用 `can_publish()`，普通成员发公告被拒 | 同上 |
| C2 流式 | `POST /ai/api/stream/`，SSE 事件：start / tool / delta / done / error | `club/views/ai.py` |
| C2 前端 | fetch + ReadableStream 解析，流不可用时自动回退到 `/ai/api/send/` | `templates/club/ai_chat.html` |
| C2 轨迹 | 工具调用记录存 `AIMessage.tool_calls`，刷新后仍可见 | `club/models/ai.py`、迁移 0013 |
| C3 注册表 | 早于 C 阶段完成的 `club/agents.py` 单一数据源 | `club/agents.py` |

### 工具清单

| 工具 | 类型 | 说明 |
|------|------|------|
| `search_activities` | 只读 | 按 upcoming / past / 天数 / 关键词查活动，自动排除草稿 |
| `search_problems` | 只读 | 按关键词 / 模块 / 难度查已发布题目 |
| `search_resources` | 只读 | 按关键词查学习资料 |
| `platform_stats` | 只读 | 成员、资料、题目、公告、活动数 |
| `draft_problem` | 写（草稿） | 生成题目草稿，本人确认后发布 |
| `draft_announcement` | 写（草稿） | 需管理员，生成公告草稿 |
| `draft_activity` | 写（草稿） | 需管理员，生成活动草稿 |

### 与方案的差异

1. **`update_activity_status` 未实现**：改状态属于"直接生效"的写操作，没有二次确认 UI，v1 不做。
2. **工具型智能体不是逐字流式**：多轮工具必须先跑完才能给文本，因此先执行再一次性推送；
   聊天型智能体是真正的逐字流式。
3. **流式 token 统计可能为 0**：Provider 未返回 usage 时按 0 记录（不影响请求次数配额）。
4. **DB 里历史消息只存最终文本 + 工具轨迹**，不回放 `tool_calls` 协议字段，避免上下文过长。

### 验证结果

- `python manage.py check` → 0 issues
- `python manage.py makemigrations --check` → No changes detected
- `python manage.py test club.tests` → **51 passed**
- 迁移 `0013_aimessage_tool_calls`：只给 `club_aimessage` 加一列 `tool_calls json`，已在本地 MySQL 应用

### 上线步骤

```bash
git pull
python manage.py migrate     # 新增 0013（加一列）
# 重启 Web 应用（流式响应需要服务器不缓冲 SSE）
```

> 如果线上用 PythonAnywhere，WSGI 默认支持流式；若发现一次性输出，检查反代是否缓冲，
> 代码里已设置 `X-Accel-Buffering: no`，前端也会自动回退到非流式接口。
