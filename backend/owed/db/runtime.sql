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
alter table pay_tokens add column if not exists run_id text;
create unique index if not exists payments_solana_signature on payments ((receipt->>'signature')) where rail='solana';
create table if not exists customer_agents(company_id text,customer_id text,address text,primary key(company_id,customer_id));
alter table decisions add column if not exists payload jsonb default '{}';
alter table decisions add column if not exists deadline timestamptz;
alter table decisions add column if not exists default_option text;
create table if not exists action_jobs(decision_id text primary key,status text default 'pending',created_at timestamptz default now(),claimed_at timestamptz);
create table if not exists bill_deferrals(company_id text,bill_id text,due_date date,run_id text,primary key(company_id,bill_id));
create table if not exists draw_holds(company_id text primary key,run_id text,amount numeric(14,2));
create table if not exists forecast_payments(payment_id text primary key);
