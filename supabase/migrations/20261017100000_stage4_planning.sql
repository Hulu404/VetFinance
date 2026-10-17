-- Stage 4: payment calendar and obligations (functions 21-23, 43). docs/api-contract.md, "Планирование".
-- Not applied anywhere yet. Every table has clinic_id and RLS with the same membership predicate as stages 0-3.
--
-- 1. obligations get the terms the engine calculates charges and payments from (engine/obligations.py);
--    obligation_charges stay the frozen history: rows of past months are written once (when the terms change),
--    the engine fills the months that have no row.
-- 2. planned_payments: one-off payments entered by hand (source `manual` in the calendar).
-- 3. counterparties: the deferral a counterparty allows (default 0: the payment is not moved).
-- API roles write only what the user edits in the app: obligations, their frozen charges, planned payments,
-- counterparty terms. Supabase grants everything (TRUNCATE included) to new tables, so privileges are reset first.

-- obligations: terms -------------------------------------------------------------------------------------------------
alter table public.obligations
  add column lender text check (lender is null or length(lender) <= 80),
  add column counterparty_inn text check (counterparty_inn is null or counterparty_inn ~ '^[0-9]{10}([0-9]{2})?$'),
  -- loan: original sum; lease: sum of all payments of the contract
  add column principal bigint check (principal is null or principal > 0),
  -- annual rate in basis points (1200 = 12%), loans only
  add column annual_rate_bp integer check (annual_rate_bp is null or annual_rate_bp between 0 and 10000),
  add column payment bigint check (payment is null or payment > 0),
  add column payment_day integer check (payment_day is null or payment_day between 1 and 31),
  add column first_payment_date date,
  add column payments_total integer check (payments_total is null or payments_total between 1 and 600),
  -- debt (loan) or sum left to pay (lease) before the first payment of the schedule; null: principal / payment x total
  add column start_balance bigint check (start_balance is null or start_balance >= 0),
  add column cost bigint check (cost is null or cost > 0),
  add column life_years integer check (life_years is null or life_years between 1 and 30),
  add column in_service_date date,
  -- first of a month: no charges before it (an obligation entered in the app does not rewrite past reports)
  add column effective_from date check (effective_from is null or extract(day from effective_from) = 1),
  -- first of a month: closed from this month, payments and charges from it on disappear, history stays
  add column closed_from date check (closed_from is null or extract(day from closed_from) = 1);

-- planned (manual) payments ------------------------------------------------------------------------------------------
create table public.planned_payments (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  date date not null,
  name text not null check (length(name) between 1 and 80),
  amount bigint not null check (amount > 0 and amount <= 1000000000000),
  category_id uuid,
  max_deferral_days integer not null default 0 check (max_deferral_days between 0 and 30),
  created_at timestamptz not null default now(),
  foreign key (category_id, clinic_id) references public.categories (id, clinic_id)
);
create index planned_payments_clinic_date_idx on public.planned_payments (clinic_id, date);

-- deferral of counterparties -----------------------------------------------------------------------------------------
-- key: the INN, or "n-" and a hash of the name when the statement has no INN (engine/planning_inputs.py)
create table public.counterparties (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  key text not null check (length(key) between 1 and 40),
  name text not null check (length(name) between 1 and 300),
  max_deferral_days integer not null default 0 check (max_deferral_days between 0 and 30),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (clinic_id, key)
);
create trigger counterparties_updated_at before update on public.counterparties
  for each row execute function public.set_updated_at();

-- RLS and privileges -------------------------------------------------------------------------------------------------
do $$
declare
  spec record;
  op text;
  predicate constant text :=
    'clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid()))';
begin
  for spec in
    select * from (values
      ('obligations', array['select', 'insert', 'update']),
      ('obligation_charges', array['select', 'insert']),
      ('planned_payments', array['select', 'insert', 'delete']),
      ('counterparties', array['select', 'insert', 'update'])
    ) as t (tbl, cmds)
  loop
    execute format('alter table public.%I enable row level security', spec.tbl);
    execute format('revoke all on public.%I from anon', spec.tbl);
    execute format('revoke all on public.%I from authenticated', spec.tbl);
    foreach op in array spec.cmds loop
      execute format('grant %s on public.%I to authenticated', op, spec.tbl);
      if op in ('select', 'delete') then
        if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = spec.tbl
                       and policyname = spec.tbl || '_' || op) then
          execute format('create policy %I on public.%I for %s to authenticated using (%s)',
            spec.tbl || '_' || op, spec.tbl, op, predicate);
        end if;
      elsif op = 'insert' then
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
