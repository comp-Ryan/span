#!/usr/bin/env python3
"""Chat with Span from the terminal: the same /ask, /runs and /decisions calls the web app makes, no browser, no voice.

Run from backend/ against a running backend (default http://127.0.0.1:8000):

    .venv/bin/python scripts/chat.py                         # interactive: type questions, answer approvals with yes/no
    .venv/bin/python scripts/chat.py "Will I make payroll in two weeks?"
    .venv/bin/python scripts/chat.py --decide no "Will I make payroll in two weeks?"   # answer the approval automatically
    .venv/bin/python scripts/chat.py --company company-020 --source call ...           # 'call' routes like the phone/browser call

Each later question in a session is a follow-up (parent_run_id) of the previous run, like the web chat; type /new to start
a fresh thread, /runs to list the last chats, /quit to leave. Nothing is approved unless you say so. Standard library only.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

WORDS_YES = {'y', 'yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'do it', 'go ahead', 'approve', 'approved'}
WORDS_NO = {'n', 'no', 'nope', 'not now', 'cancel', 'skip', 'stop'}


def call(base, path, body=None, timeout=30):
    req = urllib.request.Request(base + path, method='POST' if body is not None else 'GET',
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def choose_option(text, options):
    """Map what the owner typed onto a decision option id: the id, its 1-based number, its label, or a plain yes/no."""
    t = (text or '').strip().lower()
    if not t:
        return None
    ids = [o['id'] for o in options]
    if t in ids:
        return t
    if t.isdigit() and 1 <= int(t) <= len(options):
        return ids[int(t) - 1]
    for o in options:
        if t == str(o.get('label', '')).strip().lower():
            return o['id']
    first = re.split(r'[^a-z]+', t)[0]
    if (t in WORDS_YES or first in WORDS_YES) and 'yes' in ids:
        return 'yes'
    if (t in WORDS_NO or first in WORDS_NO) and 'no' in ids:
        return 'no'
    return None


def render(event):
    """One terminal line per event the owner cares about; None for bookkeeping events."""
    kind, d = event.get('event'), event.get('data') or {}
    if kind == 'run.start':
        return f"[{d.get('run_id')}] {d.get('question', '')}"
    if kind == 'node.create' and d.get('status') != 'done':
        return f"  … {d.get('title', d.get('node_id'))}"
    if kind == 'node.update' and d.get('status') == 'done':
        meta = (d.get('data') or {}).get('summary') or (d.get('data') or {}).get('spoken')
        return f"  ✓ {d.get('node_id')}" + (f" · {meta}" if meta else '')
    if kind == 'node.update' and d.get('status') == 'failed':
        return f"  ✗ {d.get('node_id')} · {(d.get('data') or {}).get('error', 'failed')}"
    if kind == 'speech':
        return f"span> {d.get('text', '')}"
    if kind == 'decision':
        opts = '\n'.join(f"  [{i}] {o['id']} · {o.get('label', '')}" for i, o in enumerate(d.get('options') or [], 1))
        return f"span> {d.get('prompt', 'Your call?')}\n{opts}"
    if kind == 'decision.resolved':
        return f"  decided: {d.get('option_id')}"
    if kind == 'run.end':
        return f"  — run {d.get('status', 'ended')} —"
    return None


class Seen:
    """Remembers how many of a run's events were already printed."""
    def __init__(self):
        self.count = 0

    def take(self, events):
        fresh = events[self.count:]
        self.count = len(events)
        return fresh


def pending_decision(events):
    resolved = {e['data'].get('decision_id') for e in events if e.get('event') == 'decision.resolved'}
    open_ones = [e['data'] for e in events if e.get('event') == 'decision' and e['data'].get('decision_id') not in resolved]
    return open_ones[-1] if open_ones else None


def settled(events):
    """'closed'/'open' once the run ended, 'decision' while it waits on the owner, else None."""
    for e in reversed(events):
        if e.get('event') == 'run.end':
            return e['data'].get('status', 'closed')
    return 'decision' if pending_decision(events) else None


class Chat:
    def __init__(self, base, company, source='web', out=sys.stdout):
        self.base, self.company, self.source, self.out = base, company, source, out
        self.parent = None

    def say(self, line):
        if line:
            print(line, file=self.out, flush=True)

    def events(self, run_id):
        return call(self.base, f'/runs/{run_id}?company={self.company}')['events']

    def follow(self, run_id, seen, timeout=120, quiet=4.0):
        """Print new events until the run ends, asks for a decision, or stays quiet for a while after its answer."""
        start = time.time(); last_change = time.time(); events = []
        while time.time() - start < timeout:
            events = self.events(run_id)
            fresh = seen.take(events)
            for e in fresh:
                self.say(render(e))
            if fresh:
                last_change = time.time()
            state = settled(events)
            if state:
                return state, events
            if time.time() - last_change > quiet and any(e.get('event') == 'speech' for e in events):
                return 'quiet', events
            time.sleep(0.8)
        self.say('  (timed out waiting for Span)')
        return 'timeout', events

    def ask(self, question, decide=None, ask_owner=None):
        body = {'question': question, 'source': self.source}
        if self.parent:
            body['parent_run_id'] = self.parent
        try:
            started = call(self.base, f'/ask?company={self.company}', body)
        except urllib.error.HTTPError as exc:
            self.say(f'  HTTP {exc.code}: {exc.read()[:300].decode(errors="replace")}')
            return None
        run_id = started['run_id']; self.parent = run_id
        seen = Seen()
        while True:
            state, events = self.follow(run_id, seen)
            if state != 'decision':
                return state
            d = pending_decision(events)
            answer = decide or (ask_owner(d) if ask_owner else None)
            option = choose_option(answer, d['options']) if answer else None
            if not option:
                self.say('  (left the approval pending; answer it later in the web app)')
                return 'decision'
            decide = None
            call(self.base, f"/decisions/{d['decision_id']}?company={self.company}", {'option_id': option})
            self.say(f'you> {option}')


def interactive(chat):
    def ask_owner(d):
        try:
            return input('decide (yes/no/number, Enter to leave pending)> ')
        except EOFError:
            return ''
    chat.say(f"Span at {chat.base} · company {chat.company} · type a question, /new, /runs or /quit")
    while True:
        try:
            line = input('you> ').strip()
        except (EOFError, KeyboardInterrupt):
            print(); return 0
        if not line:
            continue
        if line in ('/quit', '/exit', '/q'):
            return 0
        if line == '/new':
            chat.parent = None; chat.say('  (new thread)'); continue
        if line == '/runs':
            for r in call(chat.base, f'/runs?company={chat.company}')['runs'][:10]:
                chat.say(f"  {r['run_id']}  {r['status']:6}  {r['question'][:60]}")
            continue
        chat.ask(line, ask_owner=ask_owner)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('question', nargs='*', help='ask once and exit; omit for an interactive session')
    p.add_argument('--base', default='http://127.0.0.1:8000')
    p.add_argument('--company', default='company-020')
    p.add_argument('--source', default='web', choices=['web', 'call'])
    p.add_argument('--parent', help='continue this run id as a follow-up')
    p.add_argument('--decide', help="answer the first approval automatically ('yes', 'no', an option id or number)")
    a = p.parse_args(argv)
    try:
        health = call(a.base, '/health')
    except (OSError, urllib.error.URLError) as exc:
        print(f'No Span backend at {a.base} ({exc}). Start it from backend/: .venv/bin/uvicorn owed.main:app --port 8000', file=sys.stderr)
        return 2
    print(f"Span API {health.get('version', '?')} ({health.get('branch') or 'no branch'}) · planner {health.get('planner')}"
          f"{' + ' + health['planner_backup'] + ' backup' if health.get('planner_backup') else ''}", flush=True)
    chat = Chat(a.base, a.company, a.source)
    chat.parent = a.parent
    if a.question:
        state = chat.ask(' '.join(a.question), decide=a.decide)
        return 0 if state in ('closed', 'open', 'quiet', 'decision') else 1
    return interactive(chat)


if __name__ == '__main__':
    sys.exit(main())
