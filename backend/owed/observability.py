"""Request tracing, Google GenAI monitoring, logs, and secret-free telemetry."""
import logging
from urllib.parse import urlsplit, urlunsplit
import sentry_sdk
from sentry_sdk.integrations.google_genai import GoogleGenAIIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from owed.config import settings


def scrub(event, hint):
    request = event.get('request')
    if request:
        for key in ('data','headers','cookies','query_string'):
            request.pop(key,None)
        if request.get('url'):
            u=urlsplit(request['url'])
            request['url']=urlunsplit((u.scheme,u.netloc,u.path,'',''))
    return event


def init():
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn,traces_sample_rate=1.0,enable_logs=True,
            send_default_pii=False,include_local_variables=False,max_request_body_size='never',
            integrations=[GoogleGenAIIntegration(include_prompts=False),LoggingIntegration(level=logging.INFO,event_level=logging.ERROR)],
            before_send=scrub,before_send_transaction=scrub,environment=settings.environment,
            release='owed@'+settings.release)
