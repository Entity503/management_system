# 计算机俱乐部社团管理系统

一个基于 Django 的计算机俱乐部综合管理平台，集成了星空主题 UI、用户社区、学习资料、刷题系统、活动管理和 AI 智能体。适合作为计算机类社团的内部协作、学习与活动管理工具。

---

## ✨ 亮点特性

- 🌌 **星空主题界面**：深色渐变背景 + Canvas 动态星空 + 流星 + 鼠标点击粒子爆发特效，玻璃态磨砂导航栏
- 🔐 **QQ 邮箱验证码注册**：60 秒频控、10 分钟有效期，SMTP 授权码安全发送
- 👤 **完整用户资料**：昵称 / 头像 / 学号 / 专业 / 年级 / 技能标签 / 积分
- 📚 **学习资料中心**：分类筛选、Markdown + 代码高亮、下载统计、权限可见性（公开 / 成员 / 管理员）
- 🧠 **刷题平台**：7 种题型（单选 / 多选 / 判断 / 填空 / 简答 / 综合 / 代码）、3 级难度、答题判分、错题记录、用户出题审核
- 🎯 **活动系统**：报名 / 签到 / 状态流转（草稿 → 报名中 → 已截止 → 已结束）、人数上限与候补
- 📢 **公告发布**：置顶、分类、Markdown 渲染、管理员 CRUD
- 🤖 **多智能体 AI 助手**：5 种角色 + 多会话 + 上下文记忆 + 配额管理，DeepSeek / 阿里云百炼双通道自动回退
- 💬 **通用评论系统**：基于 Django ContentType 的 GenericForeignKey，支持活动 / 公告 / 题目 / 资料四种实体
- 🛠️ **管理员后台**：成员管理（Staff 开关）、AI 配额调整、Django Admin 全模型操作

---

## 🧩 功能架构

### 模块一览

| 模块 | 主要功能 |
|------|----------|
| **认证** | 邮箱验证码注册、密码登录 / 退出、Session 管理 |
| **资料** | 分类浏览、上传、Markdown 编辑（EasyMDE）、下载、删除 |
| **刷题** | 题目列表筛选、答题判分、用户出题、错题记录、Markdown 解析 |
| **AI** | 多会话、5 种角色、Token 统计、每日配额、双通道 Provider 回退 |
| **活动** | 创建 / 编辑 / 删除、报名 / 取消 / 候补、签到、状态管理 |
| **公告** | 发布 / 编辑 / 删除、置顶、分类筛选 |
| **评论** | 通用评论（活动 / 公告 / 题目 / 资料）、删除（作者 / 管理员） |
| **管理后台** | 成员 Staff 权限切换、AI 配额调整 |
| **资料分类** | 10 个内置分类：数据结构 / 计组 / 网络 / 操作系统 / C++ / Java / Python / MySQL / 离散数学 / 其它 |

### 5 种 AI 智能体

| 角色 | agent_type | 典型场景 |
|------|-----------|----------|
| 社团助手 | `club_assistant` | 新手指引、功能介绍 |
| 学习教练 | `study_coach` | 按年级 / 专业定制学习路径 |
| 题目答疑 | `problem_tutor` | 解题思路、复杂度分析、代码示例 |
| 代码评审 | `code_review` | Bug / 性能 / 可读性 / 风格多维点评 |
| 面试模拟 | `interview` | 算法 / 八股 / 项目 / 系统设计面试 + 评分 |

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
│   ├── ai_service.py        # AI Provider 封装 + 5 种智能体 System Prompt
│   ├── models/              # 数据模型子包
│   │   ├── __init__.py      #   统一 re-export
│   │   ├── users.py         #   UserProfile / Skill
│   │   ├── resources.py     #   Resource / ResourceCategory / Tag
│   │   ├── problems.py      #   Problem / Submission（含 GenericForeignKey 注释）
│   │   ├── activities.py    #   Activity / ActivitySignup
│   │   ├── announcements.py #   Announcement
│   │   ├── comments.py      #   Comment（GenericForeignKey + 防 XSS）
│   │   └── ai.py            #   AIConversation / AIMessage / AIQuota
│   ├── forms/               # Django Form 子包
│   │   ├── __init__.py
│   │   ├── auth.py          #   RegisterForm / LoginForm / ProfileForm
│   │   ├── resources.py     #   ResourceForm
│   │   ├── problems.py      #   ProblemForm
│   │   └── activities.py    #   ActivityForm
│   ├── views/               # 视图子包（按业务域拆分）
│   │   ├── __init__.py      #   统一 re-export（外部 import 完全兼容原 views.py）
│   │   ├── auth.py          #   注册 / 登录 / 退出 / 个人资料
│   │   ├── dashboard.py     #   首页工作台
│   │   ├── resources.py     #   学习资料（列表 / 详情 / 上传 / 下载 / 删除）
│   │   ├── activities.py    #   活动（列表 / 详情 / CRUD / 状态切换 / STAFF_REQUIRED）
│   │   ├── problems.py      #   刷题（列表 / 详情 + 判分 / 出题 / CRUD）
│   │   ├── ai.py            #   AI 对话 + 配额系统 + SUPER_ADMIN_EMAIL + 辅助函数
│   │   ├── admin.py         #   管理员后台（成员 / AI 配额）
│   │   ├── announcements.py  #   公告（列表 / 详情 / CRUD）
│   │   └── comments.py      #   通用评论（_inject_comments 被 4 个详情页共用）
│   ├── urls.py              # club 应用路由（app_name='club'）
│   ├── admin.py             # Django Admin 注册配置
│   └── migrations/          # 数据库迁移 + 初始分类种子数据
├── templates/               # Django 模板（继承 base.html）
│   ├── base.html            # 基础布局（导航栏 / 星空 canvas / 粒子特效脚本）
│   └── club/                # 业务模板
│       ├── dashboard.html           # 首页工作台 + 快捷入口
│       ├── profile.html              # 个人资料
│       ├── resources.html            # 资料列表
│       ├── resource_upload.html      # 上传资料（EasyMDE）
│       ├── resource_detail.html      # 资料详情 + 评论
│       ├── practice.html             # 题目列表
│       ├── problem_detail.html       # 答题 + 判分 + 评论
│       ├── problem_create.html       # 用户出题
│       ├── ai_chat.html              # AI 对话界面
│       ├── activity_list.html        # 活动列表
│       ├── activity_detail.html      # 活动详情 + 报名 + 评论
│       ├── announcement_list.html    # 公告列表
│       ├── announcement_detail.html  # 公告详情 + 评论
│       ├── admin_users.html          # 管理员 - 成员管理
│       └── admin_quotas.html         # 管理员 - AI 配额
├── static/
│   ├── css/site.css         # 全局星空主题样式（CSS Variables / 玻璃态 / 响应式）
│   ├── js/stars.js          # Canvas 动态星空 + 流星 + 鼠标视差 + 点击粒子爆发
│   ├── bootstrap5/          # Bootstrap 5 本地副本
│   └── highlight/           # highlight.js 代码高亮（185 种语言）
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
| **前端** | Django Templates · CSS Variables · backdrop-filter 玻璃态 · Canvas API |
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
| 活动列表 | `/activities/` | 登录 |
| 活动详情 | `/activities/<id>/` | 登录 |
| 公告列表 | `/announcements/` | 公开 |
| 公告详情 | `/announcements/<id>/` | 公开 |
| 管理员 - 成员管理 | `/admin/users/` | Staff |
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

`static/js/stars.js` 实现三层视差星空、流星动画、鼠标移动视差、点击粒子爆发（多色物理模拟）。导航栏和面板使用 `backdrop-filter: blur(14px)` 实现磨砂玻璃效果。

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
2. System Prompt 预置角色定义
3. 上下文历史通过 Django ORM 拼接发送
4. 响应流式写入 `AIMessage` 表，记录模型名和 Token 用量
5. 前端渲染 Markdown + 代码高亮

---

## 📝 开发约定

1. **迁移**：修改模型 → `makemigrations` → `migrate`
2. **模板继承**：新页面优先继承 `base.html`，用 `{% block content %}` 和 `{% block extra_css %}` 注入
3. **全局样式**：写在 `static/css/site.css`，优先使用 CSS 变量保证主题一致性
4. **密钥安全**：密钥、密码、API Key、**超管邮箱**只写 `.env`，代码 / 模板 / README 均不出现明文；`.gitignore` 已排除 `.env` / `db.sqlite3` / `media/`
5. **真实姓名隐私**：普通用户只显示昵称；真实姓名仅 Admin 可见
6. **出题审核**：用户提交的题目默认 `is_published=False`，管理员在 Django Admin 里审核发布
7. **图片 / 文件上传**：必须保留表单校验，不能只依赖前端限制
8. **新增模块**：先保持在 `club/` 内实现，稳定后再考虑拆分应用

---

## 🔍 常用命令

```powershell
# 检查 Django 配置
python manage.py check

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
- ✅ 多智能体 AI 助手（5 种角色 / 双通道 Provider）
- ✅ AI 配额管理
- ✅ 通用评论系统
- ✅ 星空主题 UI + 粒子特效
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