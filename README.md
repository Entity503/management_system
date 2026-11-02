# 计算机俱乐部社团管理系统

一个基于 Django 的计算机俱乐部综合管理平台，集成了星空主题 UI、用户社区、学习资料、刷题系统、活动管理和 AI 智能体。适合作为计算机类社团的内部协作、学习与活动管理工具。

---

## ✨ 亮点特性

- 🌌 **真实星空馆**：5044 颗恒星 + 88 星座（真实赤经赤纬投影），可拖拽 / 缩放探索，单击流星雨、星座科普、待机自转与纯净模式
- 🔐 **QQ 邮箱验证码注册**：60 秒频控、10 分钟有效期，SMTP 授权码安全发送
- 👤 **完整用户资料**：昵称 / 头像 / 学号 / 专业 / 年级 / 技能标签 / 积分
- 📚 **学习资料中心**：分类筛选、Markdown + 代码高亮、下载统计、权限可见性（公开 / 成员 / 管理员）
- 🧠 **刷题平台**：7 种题型（单选 / 多选 / 判断 / 填空 / 简答 / 综合 / 代码）、3 级难度、答题判分、错题记录、用户出题审核
- 🎯 **活动系统**：报名 / 签到 / 状态流转（草稿 → 报名中 → 已截止 → 已结束）、人数上限与候补
- 📢 **公告发布**：置顶、分类、Markdown 渲染、管理员 CRUD
- 🤖 **多智能体 AI 助手**：6 种角色 + 多会话 + 上下文记忆 + 配额管理，DeepSeek / 阿里云百炼双通道自动回退
- 🧾 **AI 建稿工作台**：运营助手把一句话需求转成题目 / 公告 / 活动草稿，**必须由本人点「确认发布」才落库**，全程可审计
- ⏰ **主动巡检 Agent**：定时扫描即将开始 / 报名即将截止的活动，自动生成提醒公告草稿（7 天去重、失败回退模板），无需人工触发
- 💬 **通用评论系统**：基于 Django ContentType 的 GenericForeignKey，支持活动 / 公告 / 题目 / 资料四种实体
- 🛠️ **管理员后台**：成员管理（Staff 开关与用户删除）、AI 配额调整、Django Admin 全模型操作

---

## 🧩 功能架构

### 模块一览

| 模块 | 主要功能 |
|------|----------|
| **认证** | 邮箱验证码注册、密码登录 / 退出、Session 管理 |
| **资料** | 分类浏览、上传（单文件不超过 1GB）、Markdown 编辑（EasyMDE）、下载、删除 |
| **刷题** | 题目列表筛选、答题判分、用户出题、错题记录、Markdown 解析 |
| **AI** | 多会话、6 种角色、Token 统计、每日配额、双通道 Provider 回退 |
| **AI 建稿** | 运营助手生成题目 / 公告 / 活动草稿 → 本人确认后发布 → 审计日志 |
| **主动巡检** | 定时扫描 24 小时内的活动 / 报名截止，自动生成提醒草稿（去重 + 审计） |
| **星空馆** | 真实星表渲染、拖拽 / 缩放、流星雨、星座信息卡、待机自转、纯净模式 |
| **活动** | 创建 / 编辑 / 删除、报名 / 取消 / 候补、签到、状态管理 |
| **公告** | 发布 / 编辑 / 删除、置顶、分类筛选 |
| **评论** | 通用评论（活动 / 公告 / 题目 / 资料）、删除（作者 / 管理员） |
| **管理后台** | 成员 Staff 权限切换、超级管理员删除用户、AI 配额调整 |
| **资料分类** | 10 个内置分类：数据结构 / 计组 / 网络 / 操作系统 / C++ / Java / Python / MySQL / 离散数学 / 其它 |

资料上传单个文件大小上限为 **1 GB**，后端会强制校验；部署平台还必须允许相应大小的请求体，否则需要同时调整平台或 Web 服务器的上传限制。

### 6 种 AI 智能体

| 角色 | agent_type | 能用工具做什么 | 典型场景 |
|------|-----------|----------------|----------|
| 社团助手 | `club_assistant` | 查活动 / 公告 / 题目 / 资料 / 统计 | 新手指引、按真实数据回答"最近有什么活动" |
| 学习教练 | `study_coach` | 查资料库、题库；保存学习计划 | 按年级 / 专业定制学习路径 |
| 题目答疑 | `problem_tutor` | 搜题 / 取题 / 查我的错题 / 出题入库 | 解题思路、复杂度分析、错题复盘 |
| 代码评审 | `code_review` | 流式评审；保存评审记录 | Bug / 性能 / 可读性 / 风格多维点评 |
| 面试模拟 | `interview` | 有状态面试 + 逐题评分 + 报告页 | 算法 / 八股 / 项目 / 系统设计面试 |
| 运营助手 | `ops_assistant` | 8 个工具：查询 + 建稿 | 一句话生成题目 / 公告 / 活动草稿，确认后发布 |

> 智能体的中文名、说明、示例、System Prompt、**工具白名单**统一维护在 `club/agents.py`，
> 新增智能体只需改这一个文件 + 生成迁移；`agent_runner` 会按白名单过滤工具。
>
> 挂工具的智能体（社团助手 / 题目答疑 / 学习教练）走多轮工具循环，输出为一次性；
> 代码评审 / 面试模拟保持逐字流式。

### 7 种题型

单选 · 多选 · 判断 · 填空 · 简答 · 综合 · 代码

---

## 🗂️ 项目结构

```text
management_system/
├── manage.py
├── management_system/
│   ├── settings.py          # 环境变量、数据库、邮件、静态文件配置
│   ├── urls.py              # 项目级路由（Django Admin 路径 /django-admin/）
│   ├── asgi.py              # ASGI 入口
│   └── wsgi.py              # WSGI 入口
├── club/                    # 核心业务应用
│   ├── agents.py            # 智能体注册表（名称 / 说明 / 示例 / Prompt）
│   ├── ai_service.py        # AI Provider 封装 + 统一调用入口
│   ├── models/              # 数据模型子包
│   │   ├── __init__.py      #   统一 re-export
│   │   ├── user.py          #   UserProfile
│   │   ├── resources.py     #   Resource / ResourceCategory / Tag
│   │   ├── problems.py      #   Problem / Submission / ProblemOption
│   │   ├── activities.py    #   Activity / ActivitySignup
│   │   ├── announcements.py #   Announcement
│   │   ├── comments.py      #   Comment（GenericForeignKey）
│   │   ├── ai.py            #   AIConversation / AIMessage / AIQuota
│   │   ├── ai_actions.py    #   AIDraft / AIActionLog（草稿 + 审计）
│   │   ├── artifacts.py     #   AgentArtifact（学习计划 / 评审记录）
│   │   └── interviews.py    #   InterviewSession / InterviewTurn
│   ├── forms/               # Django Form 子包
│   │   ├── __init__.py
│   │   ├── auth.py          #   RegisterForm / LoginForm / ProfileForm
│   │   ├── resources.py     #   ResourceForm
│   │   ├── problems.py      #   ProblemForm
│   │   ├── ai.py            #   AnnouncementDraftForm（草稿编辑）
│   │   └── activities.py    #   ActivityForm
│   ├── services/            # 服务层（跨视图复用）
│   │   ├── ai_actions.py    #   草稿解析 / 校验 / 权限 / 落库 / 审计
│   │   ├── ai_tools.py      #   function calling 工具（查询 + 建稿）
│   │   ├── agent_runner.py  #   多轮工具调用循环（最多 3 轮）
│   │   ├── proactive.py     #   主动巡检 Agent（规则 + 去重 + 生成草稿）
│   │   └── platform_context.py # 平台快照，注入 System Prompt
│   ├── management/commands/
│   │   └── proactive_agent.py   # 定时命令：python manage.py proactive_agent
│   ├── tests/               # 测试（草稿 / 工具 / 流式 / 体验 / 服务 / 主动巡检，101 个用例）
│   ├── views/               # 视图子包（按业务域拆分）
│   │   ├── __init__.py      #   统一 re-export（外部 import 完全兼容原 views.py）
│   │   ├── auth.py          #   注册 / 登录 / 退出 / 个人资料
│   │   ├── dashboard.py     #   首页工作台
│   │   ├── resources.py     #   学习资料（列表 / 详情 / 上传 / 下载 / 删除）
│   │   ├── activities.py    #   活动（列表 / 详情 / CRUD / 状态切换 / STAFF_REQUIRED）
│   │   ├── problems.py      #   刷题（列表 / 详情 + 判分 / 出题 / CRUD）
│   │   ├── ai.py            #   AI 对话 / 工具型智能体 / 草稿 / 产出物 / 面试
│   │   ├── admin.py         #   管理员后台（成员 / AI 配额）
│   │   ├── announcements.py  #   公告（列表 / 详情 / CRUD）
│   │   └── comments.py      #   通用评论（_inject_comments 被 4 个详情页共用）
│   ├── urls.py              # club 应用路由（app_name='club'）
│   ├── admin.py             # Django Admin 注册配置
│   └── migrations/          # 数据库迁移 + 初始分类种子数据
├── templates/               # Django 模板（继承 base.html）
│   ├── base.html            # 基础布局（固定导航栏 / 星空 canvas / 星座信息卡）
│   └── club/                # 业务模板
│       ├── dashboard.html           # 首页工作台 + 快捷入口
│       ├── profile.html              # 个人资料
│       ├── resources.html            # 资料列表
│       ├── resource_upload.html      # 上传资料（EasyMDE）
│       ├── resource_detail.html      # 资料详情 + 评论
│       ├── practice.html             # 题目列表
│       ├── problem_detail.html       # 答题 + 判分 + 评论
│       ├── problem_create.html       # 用户出题
│       ├── ai_chat.html              # AI 对话界面（含草稿卡片）
│       ├── ai_drafts.html            # AI 草稿箱
│       ├── ai_artifacts.html         # 我的 AI 产出（学习计划 / 评审）
│       ├── ai_interviews.html        # 模拟面试列表 + 新建
│       ├── ai_interview_detail.html  # 面试报告（总分 / 逐题点评）
│       ├── activity_list.html        # 活动列表
│       ├── activity_detail.html      # 活动详情 + 报名 + 评论
│       ├── announcement_list.html    # 公告列表
│       ├── announcement_detail.html  # 公告详情 + 评论
│       ├── admin_users.html          # 管理员 - 成员管理
│       └── admin_quotas.html         # 管理员 - AI 配额
├── static/
│   ├── css/site.css         # 全局星空主题样式（CSS Variables / 玻璃态 / 响应式）
│   ├── sky/                 # 星空馆：sky.json（星表 + 星座）、sky.js（渲染与交互）
│   ├── js/stars.js          # 旧版程序化星空（已被 static/sky/sky.js 取代）
│   ├── bootstrap5/          # Bootstrap 5 本地副本
│   └── highlight/           # highlight.js 代码高亮（185 种语言）
├── scripts/                 # 数据构建
│   ├── build_sky_data.py    # 把原始星表压成 static/sky/sky.json
│   └── data/                # 原始星表与星座简介（不参与部署）
├── docs/                    # 设计与运维文档
│   ├── AI_AGENT_UPGRADE_PLAN.md
│   ├── PROACTIVE_AGENT.md
│   └── SKY_BACKGROUND.md
├── media/                   # 用户上传文件（avatars / resources）
├── .env.example             # 环境变量示例
├── requirements.txt         # Python 依赖
└── README.md
```

---

## 🛠️ 技术栈

| 分类 | 技术 |
|------|------|
| **后端** | Django 5.2 LTS · Django ORM · GenericForeignKey |
| **数据库** | MySQL 8（生产）· SQLite（开发测试） |
| **前端** | Django Templates · CSS Variables · backdrop-filter 玻璃态 · Canvas 2D 球极投影星图 |
| **Markdown** | EasyMDE 富文本编辑器 · Python `markdown` 库 + highlight.js |
| **AI** | DeepSeek API · 阿里云百炼 API · requests SDK |
| **邮件** | QQ SMTP（授权码）· 控制台后端（开发模式） |
| **其他** | Pillow（图像处理）· python-dotenv（环境变量） |

---

## 📋 环境要求

- Python 3.12 或兼容版本
- Django 5.2.x（5.2 LTS）
- MySQL 8（生产环境），字符集建议 `utf8mb4`
- 可选：DeepSeek API Key / 阿里云百炼 API Key（至少配置一个才能使用 AI 功能）
- 可选：QQ 邮箱（用于验证码发送）

---

## 🚀 快速开始

### 1. 克隆与虚拟环境

```powershell
# PowerShell
git clone <your-repo-url>
cd management_system

python -m venv venv
.\venv\Scripts\Activate.ps1

# 如果 PowerShell 禁止脚本执行
Set-ExecutionPolicy -Scope Process Bypass
```

### 2. 安装依赖

```powershell
pip install -r requirements.txt
```

### 3. 配置环境变量

```powershell
Copy-Item .env.example .env
```

编辑 `.env` 文件：

```dotenv
# 必须修改
DJANGO_SECRET_KEY=请替换为随机密钥
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

# 数据库（生产用 MySQL；开发可临时用 SQLite，见下文）
MYSQL_DATABASE=management_system
MYSQL_USER=root
MYSQL_PASSWORD=你的MySQL密码
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306

# AI（至少配一个）
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
BAILIAN_API_KEY=your-bailian-key

# 唯一的超级管理员（username 与此邮箱一致，在管理员后台拥有全部权限）
SUPER_ADMIN_EMAIL=your-super-admin@example.com

# 邮箱验证码（开发未配置时会打印到终端）
QQ_EMAIL_HOST=smtp.qq.com
QQ_EMAIL_PORT=465
QQ_EMAIL_USER=your-qq-number@qq.com
QQ_EMAIL_PASSWORD=QQ邮箱SMTP授权码
```

> 💡 **临时用 SQLite**：如果 MySQL 还没装好，运行 `$env:DJANGO_USE_SQLITE="True"` 即可让 settings.py 切换到 SQLite。

### 4. 数据库初始化

```powershell
python manage.py check
python manage.py migrate
```

首次 migrate 会自动创建所有表，并在 `0003_seed_resource_categories` 迁移里写入 10 个内置资料分类。

### 5. 创建管理员

```powershell
python manage.py createsuperuser
```

### 6. 启动开发服务器

```powershell
python manage.py runserver
```

访问 <http://127.0.0.1:8000/> 即可看到星空首页。

---

## 📑 页面速查

| 页面 | 地址 | 权限 |
|------|------|------|
| 首页工作台 | `/` | 公开 |
| 注册 | `/register/` | 公开 |
| 登录 | `/login/` | 公开 |
| 个人资料 | `/profile/` | 登录 |
| 资料列表 | `/resources/` | 登录 |
| 上传资料 | `/resources/upload/` | 登录 |
| 刷题中心 | `/practice/` | 登录 |
| 题目详情 / 答题 | `/practice/<id>/` | 登录 |
| 用户出题 | `/practice/create/` | 登录 |
| AI 助手（新建会话） | `/ai/` | 登录 |
| AI 助手（继续会话） | `/ai/<conversation_id>/` | 登录 |
| AI 草稿箱 | `/ai/drafts/` | 登录（只能看/确认自己的草稿） |
| 我的 AI 产出 | `/ai/artifacts/` | 登录（学习计划 / 评审记录） |
| 模拟面试 | `/ai/interviews/` | 登录（新建 / 历史报告） |
| 活动列表 | `/activities/` | 登录 |
| 活动详情 | `/activities/<id>/` | 登录 |
| 公告列表 | `/announcements/` | 公开 |
| 公告详情 | `/announcements/<id>/` | 公开 |
| 管理员 - 成员管理 | `/admin/users/` | Staff（删除用户仅超级管理员） |
| 管理员 - AI 配额 | `/admin/quotas/` | **超管**（SUPER_ADMIN_EMAIL） |
| Django Admin | `/django-admin/` | Superuser |

---

## 🎨 UI 主题说明

前端采用 **CSS Variables** + **Canvas 绘制** 的纯 CSS/JS 方案，不依赖 UI 框架：

```css
:root {
    --paper: #0b0d1a;        /* 主背景（深空蓝） */
    --ink: #e8eaf2;          /* 主文字 */
    --muted: #8b90a8;        /* 次要文字 */
    --glow: #6b8cff;         /* 星蓝 */
    --coral: #ff765f;        /* 珊瑚橙 */
    --panel: rgba(16, 20, 40, 0.55); /* 玻璃面板 */
    --line: rgba(255,255,255,0.08);  /* 分隔线 */
}
```

`static/sky/sky.js` 实现真实星表渲染（球极投影）、拖拽平移、缩放、流星雨与星座信息卡；详见下方「星空馆」。导航栏使用 `position: fixed` + `backdrop-filter: blur(18px)` 实现固定在顶部的磨砂玻璃效果。

---

## 🌌 星空馆

背景不是随机撒点，而是按**真实赤经赤纬**投影的星空：

| 项目 | 数据 |
|------|------|
| 恒星 | 5044 颗（星等 ≤ 6，含 B−V 色指数），来自 HYG Database |
| 星座 | 88 个、743 条连线，来自 d3-celestial（BSD-3） |
| 中文名 | 统一为简体标准星座名 |
| 简介 | 88 条本地撰写科普文案（不依赖外部 API） |
| 体积 | `sky.json` 159 KB（gzip 54 KB），同源加载 |

### 交互

| 操作 | 效果 |
|------|------|
| 拖拽 | 平移天球 |
| Ctrl / ⌘ + 滚轮 | 缩放（视场 20°–140°） |
| 双击 | 复位 |
| 单击空白 | 召唤流星雨 |
| 单击星座 | 弹出信息卡（中英文名 / 坐标 / 主要亮星 / 简介） |
| **S** | 进入 / 退出纯净模式（只留星空） |
| **Esc** | 关闭信息卡；再按退出纯净模式 |

### 可调节项

HUD 上三个按钮循环切换，档位存 `localStorage`：

- **自转**：关 / 慢 0.4°/s / 中 1.5°/s / 快 4°/s（停手 3.5 秒后启动）
- **流星**：关 / 低 70–150s / 中 30–70s / 高 12–30s（随机位置与规模）
- **纯净**：隐藏导航与正文，仅保留星空

### 性能策略

- 星点只在视角变化时重绘；流星画在独立 `#sky-fx` 图层，不触发星空重绘
- 低端机（`deviceMemory ≤ 4` 或 `hardwareConcurrency ≤ 4`）自动降星等、限制 DPR 与帧率
- 尊重 `prefers-reduced-motion`（不生成环境流星）

### 重新生成星表数据

```powershell
python scripts/build_sky_data.py
```

> 原始星表放在 `scripts/data/`（不参与部署），生成物 `static/sky/sky.json` 请勿手改。
> 数据来源与许可见 [docs/SKY_BACKGROUND.md](docs/SKY_BACKGROUND.md)。

---

## 🤖 AI 功能说明

### Provider 回退链

```
用户请求
  └─ club/ai_service.py
       ├─ 先尝试 DeepSeek (DEEPSEEK_API_KEY)
       ├─ 失败自动回退到阿里云百炼 (BAILIAN_API_KEY)
       └─ 都未配置 → 返回友好错误提示，不崩溃
```

### 配额机制

每个用户绑定 `AIQuota`，可在管理员后台 `/admin/quotas/` 调整：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `max_conversations_per_day` | 10 | 每日新建会话上限 |
| `max_requests_per_day` | 5 | 每日实际调用 AI 上限 |
| `max_conversation_size_mb` | 64 | 单个会话体积上限 |
| `total_conversations` | — | 累计会话数（只读） |
| `total_tokens_used` | — | 累计消耗 Token（只读） |

AI 接口仅允许登录用户访问，并限制单条消息长度和请求频率。删除会话不会恢复当天已经消耗的 AI 请求次数。

### 对话流程

1. 用户选择智能体角色 → 创建新会话
2. System Prompt 预置角色定义，并附带一段【平台当前状态】快照（公告 / 活动 / 题库 / 分类）
3. 只把最近 12 条历史 + 本轮问题发给模型，避免上下文无限膨胀
4. 响应写入 `AIMessage` 表，记录模型名和 Token 用量
5. 前端渲染 Markdown + 代码高亮

### AI 建稿（运营助手）

```text
用户一句话
  → 运营助手多轮 function calling（最多 3 轮）
      ├─ 查询：search_activities / search_problems / search_resources / platform_stats
      └─ 建稿：draft_problem / draft_announcement / draft_activity
  → 建稿走 club/services/ai_actions.py 的 ModelForm 二次校验
  → AIDraft(status=pending)
  → 用户点「确认发布」
  → 事务内落库 + AIActionLog 审计
```

| 草稿类型 | 谁能确认发布 | 落库后状态 |
|----------|--------------|------------|
| 题目 | 任意登录用户（与 `/practice/create/` 一致） | 已发布 |
| 公告 | 管理员 | 已发布 |
| 活动 | 管理员 | 按草稿里的 status（默认草稿） |

设计要点：

- **AI 输出永远不可信**：字段必须过白名单 + ModelForm 校验，非法即拒绝，不猜
- **必须人工确认**：没有"全自动发布"开关，草稿只能由创建者本人在 `/ai/drafts/` 或对话框里确认
- **权限只在服务端判断**：提示词注入绕不过 `apply_draft()` 的检查
- **可审计**：每次生成 / 确认 / 丢弃都会写一条 `AIActionLog`
- 每人每天最多生成 20 条草稿（`MAX_DRAFTS_PER_DAY`），防止刷模型额度

### 工具调用与流式输出

| 能力 | 说明 |
|------|------|
| Function calling | 运营助手最多 3 轮工具调用，结果以 `role=tool` 回填后继续推理 |
| 工具白名单 | 只暴露 `search_*` / `platform_stats` / `draft_*`，参数用 JSON Schema 约束 |
| 权限 | 建稿工具在服务端校验权限，普通成员调 `draft_announcement` 会被拒绝并返回原因 |
| 流式 | `/ai/api/stream/` 用 SSE 逐字返回；前端在流不可用时自动回退到 `/ai/api/send/` |
| 轨迹 | 工具调用记录存进 `AIMessage.tool_calls`，刷新页面后仍能看到「查询活动 · 查到 3 场」这样的气泡 |

> 工具型智能体先跑完工具再输出文本（草稿场景本来就只有一两句话），
> 聊天型智能体则是真正的逐字流式。

### 智能体体验增强

| 能力 | 说明 |
|------|------|
| **讲解这题** | 题目详情页按钮 → 带题干/选项/参考答案建 `problem_tutor` 会话，要求先提示后给解法 |
| **资料问答** | 资料详情页按钮 → 带正文节选建 `study_coach` 会话 |
| **草稿编辑** | 确认发布前可修改标题/正文/时间/答案，保存后仍是草稿 |
| **重新生成** | 删掉最后一问一答，用同样的提问重跑 |
| **会话重命名** | 侧边栏 ✎ 图标 |
| **👍 / 👎 反馈** | 存在 `AIMessage.feedback`，为后续调 prompt 留数据 |
| **按智能体调温度** | 代码评审 0.2、面试 0.4、题目答疑 0.5、运营 0.3、教练/助手 0.7 |
| **输出消毒** | 前端 DOMPurify 过滤模型输出，防止提示词注入带出 `<script>` |

### 学习资产与面试报告

- **学习计划 / 评审记录**：在 `study_coach` / `code_review` 的回复下点「保存」，写入 `AgentArtifact`，在 `/ai/artifacts/` 回看
- **模拟面试**：`/ai/interviews/` 新建（方向 + 难度）→ 对话结束后点「结束并生成报告」→ 模型总结对话，落 `InterviewSession.score` 与逐题 `InterviewTurn`，报告页展示总分、逐题点评

### 主动巡检 Agent（定时任务）

不等人开口：定时扫描一次，把「需要提醒的事」变成待确认草稿。

| 规则 | 触发条件 | 产出 |
|------|----------|------|
| `activity-start` | 活动 24 小时内开始 | 「提醒：XX 即将开始」 |
| `activity-deadline` | 报名 24 小时内截止 | 「报名即将截止：XX」 |

- **去重**：`AIDraft.source_key` 保证同一活动 7 天内只提醒一次
- **归属**：优先活动组织者（管理员），否则回退超级管理员
- **文案**：模板兜底；配置了 API Key 时用 LLM 润色，模型失败自动回退模板
- **审计**：每次生成写 `AIActionLog(action='agent.proactive')`
- **命令**：`python manage.py proactive_agent --no-llm`，详见 [docs/PROACTIVE_AGENT.md](docs/PROACTIVE_AGENT.md)

---

## 📝 开发约定

1. **迁移**：修改模型 → `makemigrations` → `migrate`
2. **模板继承**：新页面优先继承 `base.html`，用 `{% block content %}` 和 `{% block extra_css %}` 注入
3. **全局样式**：写在 `static/css/site.css`，优先使用 CSS 变量保证主题一致性
4. **密钥安全**：密钥、密码、API Key、**超管邮箱**只写 `.env`，代码 / 模板 / README 均不出现明文；`.gitignore` 已排除 `.env` / `db.sqlite3` / `media/`
5. **真实姓名隐私**：普通用户只显示昵称；真实姓名仅 Admin 可见
6. **内容发布**：AI 建稿必须由创建者本人确认后才会落库；手工入口（出题 / 上传资料）仍是提交即生效，权限规则保持一致
7. **图片 / 文件上传**：必须保留表单校验，不能只依赖前端限制
8. **新增模块**：先保持在 `club/` 内实现，稳定后再考虑拆分应用
9. **星空数据**：改 `scripts/data/` 后运行 `python scripts/build_sky_data.py`，不要手改 `static/sky/sky.json`；星座简介写在 `scripts/data/constellation_info.json`

---

## 🔍 常用命令

```powershell
# 检查 Django 配置
python manage.py check

# 跑测试（SQLite 内存库，不会碰本地/线上数据）
$env:DJANGO_USE_SQLITE="True"; python manage.py test club.tests

# 编译检查所有 Python 文件
python -m compileall -q club management_system

# 查看迁移状态
python manage.py showmigrations

# 进入 Django Shell
python manage.py shell

# 创建超级用户
python manage.py createsuperuser

# 收集静态文件（生产环境）
python manage.py collectstatic --noinput

# 重新生成星空数据（修改 scripts/data/ 后）
python scripts/build_sky_data.py

# 主动巡检：生成活动提醒草稿（--dry-run 只看计划）
python manage.py proactive_agent --no-llm
```

---

## 📦 依赖清单

```
Django>=5.2,<6.0
python-dotenv>=1.0,<2.0
djangorestframework>=3.15,<4.0
mysqlclient>=2.2,<3.0
Pillow>=10.0,<13.0
markdown>=3.5,<4.0
requests>=2.31,<3.0
resend>=2.0,<3.0
```

---

## 🏗️ 后续规划

- ✅ QQ 邮箱验证码注册
- ✅ 用户资料系统
- ✅ 学习资料（分类 / 上传 / 下载 / Markdown）
- ✅ 完整刷题模块（7 种题型 / 用户出题 / 审核发布）
- ✅ 活动报名 / 签到 / 状态管理
- ✅ 公告发布与分类
- ✅ 多智能体 AI 助手（6 种角色 / 双通道 Provider）
- ✅ AI 配额管理
- ✅ AI 建稿工作台（运营助手 + 草稿确认 + 审计）
- ✅ 主动巡检 Agent（活动提醒 / 去重 / 定时任务）
- ✅ 多角色 Agent 工具化（社团助手 / 题目答疑 / 学习教练）
- ✅ 学习资产（学习计划 / 评审记录）与模拟面试报告
- ✅ 平台快照注入（AI 知道社团当前有什么）
- ✅ AI 体验增强（讲解这题 / 草稿编辑 / 重新生成 / 反馈 / 流式）
- ✅ 通用评论系统
- ✅ 星空馆（真实星表 + 88 星座 + 拖拽探索 + 星座科普）
- ✅ 管理员后台
- ⬜ RAG 资料问答
- ⬜ DRF REST API
- ⬜ Celery + Redis 异步任务（邮件 / AI 流式）
- ⬜ Docker 沙箱判题
- ⬜ Nginx + HTTPS + 日志 + 备份
- ⬜ CI/CD 流水线

---

## 📄 License

MIT License