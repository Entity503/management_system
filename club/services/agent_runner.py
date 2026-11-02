"""
智能体执行器（多轮工具调用）
============================
把「模型 → 调用工具 → 把结果喂回模型 → 再回答」这套循环封装起来。

约束：
- 最多 3 轮工具调用，防止模型无限绕圈
- 工具白名单 + 参数校验 + 服务端权限判断
- 只读工具直接返回数据；写操作只产出 AIDraft(pending)，绝不直接发布
"""

from .. import ai_service
from ..agents import agent_temperature
from .ai_tools import TOOL_LABELS, TOOL_SCHEMAS, execute_tool

MAX_TOOL_ROUNDS = 3
FALLBACK_TEXT = '我暂时没法完成这个请求，可以再具体描述一下吗？'


def run_with_tools(agent_type, history, user_message, context, user):
    """
    执行一次带工具的对话。

    返回 {'content', 'model', 'tokens', 'tool_trace', 'draft'}：
    - tool_trace：给前端渲染的气泡列表 [{'name','label','ok','summary'}]
    - draft：本轮生成的最后一个草稿对象（没有则 None）
    """
    messages = ai_service.build_messages(agent_type, history, user_message, context=context)
    temperature = agent_temperature(agent_type)
    trace = []
    draft = None
    model_name = ''
    tokens = 0

    for round_index in range(MAX_TOOL_ROUNDS):
        result = ai_service.chat_messages(messages, tools=TOOL_SCHEMAS, temperature=temperature)
        model_name = result.get('model') or model_name
        tokens += int(result.get('tokens') or 0)

        tool_calls = result.get('tool_calls') or []
        if not tool_calls:
            return {
                'content': result.get('content') or '',
                'model': model_name,
                'tokens': tokens,
                'tool_trace': trace,
                'draft': draft,
            }

        messages.append({
            'role': 'assistant',
            'content': result.get('content') or '',
            'tool_calls': tool_calls,
        })

        for call_index, call in enumerate(tool_calls):
            function = call.get('function') or {}
            name = function.get('name') or ''
            call_id = call.get('id') or f'call_{round_index}_{call_index}'

            outcome = execute_tool(name, function.get('arguments'), user)
            messages.append({
                'role': 'tool',
                'tool_call_id': call_id,
                'content': outcome['for_model'],
            })
            trace.append({
                'name': name,
                'label': TOOL_LABELS.get(name, name),
                'ok': bool(outcome.get('ok')),
                'summary': outcome.get('summary', ''),
            })
            if outcome.get('draft') is not None:
                draft = outcome['draft']

    # 轮次用尽：不再给工具，强制模型用文本收尾
    result = ai_service.chat_messages(messages, temperature=temperature)
    model_name = result.get('model') or model_name
    tokens += int(result.get('tokens') or 0)
    return {
        'content': result.get('content') or FALLBACK_TEXT,
        'model': model_name,
        'tokens': tokens,
        'tool_trace': trace,
        'draft': draft,
    }
