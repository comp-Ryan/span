import asyncio
import json
import httpx
from owed.channels.photon import Photon
from owed.config import settings


def test_photon_wire_format_and_idempotency(monkeypatch):
    monkeypatch.setattr(settings, 'photon_api_key', 'test-key')
    monkeypatch.setattr(settings, 'photon_project_id', 'test-project')
    monkeypatch.setattr(settings, 'photon_sms_sender_id', 'sender')
    requests=[]
    def handle(request):
        requests.append(request)
        assert request.headers['authorization'] == 'Bearer test-key'
        if request.url.path.endswith('/users'):
            return httpx.Response(200,json={'id':'recipient'})
        if request.url.path.endswith('/spaces'):
            assert json.loads(request.content)['participantIds'] == ['sender','recipient']
            return httpx.Response(200,json={'id':'space'})
        assert request.headers['idempotency-key']=='rem-test'
        assert json.loads(request.content)['content']=={'type':'text','format':'plain','text':'Please pay'}
        return httpx.Response(202,json={'id':'message','status':'dispatched'})
    result=asyncio.run(Photon(httpx.MockTransport(handle)).send('+15555550123','Please pay','sms','rem-test'))
    assert result['provider_message_id']=='message'
    assert len(requests)==3
