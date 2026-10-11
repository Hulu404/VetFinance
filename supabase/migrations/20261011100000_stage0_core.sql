-- Stage 0: clinics, memberships, accounts, transactions with RLS.
-- Money: bigint kopecks. Every table has clinic_id. No roles: membership = full access to the clinic.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- clinics -------------------------------------------------------------------
create table public.clinics (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(name) between 1 and 200),
  legal_entity text,
  tax_regime text,
  timezone text not null default 'Europe/Moscow',
  safe_balance bigint not null default 0 check (safe_balance >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create trigger clinics_updated_at before update on public.clinics
  for each row execute function public.set_updated_at();

-- memberships (one row per user per clinic; no roles) -------------------------
create table public.memberships (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (user_id, clinic_id)
);
create index memberships_user_idx on public.memberships (user_id);
create index memberships_clinic_idx on public.memberships (clinic_id);

-- accounts ---------------------------------------------------------------------
create table public.accounts (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  name text not null check (length(name) between 1 and 200),
  kind text not null check (kind in ('bank', 'cash')),
  opening_balance bigint not null default 0,
  opening_date date not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index accounts_clinic_idx on public.accounts (clinic_id);
create trigger accounts_updated_at before update on public.accounts
  for each row execute function public.set_updated_at();

-- transactions -----------------------------------------------------------------
-- category_id has no FK yet: the categories table arrives in stage 1.
create table public.transactions (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  account_id uuid not null references public.accounts (id) on delete restrict,
  date date not null,
  description text not null default '',
  amount bigint not null,
  kind text not null check (kind in ('in', 'out', 'transfer')),
  source text not null check (source in ('bank', 'vetmanager', 'bot', 'manual')),
  external_id text,
  dedup_hash text,
  category_id uuid,
  status text not null default 'ok' check (status in ('ok', 'check', 'duplicate')),
  created_at timestamptz not null default now()
);
create index transactions_clinic_date_idx on public.transactions (clinic_id, date desc);
create index transactions_account_date_idx on public.transactions (account_id, date);
create index transactions_clinic_hash_idx on public.transactions (clinic_id, dedup_hash)
  where dedup_hash is not null;
create unique index transactions_source_external_uq
  on public.transactions (clinic_id, source, external_id)
  where external_id is not null;

-- A transaction must reference an account of the same clinic.
create or replace function public.check_transaction_account() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if not exists (
    select 1 from public.accounts a where a.id = new.account_id and a.clinic_id = new.clinic_id
  ) then
    raise exception 'account % does not belong to clinic %', new.account_id, new.clinic_id;
  end if;
  return new;
end;
$$;
create trigger transactions_account_check before insert or update on public.transactions
  for each row execute function public.check_transaction_account();

-- RLS ---------------------------------------------------------------------------
alter table public.clinics enable row level security;
alter table public.memberships enable row level security;
alter table public.accounts enable row level security;
alter table public.transactions enable row level security;

revoke all on public.clinics, public.memberships, public.accounts, public.transactions from anon;
grant select, update on public.clinics to authenticated;
grant select on public.memberships to authenticated;
grant select, insert, update on public.accounts to authenticated;
grant select, insert, update on public.transactions to authenticated;

-- memberships: a user sees only their own rows (no self-reference, so no recursion).
create policy memberships_select on public.memberships for select to authenticated
  using (user_id = (select auth.uid()));

-- clinics: select/update for members. Creation is done by the service role (seed, onboarding).
create policy clinics_select on public.clinics for select to authenticated
  using (id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())));
create policy clinics_update on public.clinics for update to authenticated
  using (id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())))
  with check (id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())));

-- accounts and transactions: select/insert/update by membership. No delete in MVP.
create policy accounts_select on public.accounts for select to authenticated
  using (clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())));
create policy accounts_insert on public.accounts for insert to authenticated
  with check (clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())));
create policy accounts_update on public.accounts for update to authenticated
  using (clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())))
  with check (clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())));

create policy transactions_select on public.transactions for select to authenticated
  using (clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())));
create policy transactions_insert on public.transactions for insert to authenticated
  with check (clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())));
create policy transactions_update on public.transactions for update to authenticated
  using (clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())))
  with check (clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())));
