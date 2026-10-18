"""OpenRouter backup for the planner: same tool loop, OpenAI-compatible wire format, used when Gemini cannot answer."""
import asyncio
import json
from datetime import date
from types import SimpleNamespace as NS

import httpx
import pytest
from google.genai import errors, types

from owed import planner
from owed.config import settings
from owed.planner_backup import OpenRouterClient, to_openai_messages, to_openai_tools


def test_tool_declarations_convert_to_openai_function_schemas():
    tools = to_openai_tools(planner.TOOLS)
    assert tools[0]['type'] == 'function'
    forecast = next(t['function'] for t in tools if t['function']['name'] == 'forecast_cash')
    assert forecast['parameters']['type'] == 'object'
    assert forecast['parameters']['properties']['target_date'] == {'type': 'string'}
    assert forecast['parameters']['properties']['will_pay'] == {'type': 'boolean'}
    afford = next(t['function'] for t in tools if t['function']['name'] == 'check_affordability')
    assert afford['parameters']['properties']['frequency'] == {'type': 'string', 'enum': ['once', 'weekly', 'monthly']}
    assert afford['parameters']['required'] == ['amount', 'start_date', 'frequency']


def test_contents_convert_to_openai_messages_including_gemini_turns_without_ids():
    gemini_turn = types.Content(role='model', parts=[types.Part(function_call=types.FunctionCall(name='forecast_cash', args={'target_date': '2026-10-20'}))])
    contents = [
        types.Content(role='user', parts=[types.Part(text='Will I make payroll?')]),
        gemini_turn,
        types.Content(role='user', parts=[types.Part(function_response=types.FunctionResponse(id=None, name='forecast_cash', response={'gap': 385})),
                                          types.Part(text=planner.FINAL_NUDGE)]),
    ]
    messages = to_openai_messages('You are Span.', contents)
    assert messages[0] == {'role': 'system', 'content': 'You are Span.'}
    assert messages[1] == {'role': 'user', 'content': 'Will I make payroll?'}
    assert messages[2]['role'] == 'assistant' and messages[2]['tool_calls'][0]['function'] == {'name': 'forecast_cash', 'arguments': '{"target_date": "2026-10-20"}'}
    call_id = messages[2]['tool_calls'][0]['id']
    assert messages[3] == {'role': 'tool', 'tool_call_id': call_id, 'content': '{"gap": 385}'}
    assert messages[4] == {'role': 'user', 'content': planner.FINAL_NUDGE}


def test_openrouter_client_speaks_openai_and_returns_gemini_shaped_responses():
    seen = {}

    def handle(request):
        seen['url'] = str(request.url); seen['auth'] = request.headers.get('authorization'); seen['body'] = json.loads(request.content)
        if seen['body'].get('tool_choice') == 'none':
            return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': 'No, $385 short.\n---\n## Why\nBooks.'}}]})
        return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'call_1', 'type': 'function', 'function': {'name': 'forecast_cash', 'arguments': '{"target_date": "2026-10-20"}'}}]}}]})

    client = OpenRouterClient('sk-or-test', 'google/gemini-3.8-flash', transport=httpx.MockTransport(handle))
    config = types.GenerateContentConfig(system_instruction='You are Span.', tools=[types.Tool(function_declarations=planner.TOOLS)])
    contents = [types.Content(role='user', parts=[types.Part(text='Will I make payroll?')])]
    response = asyncio.run(client.aio.models.generate_content(model='google/gemini-3.8-flash', contents=contents, config=config))
    assert seen['url'] == 'https://openrouter.ai/api/v1/chat/completions' and seen['auth'] == 'Bearer sk-or-test'
    assert seen['body']['model'] == 'google/gemini-3.8-flash' and seen['body']['tool_choice'] == 'auto' and len(seen['body']['tools']) == len(planner.TOOLS)
    assert seen['body']['max_tokens'] == 4096  # OpenRouter reserves the cap against the balance; the planner never needs the model's 65k ceiling
    content = response.candidates[0].content
    call = [p.function_call for p in content.parts if p.function_call][0]
    assert call.name == 'forecast_cash' and call.args == {'target_date': '2026-10-20'} and call.id == 'call_1'
    # the shim's own turn plus the tool result round-trip on the next call
    contents += [content, types.Content(role='user', parts=[types.Part(function_response=types.FunctionResponse(id=call.id, name=call.name, response={'gap': 385}))])]
    final = config.model_copy(update={'tool_config': types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode='NONE'))})
    response = asyncio.run(client.aio.models.generate_content(model='google/gemini-3.8-flash', contents=contents, config=final))
    assert seen['body']['messages'][2]['tool_calls'][0]['id'] == 'call_1' and seen['body']['messages'][3] == {'role': 'tool', 'tool_call_id': 'call_1', 'content': '{"gap": 385}'}
    parts = response.candidates[0].content.parts
    assert [p.text for p in parts] == ['No, $385 short.\n---\n## Why\nBooks.'] and not any(p.function_call for p in parts)
    asyncio.run(client.aio.aclose())


def test_openrouter_errors_are_explained():
    client = OpenRouterClient('sk-or-test', 'google/gemini-3.8-flash', transport=httpx.MockTransport(lambda r: httpx.Response(402, json={'error': {'message': 'Insufficient credits'}})))
    config = types.GenerateContentConfig(system_instruction='x', tools=[types.Tool(function_declarations=planner.TOOLS)])
    with pytest.raises(ValueError, match='OpenRouter.*402.*Insufficient credits'):
        asyncio.run(client.aio.models.generate_content(model='m', contents=[types.Content(role='user', parts=[types.Part(text='hi')])], config=config))


def test_planner_fails_over_to_openrouter_when_gemini_credits_are_depleted(monkeypatch):
    from tests.test_planner_conversation import Connection
    emitted = []
    monkeypatch.setattr(planner, 'emit', lambda run_id, event, data: emitted.append((event, data)))
    monkeypatch.setattr(planner, 'finish', lambda run_id, status: None)
    monkeypatch.setattr(planner, 'conn', lambda: Connection(None))
    monkeypatch.setattr(settings, 'openrouter_api_key', 'sk-or-test')
    monkeypatch.setattr(settings, 'openrouter_model', 'google/gemini-3.8-flash')

    class Depleted:
        async def generate_content(self, model, contents, config):
            raise errors.ClientError(402, {'error': {'code': 402, 'status': 'RESOURCE_EXHAUSTED', 'message': 'credits depleted'}})

    used = {}

    class FakeBackup:
        def __init__(self, key, model, transport=None):
            used['key'], used['model'] = key, model
            self.aio = NS(models=self, aclose=self.aclose)

        async def generate_content(self, model, contents, config):
            used['calls'] = used.get('calls', 0) + 1
            return NS(candidates=[NS(content=NS(role='model', parts=[NS(function_call=None, thought=False, text='Fine.\n---\n## Why\nOk.')]))])

        async def aclose(self):
            used['closed'] = True

    monkeypatch.setattr(planner, 'OpenRouterClient', FakeBackup)
    asyncio.run(planner.run_planner('run-1', 'company-1', 'Am I okay?', date(2026, 10, 9), client=NS(aio=NS(models=Depleted()))))
    assert used == {'key': 'sk-or-test', 'model': 'google/gemini-3.8-flash', 'calls': 1, 'closed': True}
    answer = next(d for e, d in emitted if e == 'node.create' and d['node_id'] == 'answer')
    assert answer['data']['spoken'] == 'Fine.' and answer['data']['provider'] == 'openrouter'
    assert any(e == 'node.update' and d.get('node_id') == 'context' and d['data'].get('planner') == 'openrouter' for e, d in emitted)


def test_settings_accept_the_open_router_key_spellings(monkeypatch):
    from owed.config import Settings
    for name in ('OPENROUTER_API_KEY', 'OPENROUTER_KEY', 'OPEN_ROUTER', 'OPEN_ROUTER_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('OPEN_ROUTER', 'sk-or-alias')
    assert Settings(_env_file=None).openrouter_api_key == 'sk-or-alias'
