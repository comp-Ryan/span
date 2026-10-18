"""Live question battery against a running Span backend.

Run from backend/:  .venv/bin/python scripts/ask_battery.py [--base URL] [--company ID] [--only N,M] [--json out.json]

Posts each question to /ask, polls /runs/{id} until run.end and prints intent, tool
sequence, final spoken answer, failures and timing. Approval tools (rank_chase,
send_message, defer_bill) create real pending decisions; this script never resolves them.
Uses only the standard library.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

QUESTIONS = [
    {'q': 'Will I make payroll in two weeks?'},
    {'q': 'Can I cover payroll on Friday?'},
    {'q': 'Can I afford a $3,000 forklift next week?'},
    {'q': 'Can I afford to hire someone at $4k/month starting November?'},
    {'q': 'Who should I chase today?'},
    {'q': "Who's my worst payer?"},
    {'q': 'How is Evergreen doing?'},
    {'q': 'How reliable is Yeoman Roasters?'},
    {'q': 'What bills are due this week?'},
    {'q': 'Can I push the utilities bill?'},
    {'q': "What's my cash low point in the next month?"},
    {'q': 'How much am I owed and how much is overdue?'},
    {'q': 'Should I take a $1,200 order from Yeoman Roasters on net 30?'},
    {'q': 'Am I okay?'},
    {'q': "What's the weather?"},
    {'q': 'Should I take a big new order?', 'followup': 'It is $5,000 from Evergreen, net 30, materials cost $2,000 up front.'},
]


def call(base, path, body=None, timeout=30):
    req = urllib.request.Request(base + path, method='POST' if body is not None else 'GET',
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def summarize(events):
    nodes, order, speech, ended = {}, [], [], None
    for e in events:
        d = e['data']
        if e['event'] == 'node.create':
            nodes[d['node_id']] = dict(d)
            order.append(d['node_id'])
        elif e['event'] == 'node.update' and d.get('node_id') in nodes:
            nodes[d['node_id']].update({k: v for k, v in d.items() if k in ('status', 'data')})
        elif e['event'] == 'speech':
            speech.append(d.get('text', ''))
        elif e['event'] == 'run.end':
            ended = d.get('status')
    tools = [nodes[i]['title'] for i in order if i.startswith('tool-') or i in ('n1', 'n2', 'n3', 'n5', 'late-scoring')]
    failures = [f"{nodes[i]['title']}: {(nodes[i].get('data') or {}).get('error', 'failed')}"
                for i in order if nodes[i].get('status') == 'failed']
    answer = next((nodes[i] for i in order if nodes[i].get('type') == 'answer'), None)
    return {'tools': tools, 'failures': failures, 'speech': speech[-1] if speech else None, 'ended': ended,
            'awaiting_input': bool(answer and (answer.get('data') or {}).get('awaiting_input')),
            'detail': (answer.get('data') or {}).get('detail', '') if answer else ''}


def ask(base, company, question, parent=None, timeout=90):
    start = time.time()
    body = {'question': question, 'source': 'web'}
    if parent:
        body['parent_run_id'] = parent
    try:
        started = call(base, f'/ask?company={company}', body)
    except urllib.error.HTTPError as exc:
        return {'question': question, 'error': f'HTTP {exc.code}: {exc.read()[:200]!r}', 'seconds': 0}
    run_id = started['run_id']
    result = {}
    while time.time() - start < timeout:
        time.sleep(1.5)
        result = summarize(call(base, f'/runs/{run_id}?company={company}')['events'])
        if result['ended']:
            break
    else:
        result['failures'] = result.get('failures', []) + ['timeout waiting for run.end']
    return {'question': question, 'run_id': run_id, 'intent': started['intent'],
            'seconds': round(time.time() - start, 1), **result}


def show(r, verbose):
    print('=' * 100)
    print(f"Q: {r['question']}")
    if r.get('error'):
        print(f"  ERROR {r['error']}")
        return
    print(f"  run={r['run_id']} intent={r['intent']} {r['seconds']}s ended={r.get('ended')}"
          f"{' AWAITING_INPUT' if r.get('awaiting_input') else ''}")
    print(f"  tools: {' -> '.join(r.get('tools') or []) or '(none)'}")
    print(f"  spoken: {r.get('speech')}")
    if r.get('failures'):
        print(f"  FAILURES: {r['failures']}")
    if verbose and r.get('detail'):
        print('  detail:\n    ' + r['detail'].replace('\n', '\n    '))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', default='http://127.0.0.1:8000')
    p.add_argument('--company', default='company-020')
    p.add_argument('--only', default='', help='comma-separated 1-based question numbers')
    p.add_argument('--question', action='append', default=[], help='ask custom question(s) instead')
    p.add_argument('--verbose', '-v', action='store_true')
    p.add_argument('--json')
    a = p.parse_args()
    items = [{'q': q} for q in a.question] or QUESTIONS
    if a.only:
        items = [items[int(i) - 1] for i in a.only.split(',')]
    results = []
    for item in items:
        r = ask(a.base, a.company, item['q'])
        show(r, a.verbose)
        results.append(r)
        if item.get('followup') and r.get('run_id'):
            f = ask(a.base, a.company, item['followup'], parent=r['run_id'])
            f['parent_run_id'] = r['run_id']
            show(f, a.verbose)
            results.append(f)
    bad = [r for r in results if r.get('error') or r.get('failures') or not r.get('speech')]
    print('=' * 100)
    print(f'{len(results) - len(bad)}/{len(results)} runs ended with an answer and no failed nodes')
    if a.json:
        with open(a.json, 'w') as fh:
            json.dump(results, fh, indent=2)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
