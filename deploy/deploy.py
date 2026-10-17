"""Deploy to an existing authorized Vultr host without replacing a populated database."""
import argparse
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def run(args,**kwargs):
    return subprocess.run(args,check=True,**kwargs)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+',args.host):
        parser.error('Use an SSH user@host')
    for file in ['backend/.env','deploy/.env','backend/models/payment_model.pkl']:
        if not (ROOT/file).is_file():
            parser.error(f'Missing {file}')
    containers=run(['docker','ps','--filter','publish=5433','--format','{{.ID}}'],capture_output=True,text=True).stdout.splitlines()
    if len(containers)!=1:
        parser.error('Expected one source database container on port 5433')
    local=ROOT/'.local'; local.mkdir(exist_ok=True)
    dump=local/'deploy.dump'
    with dump.open('wb') as output:
        run(['docker','exec',containers[0],'pg_dump','-U','owed','-d','owed','-Fc'],stdout=output)
    os.chmod(dump,0o600)
    run(['ssh',args.host,'mkdir -p /opt/owed/backend /opt/owed/deploy && chmod 700 /opt/owed'])
    run(['rsync','-az','--exclude=.env','--exclude=.venv','--exclude=*.log','--exclude=__pycache__',str(ROOT/'backend')+'/',args.host+':/opt/owed/backend/'])
    run(['rsync','-az','--exclude=.env',str(ROOT/'deploy')+'/',args.host+':/opt/owed/deploy/'])
    run(['rsync','-az',str(ROOT/'docs')+'/',args.host+':/opt/owed/docs/'])
    run(['scp',str(ROOT/'.dockerignore'),args.host+':/opt/owed/.dockerignore'])
    run(['scp',str(ROOT/'backend/.env'),args.host+':/opt/owed/backend/.env'])
    run(['scp',str(ROOT/'deploy/.env'),args.host+':/opt/owed/deploy/.env'])
    run(['scp',str(dump),args.host+':/opt/owed/deploy.dump'])
    script='''set -eu
cd /opt/owed/deploy
chmod 600 .env ../backend/.env ../deploy.dump
docker compose up -d --wait db
exists=$(docker compose exec -T db psql -U owed -d owed -Atc "select to_regclass('public.companies') is not null")
if [ "$exists" = "f" ]; then
  docker compose exec -T db pg_restore -U owed -d owed --no-owner < ../deploy.dump
fi
docker compose up -d --build --wait api agents caddy
curl --fail --retry 12 --retry-delay 5 http://127.0.0.1:8000/health
'''
    run(['ssh',args.host,'sh','-s'],input=script,text=True)
    print('Remote services started. Verify the public domain and provider callbacks before claiming deployment complete.')

if __name__=='__main__':
    main()
