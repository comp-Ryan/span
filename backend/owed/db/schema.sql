-- Owed schema: flattened Intuit QuickBooks hackathon dataset + runtime tables.
-- Money: numeric(14,2). IDs are company-scoped, so every PK includes company_id.

create extension if not exists timescaledb;

create table if not exists companies (
  company_id text primary key,
  display_name text not null,
  industry_naics text, industry_title text,
  profile text, archetype text, size_tier text,
  business_status text, distressed boolean,
  dataset_id text, world_dir text,
  fiscal_year_start text,
  state text,
  cash numeric(14,2), revenue numeric(14,2), profit numeric(14,2),
  receivables numeric(14,2), payables numeric(14,2), debt numeric(14,2),
  period_start date, period_end date
);

create table if not exists customers (
  company_id text, id text, display_name text, company_name text,
  email text, phone text, state text,
  payment_terms text, payment_terms_days int, credit_limit numeric(14,2),
  joined_date date, ended_date date,
  primary key (company_id, id)
);

create table if not exists vendors (
  company_id text, id text, display_name text, email text, phone text,
  payment_terms text, payment_terms_days int, supply_role text, joined_date date,
  primary key (company_id, id)
);

create table if not exists employees (
  company_id text, id text, display_name text, job_title text,
  hired_date date, released_date date, weekly_wage numeric(14,2),
  primary key (company_id, id)
);

create table if not exists invoices (
  company_id text, id text, doc_number text,
  customer_id text, customer_name text,
  txn_date date, due_date date,
  total_amount numeric(14,2),
  deposit_applied numeric(14,2), retainage numeric(14,2),
  project_id text, memo text,
  primary key (company_id, id)
);
create index if not exists invoices_cust on invoices (company_id, customer_id);
create index if not exists invoices_due on invoices (company_id, due_date);

create table if not exists invoice_lines (
  company_id text, invoice_id text, line_num int,
  item_id text, item_name text, description text,
  quantity numeric(14,3), unit_price numeric(14,2), amount numeric(14,2),
  primary key (company_id, invoice_id, line_num)
);

create table if not exists customer_payments (
  company_id text, id text, customer_id text, customer_name text,
  txn_date date, amount numeric(14,2), unapplied numeric(14,2), project_id text,
  primary key (company_id, id)
);

create table if not exists payment_applications (
  company_id text, payment_id text, document_id text, amount numeric(14,2),
  primary key (company_id, payment_id, document_id)
);
create index if not exists payapp_doc on payment_applications (company_id, document_id);

create table if not exists sales_receipts (
  company_id text, id text, customer_id text, txn_date date, total_amount numeric(14,2),
  primary key (company_id, id)
);

create table if not exists bills (
  company_id text, id text, doc_number text,
  vendor_id text, vendor_name text, expense_kind text, cost_category text,
  txn_date date, due_date date, total_amount numeric(14,2), project_id text, memo text,
  primary key (company_id, id)
);
create index if not exists bills_due on bills (company_id, due_date);

create table if not exists bill_payments (
  company_id text, id text, vendor_id text, vendor_name text, txn_date date, amount numeric(14,2),
  primary key (company_id, id)
);

create table if not exists bill_payment_applications (
  company_id text, payment_id text, document_id text, amount numeric(14,2),
  primary key (company_id, payment_id, document_id)
);
create index if not exists billpayapp_doc on bill_payment_applications (company_id, document_id);

create table if not exists payroll_runs (
  company_id text, id text, run_date date, total_amount numeric(14,2),
  primary key (company_id, id)
);
create index if not exists payroll_date on payroll_runs (company_id, run_date);

create table if not exists payroll_lines (
  company_id text, run_id text, employee_id text, employee_name text, gross_amount numeric(14,2),
  primary key (company_id, run_id, employee_id)
);

create table if not exists bank_transactions (
  company_id text, id text, txn_date date, amount numeric(14,2), direction text,
  running_balance numeric(14,2), source_document_id text, memo text, kind text,
  primary key (company_id, id)
);
create index if not exists bank_date on bank_transactions (company_id, txn_date);

create table if not exists journal_entries (
  company_id text, id text, doc_number text, purpose text, txn_date date, memo text, project_id text,
  primary key (company_id, id)
);
create table if not exists journal_lines (
  company_id text, je_id text, line_num int, account_id text, account_name text,
  description text, debit numeric(14,2), credit numeric(14,2),
  customer_id text, vendor_id text, document_id text,
  primary key (company_id, je_id, line_num)
);
create index if not exists jl_doc on journal_lines (company_id, document_id);

-- Secondary entities kept as JSON documents.
create table if not exists docs (
  company_id text, entity text, id text, doc jsonb,
  primary key (company_id, entity, id)
);

create table if not exists reports (
  company_id text, name text, doc jsonb,
  primary key (company_id, name)
);

create table if not exists ar_aging (
  company_id text, document_id text, party text, due_date date, days_past_due int, bucket text, balance numeric(14,2),
  primary key (company_id, document_id)
);
create table if not exists ap_aging (
  company_id text, document_id text, party text, due_date date, days_past_due int, bucket text, balance numeric(14,2),
  primary key (company_id, document_id)
);

-- Derived: one row per invoice with settlement facts. Rebuilt by the loader.
create table if not exists invoice_facts (
  company_id text, invoice_id text, customer_id text,
  txn_date date, due_date date, total_amount numeric(14,2),
  paid_amount numeric(14,2), first_paid_date date, last_paid_date date,
  written_off numeric(14,2), open_balance numeric(14,2),
  days_late int,           -- last_paid_date - due_date, null if unpaid
  status text,             -- paid | open | written_off | partial
  primary key (company_id, invoice_id)
);

-- Runtime tables
create table if not exists runs (
  run_id text primary key, company_id text, question text, source text, intent text,
  started_at timestamptz default now(), ended_at timestamptz, status text default 'open',
  answer_title text, report_id text
);
create table if not exists events (
  id bigserial, run_id text, company_id text, ts timestamptz default now(),
  event text, data jsonb,
  primary key (id)
);
create index if not exists events_run on events (run_id, id);
create table if not exists decisions (
  decision_id text primary key, run_id text, node_id text, prompt text, options jsonb,
  resolved text, resolved_at timestamptz, created_at timestamptz default now()
);
create table if not exists reminders (
  reminder_id text primary key, run_id text, company_id text, invoice_id text, customer_id text,
  channel text, body text, tone text, draft_source text, pay_token text, sent_at timestamptz
);
create table if not exists negotiations (
  negotiation_id text primary key, run_id text, company_id text, invoice_id text,
  status text, rounds jsonb default '[]', agreement jsonb, created_at timestamptz default now()
);
create table if not exists payments (
  payment_id text primary key, pay_token text, company_id text, invoice_id text,
  rail text, amount numeric(14,2), paid_at timestamptz, receipt jsonb
);
create table if not exists pay_tokens (
  pay_token text primary key, company_id text, invoice_id text, amount numeric(14,2), status text default 'unpaid',
  negotiation_id text, run_id text, created_at timestamptz default now()
);
alter table pay_tokens add column if not exists run_id text;
create table if not exists generated_reports (
  report_id text primary key, run_id text, company_id text, generated_at timestamptz default now(), doc jsonb
);

-- Cash projection as a hypertable (one row per company/day/scenario).
create table if not exists cash_projection (
  company_id text, scenario text, day date, inflow numeric(14,2), outflow numeric(14,2), balance numeric(14,2),
  computed_at timestamptz default now()
);
select create_hypertable('cash_projection', 'day', if_not_exists => true, migrate_data => true);
