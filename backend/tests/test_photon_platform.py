"""A Photon shared line can be iMessage: the platform used for users and spaces is configurable, and the sender id is a pho_usr_ agent user."""
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import httpx

from owed.config import settings
from owed.channels.photon import Photon


def test_platform_setting_drives_user_and_space_creation(monkeypatch):
    monkeypatch.setattr(settings, 'photon_api_key', 'pho_sk_test')
    monkeypatch.setattr(settings, 'photon_project_id', 'pho_prj_test')
    monkeypatch.setattr(settings, 'photon_sms_sender_id', 'pho_usr_agent')
    monkeypatch.setattr(settings, 'photon_platform', 'imessage')
    bodies = []

    def handle(request):
        if request.method == 'GET':
            bodies.append((request.url.path, dict(request.url.params)))
            return httpx.Response(200, json={'items': []})
        bodies.append((request.url.path, json.loads(request.content), request.headers.get('idempotency-key')))
        if request.url.path.endswith('/users'):
            return httpx.Response(200, json={'id': 'pho_usr_owner', 'platform': 'imessage'})
        if request.url.path.endswith('/spaces'):
            return httpx.Response(200, json={'id': 'pho_spc_1'})
        return httpx.Response(200, json={'id': 'pho_msg_1', 'status': 'accepted'})

    asyncio.run(Photon(httpx.MockTransport(handle)).send('+19495550000', 'Please pay', 'sms', 'rem-1'))
    assert bodies[0] == ('/v1/projects/pho_prj_test/spaces', {'platform': 'imessage', 'participantHandle': '+19495550000', 'pageSize': '1'})
    assert bodies[1] == ('/v1/projects/pho_prj_test/users', {'platform': 'imessage', 'handle': '+19495550000'}, None)
    assert bodies[2][1]['platform'] == 'imessage' and bodies[2][1]['participantIds'] == ['pho_usr_agent', 'pho_usr_owner'] and bodies[2][2] == 'rem-1:space'
    assert bodies[3][1]['senderId'] == 'pho_usr_agent' and bodies[3][1]['spaceId'] == 'pho_spc_1' and bodies[3][2] == 'rem-1'


def test_existing_shared_line_conversation_is_reused(monkeypatch):
    """A shared iMessage line can only answer inside the conversation the owner started: no new user or space."""
    monkeypatch.setattr(settings, 'photon_api_key', 'pho_sk_test')
    monkeypatch.setattr(settings, 'photon_project_id', 'pho_prj_test')
    monkeypatch.setattr(settings, 'photon_sms_sender_id', 'pho_usr_agent')
    monkeypatch.setattr(settings, 'photon_platform', 'imessage')
    calls = []

    def handle(request):
        calls.append((request.method, request.url.path))
        if request.method == 'GET':
            return httpx.Response(200, json={'items': [{'id': 'pho_spc_existing', 'participantIds': ['pho_usr_agent', 'pho_usr_owner'], 'platform': 'imessage'}]})
        assert json.loads(request.content)['spaceId'] == 'pho_spc_existing'
        return httpx.Response(200, json={'id': 'pho_msg_2', 'status': 'accepted'})

    receipt = asyncio.run(Photon(httpx.MockTransport(handle)).send('+19495550000', 'Please pay', 'sms', 'rem-2'))
    assert [c[0] for c in calls] == ['GET', 'POST'] and calls[1][1].endswith('/messages')
    assert receipt == {'provider_message_id': 'pho_msg_2', 'space_id': 'pho_spc_existing', 'provider_status': 'accepted'}


def test_platform_defaults_to_sms():
    assert settings.model_fields['photon_platform'].default == 'sms'


def test_senders_script_lists_agent_users_without_printing_the_key():
    spec = importlib.util.spec_from_file_location('photon_senders', Path(__file__).resolve().parents[1] / 'scripts' / 'photon_senders.py')
    mod = importlib.util.module_from_spec(spec); sys.modules['photon_senders'] = mod; spec.loader.exec_module(mod)
    page = {'items': [
        {'id': 'pho_usr_agent1', 'kind': 'agent', 'platform': 'imessage', 'handle': '+16287896792', 'details': {'type': 'shared'}},
        {'id': 'pho_usr_human1', 'kind': 'user', 'platform': 'imessage', 'handle': '+19499759452'},
        {'id': 'pho_usr_agent2', 'kind': 'agent', 'platform': 'sms', 'handle': '+14155550123', 'details': {'type': 'dedicated'}},
    ]}
    lines = mod.describe(page)
    assert lines == ['imessage  shared     +16287896792  sender id: pho_usr_agent1',
                     'sms       dedicated  +14155550123  sender id: pho_usr_agent2']
    assert mod.env_hint(page) == 'PHOTON_SMS_SENDER_ID=pho_usr_agent1\nPHOTON_PLATFORM=imessage'
