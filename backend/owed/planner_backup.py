"""OpenRouter as the backup planner: the same Gemini-style tool loop over OpenAI's chat-completions format.

run_planner keeps building google-genai `types.Content` turns; this client translates them (and its own
turns) to OpenAI messages and returns Gemini-shaped responses (candidates → content → parts with
function_call / text), so the loop, approvals and canvas events do not change.
"""
import json
from types import SimpleNamespace as NS

import httpx

TYPE_MAP = {'OBJECT': 'object', 'STRING': 'string', 'NUMBER': 'number', 'INTEGER': 'integer',
            'BOOLEAN': 'boolean', 'ARRAY': 'array', 'NULL': 'null'}


def _schema(node):
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        if key == 'type' and isinstance(value, str):
            out[key] = TYPE_MAP.get(value.upper(), value.lower())
        elif key == 'properties' and isinstance(value, dict):
            out[key] = {name: _schema(sub) for name, sub in value.items()}
        elif key == 'items':
            out[key] = _schema(value)
        else:
            out[key] = value
    return out


def to_openai_tools(declarations):
    tools = []
    for d in declarations:
        if not isinstance(d, dict):
            d = d.model_dump(mode='json', exclude_none=True)  # google.genai types.FunctionDeclaration
        params = _schema(d.get('parameters') or {})
        params.setdefault('type', 'object')
        params.setdefault('properties', {})
        tools.append({'type': 'function', 'function': {'name': d['name'], 'description': d.get('description', ''),
                                                       'parameters': params}})
    return tools


def _fields(part):
    return (getattr(part, 'text', None), getattr(part, 'function_call', None),
            getattr(part, 'function_response', None), bool(getattr(part, 'thought', False)))


def to_openai_messages(system, contents):
    """Gemini turns (model function calls may lack ids) and this client's turns → OpenAI messages."""
    messages = [{'role': 'system', 'content': system}] if system else []
    pending_ids = []  # synthesized ids for Gemini calls without ids, consumed by the following tool results in order
    for turn, content in enumerate(contents):
        role = getattr(content, 'role', None) or 'user'
        parts = getattr(content, 'parts', None) or []
        if role in ('model', 'assistant'):
            texts, calls = [], []
            for i, part in enumerate(parts):
                text, call, _, thought = _fields(part)
                if thought:
                    continue
                if call is not None:
                    call_id = getattr(call, 'id', None) or f'call_{turn}_{i}'
                    pending_ids.append(call_id)
                    args = getattr(call, 'args', None) or {}
                    calls.append({'id': call_id, 'type': 'function',
                                  'function': {'name': call.name, 'arguments': json.dumps(dict(args), default=str)}})
                elif text:
                    texts.append(text)
            message = {'role': 'assistant', 'content': ''.join(texts) or None}
            if calls:
                message['tool_calls'] = calls
            messages.append(message)
            continue
        texts = []
        for part in parts:
            text, _, result, _ = _fields(part)
            if result is not None:
                given = getattr(result, 'id', None)
                if given and given in pending_ids:
                    pending_ids.remove(given)
                call_id = given or (pending_ids.pop(0) if pending_ids else f'call_{turn}')
                messages.append({'role': 'tool', 'tool_call_id': call_id,
                                 'content': json.dumps(getattr(result, 'response', None), default=str)})
            elif text:
                texts.append(text)
        if texts:
            messages.append({'role': 'user', 'content': '\n'.join(texts)})
    return messages


class OpenRouterClient:
    """Minimal stand-in for genai.Client: `aio.models.generate_content(model, contents, config)` and `aio.aclose()`."""

    def __init__(self, api_key, model, base_url='https://openrouter.ai/api/v1', transport=None):
        self.model = model
        self._http = httpx.AsyncClient(base_url=base_url, timeout=90, transport=transport, headers={
            'Authorization': f'Bearer {api_key}', 'HTTP-Referer': 'https://github.com/comp-Ryan/span', 'X-Title': 'Span'})
        self.aio = NS(models=NS(generate_content=self.generate_content), aclose=self.aclose)

    async def aclose(self):
        await self._http.aclose()

    async def generate_content(self, model=None, contents=(), config=None):
        system = getattr(config, 'system_instruction', None)
        declarations = [d for tool in (getattr(config, 'tools', None) or []) for d in (getattr(tool, 'function_declarations', None) or [])]
        mode = getattr(getattr(getattr(config, 'tool_config', None), 'function_calling_config', None), 'mode', None)
        mode = str(getattr(mode, 'value', mode) or '').upper()
        body = {'model': model or self.model, 'messages': to_openai_messages(system if isinstance(system, str) else None, list(contents)),
                'temperature': 0.2}
        if declarations:
            body['tools'] = to_openai_tools(declarations)
            body['tool_choice'] = 'none' if mode.endswith('NONE') else 'auto'
        response = await self._http.post('/chat/completions', json=body)
        if response.status_code >= 400:
            try:
                detail = (response.json().get('error') or {}).get('message') or response.text
            except ValueError:
                detail = response.text
            raise ValueError(f'OpenRouter backup failed ({response.status_code}): {str(detail)[:200]}')
        message = ((response.json().get('choices') or [{}])[0].get('message')) or {}
        parts = []
        text = message.get('content')
        if isinstance(text, list):
            text = ''.join(c.get('text', '') for c in text if isinstance(c, dict))
        if text:
            parts.append(NS(text=text, function_call=None, function_response=None, thought=False))
        for i, call in enumerate(message.get('tool_calls') or []):
            fn = call.get('function') or {}
            try:
                args = json.loads(fn.get('arguments') or '{}')
            except json.JSONDecodeError:
                args = {}
            parts.append(NS(text=None, function_response=None, thought=False,
                            function_call=NS(name=fn.get('name'), args=args if isinstance(args, dict) else {}, id=call.get('id') or f'call_{i}')))
        return NS(candidates=[NS(content=NS(role='model', parts=parts))], provider='openrouter')
