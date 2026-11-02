# 主动巡检 Agent

> 让系统在没人提问时也会「自己找活干」：巡检即将开始 / 即将截止报名的活动，自动生成提醒公告草稿，等人确认。

## 它和手动建稿的关系

共用同一条可信链路：

```
巡检（规则） → 生成文案（模板 / LLM） → AIDraft(source=proactive, pending)
             → 管理员在草稿箱点「确认发布」 → 事务落库 + 审计
```

Agent **不会自动发布**，所有产出仍然是 `pending` 草稿；权限、校验、审计与手动建稿完全一致。

## 触发规则

| 规则 | 条件 | 生成内容 |
|------|------|----------|
| `activity-start` | 活动 `status=published`，24 小时内开始 | 「提醒：XX 即将开始」，含时间、地点、报名人数、报名截止 |
| `activity-deadline` | 报名截止在 24 小时内，且活动尚未开始 | 「报名即将截止：XX」，含截止时间、当前人数 |

同一活动两条规则不会重复命中（先命中 start 就跳过 deadline）。

## 去重与归属

- **去重**：`source_key = activity-start:<id>` / `activity-deadline:<id>`，同一活动 **7 天内**只提醒一次（任何状态都算，包括已丢弃）
- **归属**：优先活动组织者（必须是管理员）；否则回退到 `SUPER_ADMIN_EMAIL`；都没有则跳过
- **审计**：每次生成写一条 `AIActionLog(action='agent.proactive')`

## 文案生成

1. 先用**确定性模板**保证一定有产出
2. 若配置了 `DEEPSEEK_API_KEY` / `BAILIAN_API_KEY`，再让模型基于真实事实润色（JSON 输出）
3. 模型失败 / 输出不合法 → **自动回退模板**，定时任务不会因为 API 抖动中断

## 命令

```bash
# 只看计划，不写库
python manage.py proactive_agent --dry-run --no-llm

# 真正生成草稿（有 API Key 时默认用 LLM 润色）
python manage.py proactive_agent

# 纯模板、不调用模型（推荐给定时任务，零成本）
python manage.py proactive_agent --no-llm

# 限制单次处理数量
python manage.py proactive_agent --limit 5
```

## 部署到 PythonAnywhere 定时任务

1. 打开 **Tasks** 标签 → 新建任务
2. 命令填（注意用**虚拟环境的 python 绝对路径**）：

```bash
/home/<你的用户名>/.virtualenvs/<环境名>/bin/python /home/<你的用户名>/management_system/manage.py proactive_agent --no-llm
```

3. 时间建议每天一次（PythonAnywhere 的任务时间按 **UTC**，北京时间 08:00 = UTC 00:00）

> 也可以挂每小时一次；有去重保护，不会重复打扰。

## 本地定时（可选）

Linux / macOS crontab：

```cron
0 8 * * * cd /path/to/management_system && venv/bin/python manage.py proactive_agent --no-llm
```

Windows 任务计划程序：程序填 `venv\Scripts\python.exe`，参数 `manage.py proactive_agent --no-llm`，起始于项目目录。

## 验证

```bash
python manage.py proactive_agent --dry-run --no-llm
```

看到「巡检完成：候选活动 N 个」即正常。真正执行后，到 `/ai/drafts/` 应该能看到带绿色「主动」标签的待确认草稿。

## 关闭 / 回滚

- 停用：删除或暂停定时任务即可
- 清理已生成草稿：`AIDraft.objects.filter(source='proactive', status='pending').delete()`
- 字段回滚：`python manage.py migrate club 0014`（会删除 `source` / `source_key` 两列）

## 后续可扩展的巡检规则

- 活动报名人数长期低于 50% → 生成「招募文案」
- 题库某模块超过 N 天没有新题 → 提醒管理员
- 公告发布后 7 天无人阅读（需要阅读统计）→ 建议置顶或改写
- 资料上传后无简介/无分类 → 提醒补齐
