"""
AI 服务层
==========
封装大模型 Provider 调用，是唯一对外出入口。

设计要点：
- Provider 回退链：DeepSeek（优先） → 阿里云百炼（回退）
- 两者都未配置时抛 RuntimeError，由 views 层捕获并给用户友好提示
- 统一返回 {'content', 'tool_calls', 'model', 'tokens', 'provider'}
- ``stream_messages`` 是生成器，逐块产出 ('delta', 文本) / ('done', 元信息)
- 智能体的 System Prompt 统一维护在 club/agents.py
"""

import json
import os

import requests

from .agents import AGENT_LABELS, AGENT_PROMPTS, DEFAULT_AGENT  # noqa: F401  re-export 兼容旧引用

DEFAULT_TIMEOUT = 60
DEFAULT_MODEL = 'deepseek-chat'
BAILIAN_MODEL = 'qwen-plus'

# 平台配置：DeepSeek 与百炼的兼容模式都走 OpenAI 协议
DEEPSEEK_URL = '/chat/completions'
BAILIAN_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'


def build_messages(agent_type, history, user_message, context=None):
    """
    组装传给大模型的 messages 列表。

    顺序：System Prompt（+ 平台快照）→ 历史上下文（user + assistant 交替）→ 本轮 user 消息。
    agent_type 不在注册表里时自动 fallback 到默认智能体，保证不会空崩。
    """
    system_prompt = AGENT_PROMPTS.get(agent_type, AGENT_PROMPTS[DEFAULT_AGENT])
    if context:
        system_prompt = f'{system_prompt}\n\n{context}'
    messages = [{'role': 'system', 'content': system_prompt}]
    for msg in history:
        if msg.role not in ('user', 'assistant'):
            continue
        messages.append({'role': msg.role, 'content': msg.content})
    messages.append({'role': 'user', 'content': user_message})
    return messages


# 兼容旧调用
_build_messages = build_messages


def _provider_functions():
    """按配置优先级返回 [(provider 名, 调用函数), ...]。"""
    providers = []
    if os.getenv('DEEPSEEK_API_KEY'):
        providers.append(('deepseek', call_deepseek))
    if os.getenv('BAILIAN_API_KEY'):
        providers.append(('bailian', call_bailian))
    return providers


def _post_deepseek(payload, stream=False):
    api_key = os.getenv('DEEPSEEK_API_KEY')
    base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY 未配置')
    return requests.post(
        f'{base_url}{DEEPSEEK_URL}',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json=payload,
        timeout=DEFAULT_TIMEOUT,
        stream=stream,
    )


def _post_bailian(payload, stream=False):
    api_key = os.getenv('BAILIAN_API_KEY')
    if not api_key:
        raise RuntimeError('BAILIAN_API_KEY 未配置')
    return requests.post(
        BAILIAN_URL,
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json=payload,
        timeout=DEFAULT_TIMEOUT,
        stream=stream,
    )


def _parse_completion(data, model):
    """把非流式响应压成统一结构。"""
    choice = (data.get('choices') or [{}])[0]
    message = choice.get('message') or {}
    tool_calls = message.get('tool_calls') or []
    return {
        'content': message.get('content') or '',
        'tool_calls': tool_calls,
        'model': data.get('model') or model,
        'tokens': (data.get('usage') or {}).get('total_tokens', 0),
    }


def call_deepseek(messages, model=DEFAULT_MODEL, temperature=0.7, tools=None):
    """
    调用 DeepSeek Chat API（非流式）。

    - 地址：{DEEPSEEK_BASE_URL}/chat/completions（默认 https://api.deepseek.com）
    - tools 不为空时走 function calling，返回值里带 tool_calls
    """
    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'stream': False,
    }
    if tools:
        payload['tools'] = tools
        payload['tool_choice'] = 'auto'

    resp = _post_deepseek(payload)
    resp.raise_for_status()
    result = _parse_completion(resp.json(), model)
    result['provider'] = 'deepseek'
    return result


def call_bailian(messages, model=BAILIAN_MODEL, temperature=0.7, tools=None):
    """
    调用阿里云百炼（DashScope）兼容模式。

    请求体与 DeepSeek 完全一致（OpenAI 协议），因此复用同一套解析逻辑。
    """
    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'stream': False,
    }
    if tools:
        payload['tools'] = tools
        payload['tool_choice'] = 'auto'

    resp = _post_bailian(payload)
    resp.raise_for_status()
    result = _parse_completion(resp.json(), model)
    result['provider'] = 'bailian'
    return result


def chat_messages(messages, tools=None, temperature=0.7):
    """
    直接对 messages 发起一次（可能带工具的）对话，供 agent_runner 多轮调用。

    依次尝试已配置的 Provider，第一个成功的结果直接返回。
    """
    providers = _provider_functions()
    if not providers:
        raise RuntimeError('未配置任何 AI API Key，请在 .env 中设置 DEEPSEEK_API_KEY 或 BAILIAN_API_KEY')

    last_err = None
    for name, fn in providers:
        try:
            return fn(messages, tools=tools, temperature=temperature)
        except Exception as exc:  # noqa: BLE001  需要把所有 Provider 都试一遍
            last_err = exc
    raise RuntimeError(f'AI 调用失败（{len(providers)} 个 Provider 均失败）: {last_err}')


def chat(agent_type, history, user_message, context=None):
    """
    AI 对话入口（单轮，无工具）。

    返回统一格式字典；全部 Provider 失败时抛 RuntimeError。
    """
    messages = build_messages(agent_type, history, user_message, context=context)
    return chat_messages(messages)


# ---------------------------------------------------------------------------
# 流式输出（SSE）
# ---------------------------------------------------------------------------
def _iter_stream_chunks(response, model):
    """
    解析 OpenAI 协议的流式响应，逐块产出 ('delta', 文本) / ('done', 元信息)。

    [DONE] 之后结束；usage 只有 provider 返回时才有。
    """
    model_name = model
    total_tokens = 0

    for raw_line in response.iter_lines():
        if not raw_line:
            continue
        # 不依赖 requests 的编码推断：SSE 一律按 UTF-8 解码
        line = raw_line.decode('utf-8', errors='replace').strip()
        if not line.startswith('data:'):
            continue
        data_str = line[5:].strip()
        if data_str == '[DONE]':
            break
        try:
            data = json.loads(data_str)
        except (TypeError, ValueError):
            continue

        model_name = data.get('model') or model_name
        usage = data.get('usage') or {}
        if usage:
            total_tokens = usage.get('total_tokens', total_tokens)

        choices = data.get('choices') or []
        if not choices:
            continue
        delta = choices[0].get('delta') or {}
        text = delta.get('content')
        if text:
            yield 'delta', text

    yield 'done', {'model': model_name, 'tokens': total_tokens}


def _stream_provider(post_fn, messages, model, temperature):
    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'stream': True,
    }
    response = post_fn(payload, stream=True)
    response.raise_for_status()
    try:
        yield from _iter_stream_chunks(response, model)
    finally:
        response.close()


def stream_messages(messages, model=None, temperature=0.7):
    """
    流式对话生成器（仅文本，不含工具）。

    产出 ('delta', 文本片段) ... 最后产出 ('done', {'model', 'tokens'})。
    已经吐出内容后再出错会直接抛出，由视图层给前端发 error 事件。
    """
    providers = _provider_functions()
    if not providers:
        raise RuntimeError('未配置任何 AI API Key，请在 .env 中设置 DEEPSEEK_API_KEY 或 BAILIAN_API_KEY')

    last_err = None
    for name, fn in providers:
        emitted = False
        try:
            if name == 'deepseek':
                generator = _stream_provider(_post_deepseek, messages, model or DEFAULT_MODEL, temperature)
            else:
                generator = _stream_provider(_post_bailian, messages, model or BAILIAN_MODEL, temperature)

            for kind, payload in generator:
                if kind == 'delta':
                    emitted = True
                yield kind, payload
            return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if emitted:
                raise
    raise RuntimeError(f'AI 流式调用失败（{len(providers)} 个 Provider 均失败）: {last_err}')
