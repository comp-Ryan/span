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
        bodies.append((request.url.path, json.loads(request.content)))
        if request.url.path.endswith('/users'):
            return httpx.Response(200, json={'id': 'pho_usr_owner', 'platform': 'imessage'})
        if request.url.path.endswith('/spaces'):
            return httpx.Response(200, json={'id': 'pho_spc_1'})
        return httpx.Response(200, json={'id': 'pho_msg_1', 'status': 'accepted'})

    asyncio.run(Photon(httpx.MockTransport(handle)).send('+19495550000', 'Please pay', 'sms', 'rem-1'))
    assert bodies[0] == ('/v1/projects/pho_prj_test/users', {'platform': 'imessage', 'handle': '+19495550000'})
    assert bodies[1][1]['platform'] == 'imessage' and bodies[1][1]['participantIds'] == ['pho_usr_agent', 'pho_usr_owner']
    assert bodies[2][1]['senderId'] == 'pho_usr_agent'


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
