"""
AI 服务层
=========
封装大模型 Provider 调用和智能体 System Prompt 管理。

设计要点：
- Provider 回退链：用户请求 → DeepSeek（优先） → 阿里云百炼（回退）
- 两者都未配置时抛 RuntimeError，由 views 层捕获并给用户友好提示
- 每个 Provider 函数返回统一格式 {'content', 'model', 'tokens', 'provider'}
- 超时统一 60 秒，stream=False（暂不支持流式输出）
"""

import os

import requests

# ---------------------------------------------------------------------------
# 5 种智能体的 System Prompt
# ---------------------------------------------------------------------------
# 每个智能体角色在其 Prompt 中定义了：能力边界、语气风格、回答格式要求。
# 如需新增智能体类型，在此处追加后同步更新 AIConversation.AGENT_CHOICES。

AGENT_PROMPTS = {
    'club_assistant': (
        '你是计算机俱乐部的社团助手。你的职责是：\n'
        '1. 介绍社团的活动、资料、刷题等功能；\n'
        '2. 帮助新成员了解 10 个学习模块（数据结构、组成原理、网络、操作系统、C/C++、Java、Python、MySQL、离散数学、其它）；\n'
        '3. 引导用户使用上传资料、提交题目等功能；\n'
        '4. 语气亲切友好，像俱乐部里热心的学长/学姐。\n'
        '回答使用 Markdown 格式，代码用 ```language 包裹。'
    ),
    'study_coach': (
        '你是一位经验丰富的计算机学习教练。你的职责是：\n'
        '1. 根据用户的年级、专业和目标，定制分阶段的学习路线图；\n'
        '2. 在 10 个模块（数据结构、组成原理、网络、操作系统、C/C++、Java、Python、MySQL、离散数学、其它）中推荐合适的学习顺序；\n'
        '3. 推荐具体的书籍、视频、在线课程和刷题网站；\n'
        '4. 帮助制定每周学习计划和时间管理策略；\n'
        '5. 鼓励用户坚持学习，保持积极的学习心态。\n'
        '回答使用 Markdown 格式，代码用 ```language 包裹，尽量结构化。'
    ),
    'problem_tutor': (
        '你是计算机题库的题目答疑老师。你的职责是：\n'
        '1. 分析计算机相关题目的解题思路和最优解法；\n'
        '2. 说明不同解法的时间/空间复杂度；\n'
        '3. 提供可运行的代码示例，支持 C/C++、Java、Python；\n'
        '4. 讲解相关的知识点（数据结构、算法、操作系统、网络等）；\n'
        '5. 引导用户思考，而不是直接给出答案。\n'
        '回答使用 Markdown 格式，代码用 ```language 包裹。'
    ),
    'code_review': (
        '你是一位资深的代码评审专家。你的职责是：\n'
        '1. 审查代码中的 bug、边界条件错误和安全隐患；\n'
        '2. 评估代码的时间复杂度、空间复杂度和性能瓶颈；\n'
        '3. 检查代码风格、命名规范和可读性；\n'
        '4. 提出具体的改进建议和优化方案；\n'
        '5. 给出改进后的代码示例。\n'
        '评审维度：正确性 → 性能 → 可读性 → 风格规范。\n'
        '回答使用 Markdown 格式，代码用 ```language 包裹。'
    ),
    'interview': (
        '你是计算机专业的资深面试官。你的职责是：\n'
        '1. 进行算法题面试，实时评估候选人的解题思路；\n'
        '2. 提问计算机网络、操作系统、数据库、数据结构等八股文；\n'
        '3. 进行项目经验深挖和系统设计；\n'
        '4. 每次候选人回答后给出评分（1-10）和具体反馈；\n'
        '5. 面试结束后给出综合评价和改进建议。\n'
        '风格：严肃、专业、模拟真实面试场景。\n'
        '回答使用 Markdown 格式，代码用 ```language 包裹。'
    ),
}

# 智能体类型 → 中文名，用于前端下拉选择和后端日志
AGENT_LABELS = {
    'club_assistant': '社团助手',
    'study_coach': '学习教练',
    'problem_tutor': '题目答疑',
    'code_review': '代码评审',
    'interview': '面试模拟',
}


def _build_messages(agent_type, history, user_message):
    """
    组装传给大模型的 messages 列表。

    顺序：System Prompt → 历史上下文（user + assistant 交替）→ 本轮 user 消息。
    agent_type 不在 AGENT_PROMPTS 里时自动 fallback 到社团助手，保证不会空崩。
    """
    system_prompt = AGENT_PROMPTS.get(agent_type, AGENT_PROMPTS['club_assistant'])
    messages = [{'role': 'system', 'content': system_prompt}]
    for msg in history:
        messages.append({'role': msg.role, 'content': msg.content})
    messages.append({'role': 'user', 'content': user_message})
    return messages


def call_deepseek(messages, model='deepseek-chat', temperature=0.7):
    """
    调用 DeepSeek Chat API。

    - 地址：{DEEPSEEK_BASE_URL}/chat/completions（默认 https://api.deepseek.com）
    - model 默认 deepseek-chat，可通过参数传入 deepseek-reasoner 等
    - 返回统一格式 dict，方便上层 chat() 函数透明处理
    """
    api_key = os.getenv('DEEPSEEK_API_KEY')
    base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY 未配置')
    resp = requests.post(
        f'{base_url}/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'model': model,
            'messages': messages,
            'temperature': temperature,
            'stream': False,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        'content': data['choices'][0]['message']['content'],
        'model': data.get('model', model),
        'tokens': data.get('usage', {}).get('total_tokens', 0),
        'provider': 'deepseek',
    }


def call_bailian(messages, model='qwen-plus', temperature=0.7):
    """
    调用阿里云百炼（DashScope）兼容模式。

    - 地址固定为 https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
    - 兼容 OpenAI 格式，所以请求体结构与 DeepSeek 完全一致
    """
    api_key = os.getenv('BAILIAN_API_KEY')
    if not api_key:
        raise RuntimeError('BAILIAN_API_KEY 未配置')
    resp = requests.post(
        'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'model': model,
            'messages': messages,
            'temperature': temperature,
            'stream': False,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        'content': data['choices'][0]['message']['content'],
        'model': data.get('model', model),
        'tokens': data.get('usage', {}).get('total_tokens', 0),
        'provider': 'bailian',
    }


def chat(agent_type, history, user_message):
    """
    AI 对话入口（唯一对外接口）。

    执行流程：
    1. 根据 agent_type 构建带 System Prompt 的 messages
    2. 按「配置优先级」组装 Provider 列表（谁先配置谁先试）
    3. 依次尝试，第一个成功的 Provider 结果直接返回
    4. 全部失败则抛 RuntimeError，被 views.ai_api_send 捕获后写一条错误 AIMessage

    这样设计的好处：
    - 用户无感知底层 Provider 切换
    - 可以未来方便追加新 Provider（如 硅基流动 / 通义千问原生 / 本地 Ollama）
    - 配置哪个用哪个，不强制要求两个都配
    """
    messages = _build_messages(agent_type, history, user_message)
    providers = []
    if os.getenv('DEEPSEEK_API_KEY'):
        providers.append(('deepseek', call_deepseek))
    if os.getenv('BAILIAN_API_KEY'):
        providers.append(('bailian', call_bailian))
    if not providers:
        raise RuntimeError('未配置任何 AI API Key，请在 .env 中设置 DEEPSEEK_API_KEY 或 BAILIAN_API_KEY')
    last_err = None
    for name, fn in providers:
        try:
            return fn(messages)
        except Exception as e:
            last_err = e
    raise RuntimeError(f'AI 调用失败（{len(providers)} 个 Provider 均失败）: {last_err}')