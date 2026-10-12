-- Stage 1: categories, category rules, bank statement imports, duplicates, Vetmanager data, connections,
-- sync runs, acquiring reviews. Every table has clinic_id and RLS (membership = full access to the clinic).
-- Cross-table references are composite (id, clinic_id) so a row can never point into another clinic.
-- Money: bigint kopecks.

-- accounts: bank account number (links statement sections to accounts) and the end of the last statement -----
alter table public.accounts
  add column number text check (number is null or number ~ '^[0-9]{10,25}$'),
  add column last_statement_to date;
create unique index accounts_clinic_number_uq on public.accounts (clinic_id, number) where number is not null;

-- clinics: card acquiring rate in basis points (190 = 1.9%) ----------------------------------------------------
alter table public.clinics
  add column acquiring_rate_bp integer not null default 190 check (acquiring_rate_bp between 0 and 1000);

-- categories ---------------------------------------------------------------------------------------------------
create table public.categories (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  name text not null check (length(name) between 1 and 200),
  type text not null check (type in ('income', 'variable', 'fixed')),
  norm_min_pct numeric(5, 1) check (norm_min_pct is null or norm_min_pct >= 0),
  norm_max_pct numeric(5, 1) check (norm_max_pct is null or norm_max_pct >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (clinic_id, name),
  unique (id, clinic_id),
  check (norm_min_pct is null or norm_max_pct is null or norm_min_pct <= norm_max_pct)
);
create index categories_clinic_idx on public.categories (clinic_id);
create trigger categories_updated_at before update on public.categories
  for each row execute function public.set_updated_at();

-- category rules: the first matching rule (by sort_key) wins ----------------------------------------------------
create table public.category_rules (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  sort_key bigint generated always as identity,
  match text not null check (match in ('inn', 'text')),
  value text not null check (length(value) between 1 and 300),
  display_name text check (display_name is null or length(display_name) <= 300),
  direction text check (direction in ('in', 'out')),
  category_id uuid not null,
  created_at timestamptz not null default now(),
  unique (id, clinic_id),
  foreign key (category_id, clinic_id) references public.categories (id, clinic_id)
);
create unique index category_rules_key_uq
  on public.category_rules (clinic_id, match, value, coalesce(direction, ''));
create index category_rules_clinic_idx on public.category_rules (clinic_id, sort_key);

-- raw_events: one row per imported file / sync batch. Personal data of pet owners are never stored, so the
-- payload keeps only metadata (hash, size, period, counters), not the file or the API response itself. --------
create table public.raw_events (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  source text not null check (source in ('bank_statement', 'vetmanager')),
  file_hash text,
  byte_size integer check (byte_size is null or byte_size >= 0),
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (id, clinic_id)
);
create index raw_events_clinic_created_idx on public.raw_events (clinic_id, source, created_at desc);

-- transactions: counterparty, duplicate pairs, how the category was set ---------------------------------------------
alter table public.transactions
  add column counterparty_inn text not null default '',
  add column counterparty_name text not null default '',
  add column doc_number text,
  add column transfer_group text,
  add column duplicate_of uuid,
  add column duplicate_state text check (duplicate_state in ('pending', 'confirmed')),
  add column duplicate_dismissed boolean not null default false,
  add column category_source text check (category_source in ('rule', 'manual')),
  add column rule_id uuid,
  add column import_id uuid;
alter table public.transactions add constraint transactions_id_clinic_uq unique (id, clinic_id);
alter table public.transactions
  add foreign key (category_id, clinic_id) references public.categories (id, clinic_id),
  add foreign key (duplicate_of, clinic_id) references public.transactions (id, clinic_id),
  add foreign key (rule_id, clinic_id) references public.category_rules (id, clinic_id) on delete set null (rule_id),
  add foreign key (import_id, clinic_id) references public.raw_events (id, clinic_id);
alter table public.transactions add constraint transactions_duplicate_state_chk
  check (duplicate_state is null or status = 'duplicate');
create index transactions_clinic_status_date_idx on public.transactions (clinic_id, status, date desc);
create index transactions_clinic_inn_idx on public.transactions (clinic_id, counterparty_inn)
  where counterparty_inn <> '';
create index transactions_rule_idx on public.transactions (rule_id) where rule_id is not null;
create index transactions_duplicate_of_idx on public.transactions (duplicate_of) where duplicate_of is not null;

-- connections (Vetmanager and bank), the key is stored encrypted in connection_secrets ------------------------------
create table public.connections (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  type text not null check (type in ('vetmanager', 'bank')),
  address text check (address is null or length(address) <= 253),
  key_hint text check (key_hint is null or length(key_hint) <= 4),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (clinic_id, type),
  unique (id, clinic_id)
);
create trigger connections_updated_at before update on public.connections
  for each row execute function public.set_updated_at();

create or replace function public.create_default_connections() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.connections (clinic_id, type)
  values (new.id, 'vetmanager'), (new.id, 'bank')
  on conflict (clinic_id, type) do nothing;
  return new;
end;
$$;
create trigger clinics_default_connections after insert on public.clinics
  for each row execute function public.create_default_connections();
insert into public.connections (clinic_id, type)
select c.id, t.type from public.clinics c cross join (values ('vetmanager'), ('bank')) as t (type)
on conflict (clinic_id, type) do nothing;

-- The ciphertext of the API key is not granted to any API role: only these functions (membership checked) and
-- the service role (nightly worker) can reach it. The key itself is encrypted by the backend before it gets here.
create table public.connection_secrets (
  connection_id uuid primary key references public.connections (id) on delete cascade,
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  key_cipher text not null,
  updated_at timestamptz not null default now()
);
alter table public.connection_secrets enable row level security;
revoke all on public.connection_secrets from anon, authenticated;

create or replace function public.set_connection_secret(p_connection uuid, p_cipher text) returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not exists (
    select 1 from public.connections c
    join public.memberships m on m.clinic_id = c.clinic_id
    where c.id = p_connection and m.user_id = (select auth.uid())
  ) then
    raise exception 'forbidden' using errcode = '42501';
  end if;
  insert into public.connection_secrets (connection_id, clinic_id, key_cipher)
  select c.id, c.clinic_id, p_cipher from public.connections c where c.id = p_connection
  on conflict (connection_id) do update set key_cipher = excluded.key_cipher, updated_at = now();
end;
$$;

create or replace function public.get_connection_secret(p_connection uuid) returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  cipher text;
begin
  select s.key_cipher into cipher
  from public.connection_secrets s
  join public.memberships m on m.clinic_id = s.clinic_id
  where s.connection_id = p_connection and m.user_id = (select auth.uid());
  return cipher;
end;
$$;
revoke all on function public.set_connection_secret(uuid, text), public.get_connection_secret(uuid)
  from public, anon;
grant execute on function public.set_connection_secret(uuid, text), public.get_connection_secret(uuid)
  to authenticated;

-- sync_runs ----------------------------------------------------------------------------------------------------------
create table public.sync_runs (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  connection_id uuid not null,
  status text not null default 'running' check (status in ('running', 'success', 'partial', 'failed')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  error_code text check (error_code in ('invalid_key', 'unreachable', 'rate_limited', 'unknown')),
  counts jsonb,
  foreign key (connection_id, clinic_id) references public.connections (id, clinic_id) on delete cascade
);
create index sync_runs_connection_started_idx on public.sync_runs (clinic_id, connection_id, started_at desc);

-- Vetmanager data. No data of pet owners: only doctors (code and name), visits, invoices, payments. ----------------
create table public.doctors (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  external_id text not null,
  code text not null,
  name text not null,
  created_at timestamptz not null default now(),
  unique (clinic_id, external_id),
  unique (clinic_id, code),
  unique (id, clinic_id)
);

create table public.visits (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  external_id text not null,
  date date not null,
  doctor_id uuid,
  created_at timestamptz not null default now(),
  unique (clinic_id, external_id),
  foreign key (doctor_id, clinic_id) references public.doctors (id, clinic_id)
);
create index visits_clinic_date_idx on public.visits (clinic_id, date);

create table public.sales (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  external_id text not null,
  date date not null,
  status text not null check (status in ('exec', 'save')),
  amount bigint not null,
  lines jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (clinic_id, external_id)
);
create index sales_clinic_date_idx on public.sales (clinic_id, date);
create trigger sales_updated_at before update on public.sales
  for each row execute function public.set_updated_at();

create table public.payments (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  external_id text not null,
  date date not null,
  amount bigint not null,
  method text not null check (method in ('cash', 'card')),
  invoice_external_id text,
  transaction_id uuid,
  created_at timestamptz not null default now(),
  unique (clinic_id, external_id),
  foreign key (transaction_id, clinic_id) references public.transactions (id, clinic_id)
);
create index payments_clinic_method_date_idx on public.payments (clinic_id, method, date);

-- acquiring: a reconciliation row marked as reviewed (the key is the first sale day of the row) -----------------------
create table public.acquiring_reviews (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  sale_date date not null,
  note text check (note is null or length(note) <= 200),
  reviewed_at timestamptz not null default now(),
  unique (clinic_id, sale_date)
);

-- RLS ----------------------------------------------------------------------------------------------------------------
-- One policy per command, all with the same membership predicate as in stage 0.
do $$
declare
  spec record;
  cmd text;
  predicate constant text :=
    'clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid()))';
begin
  for spec in
    select * from (values
      ('categories', array['select', 'update']),
      ('category_rules', array['select', 'insert', 'update', 'delete']),
      ('raw_events', array['select', 'insert']),
      ('connections', array['select', 'update']),
      ('sync_runs', array['select', 'insert', 'update']),
      ('doctors', array['select']),
      ('visits', array['select']),
      ('sales', array['select']),
      ('payments', array['select']),
      ('acquiring_reviews', array['select', 'insert', 'update'])
    ) as t (tbl, cmds)
  loop
    execute format('alter table public.%I enable row level security', spec.tbl);
    execute format('revoke all on public.%I from anon', spec.tbl);
    foreach cmd in array spec.cmds loop
      execute format('grant %s on public.%I to authenticated', cmd, spec.tbl);
      if cmd = 'select' or cmd = 'delete' then
        execute format('create policy %I on public.%I for %s to authenticated using (%s)',
          spec.tbl || '_' || cmd, spec.tbl, cmd, predicate);
      elsif cmd = 'insert' then
        execute format('create policy %I on public.%I for insert to authenticated with check (%s)',
          spec.tbl || '_insert', spec.tbl, predicate);
      else
        execute format('create policy %I on public.%I for update to authenticated using (%s) with check (%s)',
          spec.tbl || '_update', spec.tbl, predicate, predicate);
      end if;
    end loop;
  end loop;
end;
$$;
