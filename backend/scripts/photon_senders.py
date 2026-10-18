#!/usr/bin/env python3
"""List the Photon lines this project can send from, so PHOTON_SMS_SENDER_ID can be filled in.

Run from backend/ with PHOTON_API_KEY (pho_sk_…) and PHOTON_PROJECT_ID (pho_prj_…) in .env:

    .venv/bin/python scripts/photon_senders.py

A line is an "agent" user of the project; its id (pho_usr_…) is the sender id. Nothing secret is printed.
"""
import sys

import httpx

from owed.config import settings


def describe(page):
    rows = []
    for u in page.get('items') or []:
        if u.get('kind') != 'agent':
            continue
        line = (u.get('details') or {}).get('type') or ''
        rows.append(f"{u.get('platform', ''):<9} {line:<10} {u.get('handle', ''):<13} sender id: {u.get('id', '')}")
    return rows


def env_hint(page):
    agents = [u for u in (page.get('items') or []) if u.get('kind') == 'agent']
    if not agents:
        return ''
    first = agents[0]
    return f"PHOTON_SMS_SENDER_ID={first.get('id', '')}\nPHOTON_PLATFORM={first.get('platform', 'sms')}"


def main():
    key, pid = settings.photon_api_key, settings.photon_project_id
    if not key or not pid:
        print('PHOTON_API_KEY and PHOTON_PROJECT_ID are not both set in backend/.env', file=sys.stderr)
        return 2
    if not pid.startswith('pho_prj_'):
        print(f'PHOTON_PROJECT_ID should start with pho_prj_ (Photon v2); yours starts with {pid[:4]}…  Copy it from the project settings at app.beta.photon.codes', file=sys.stderr)
        return 2
    with httpx.Client(base_url='https://api.photon.codes', headers={'Authorization': 'Bearer ' + key}, timeout=20) as client:
        response = client.get(f'/v1/projects/{pid}/users')
    if response.status_code != 200:
        try:
            detail = response.json().get('title') or response.text[:200]
        except ValueError:
            detail = response.text[:200]
        print(f'Photon answered {response.status_code}: {detail}. Check that the key is a project service key for this project.', file=sys.stderr)
        return 1
    page = response.json()
    rows = describe(page)
    if not rows:
        print('No sending lines on this project yet. Assign a shared line or buy a number in the Photon dashboard first.')
        return 1
    print('\n'.join(rows))
    print('\nAdd to backend/.env (first line shown):\n' + env_hint(page))
    return 0


if __name__ == '__main__':
    sys.exit(main())
