-- Additive runtime migrations, safe against a loaded dataset.
create index if not exists events_company_id on events(company_id,id);
alter table reminders add column if not exists node_id text;
alter table reminders add column if not exists status text default 'pending';
alter table reminders add column if not exists provider_message_id text;
alter table reminders add column if not exists space_id text;
alter table reminders add column if not exists recipient text;
create table if not exists channel_inbox (
  provider_id text primary key, company_id text, run_id text, payload jsonb not null,
  status text not null default 'pending', created_at timestamptz default now()
);
alter table channel_inbox add column if not exists claimed_at timestamptz;
