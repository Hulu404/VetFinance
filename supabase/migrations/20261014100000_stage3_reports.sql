-- Stage 3 (Отчёты): article types and report attributes, benchmarks, obligation charges, stock.
-- Not applied to production yet. Every table has clinic_id and RLS (membership = full access to the clinic).
-- Cross-table references are composite (id, clinic_id). Money: bigint kopecks.
-- Writes into the new tables other than categories are done by the loaders and the team with the service
-- role (stock from Vetmanager comes later, obligations are entered in stage 4), so API roles only read.

-- categories: new types and the attributes the reports need ------------------------------------------------------
-- tax, obligation, capex, owner_draw are real bank payments that are not expenses of the P&L (see
-- docs/api-contract.md "Отчёты"): taxes have their own row, a loan payment is debt service, equipment is
-- replaced by amortization, a withdrawal by the owner is not a cost of the clinic.
alter table public.categories drop constraint if exists categories_type_check;
alter table public.categories
  add constraint categories_type_check
    check (type in ('income', 'variable', 'fixed', 'tax', 'obligation', 'capex', 'owner_draw')),
  -- the row of the "Норма" report the article belongs to (key of public.benchmarks), null: "Остальные статьи"
  add column norm_key text check (norm_key is null or norm_key ~ '^[a-z_]{1,40}$'),
  -- direct costs of a direction (function 18); null: common (acquiring commission, fixed costs)
  add column direction text check (direction in ('services', 'goods')),
  -- salaries of employees: the "ФОТ (оклады)" child row of the fixed costs
  add column payroll boolean not null default false,
  add constraint categories_norm_key_type_chk check (norm_key is null or type in ('variable', 'fixed')),
  add constraint categories_direction_type_chk check (direction is null or type = 'variable'),
  add constraint categories_payroll_type_chk check (not payroll or type in ('variable', 'fixed'));

-- benchmarks: norms of expense shares (percent of revenue). clinic_id null = the industry norm for clinics with
-- doctors_min..doctors_max doctors, readable by everyone; a row with clinic_id is the clinic's own override.
-- The own norm of a single article stays in categories.norm_min_pct / norm_max_pct and beats both. -------------
create table public.benchmarks (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid references public.clinics (id) on delete cascade,
  key text not null check (key ~ '^[a-z_]{1,40}$'),
  label text not null check (length(label) between 1 and 200),
  kind text not null check (kind in ('expense', 'profit')),
  min_pct numeric(5, 1) check (min_pct is null or min_pct >= 0),
  max_pct numeric(5, 1) check (max_pct is null or max_pct >= 0),
  doctors_min smallint not null default 2 check (doctors_min >= 0),
  doctors_max smallint not null default 6,
  sort smallint not null,
  source text not null check (length(source) between 1 and 300),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (min_pct is not null or max_pct is not null),
  check (min_pct is null or max_pct is null or min_pct <= max_pct),
  check (doctors_min <= doctors_max)
);
create unique index benchmarks_scope_key_uq on public.benchmarks (
  coalesce(clinic_id, '00000000-0000-0000-0000-000000000000'::uuid), key, doctors_min
);
create index benchmarks_clinic_idx on public.benchmarks (clinic_id) where clinic_id is not null;
create trigger benchmarks_updated_at before update on public.benchmarks
  for each row execute function public.set_updated_at();

-- industry norms for clinics with 2-6 doctors. Values: prototype v7 (estimate of the product owner, no published
-- source yet; replace with survey data before the pilot). Acquiring is 1.0-2.0 (not 1.5-2.5 of the prototype):
-- the tariff is charged on card payments only, so the share of the whole revenue is lower (owner decision 2026-10-14).
insert into public.benchmarks (key, label, kind, min_pct, max_pct, sort, source) values
  ('payroll', 'ФОТ врачей', 'expense', 22.0, 28.0, 1, 'prototype-v7 (оценка владельца продукта, не публикация)'),
  ('drugs', 'Препараты и расходники', 'expense', 20.0, 25.0, 2, 'prototype-v7 (оценка владельца продукта, не публикация)'),
  ('rent', 'Аренда и коммуналка', 'expense', 5.0, 10.0, 3, 'prototype-v7 (оценка владельца продукта, не публикация)'),
  ('lab', 'Лаборатории', 'expense', 3.0, 6.0, 4, 'prototype-v7 (оценка владельца продукта, не публикация)'),
  ('writeoff', 'Списание по сроку', 'expense', 0.0, 0.8, 5, 'prototype-v7 (оценка владельца продукта, не публикация)'),
  ('acquiring', 'Эквайринг', 'expense', 1.0, 2.0, 6, 'prototype-v7 (оценка владельца продукта, не публикация), границы изменены'),
  ('marketing', 'Маркетинг', 'expense', 3.0, 7.0, 7, 'prototype-v7 (оценка владельца продукта, не публикация)'),
  ('net_profit', 'Чистая прибыль', 'profit', 12.0, 20.0, 8, 'prototype-v7 (оценка владельца продукта, не публикация)');

-- obligations and their monthly charges (stage 4 adds loan terms and equipment data to `obligations`) -----------
create table public.obligations (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  code text not null check (length(code) between 1 and 100),
  name text not null check (length(name) between 1 and 200),
  kind text not null check (kind in ('loan', 'lease', 'equipment')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (clinic_id, code),
  unique (id, clinic_id)
);
create trigger obligations_updated_at before update on public.obligations
  for each row execute function public.set_updated_at();

-- What the P&L row "Обязательства и амортизация" sums: loan interest, a lease payment in full, amortization
-- (cost / life in months). The loan principal is not a cost. One row per obligation, month and kind.
create table public.obligation_charges (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  obligation_id uuid not null,
  month date not null check (extract(day from month) = 1),
  kind text not null check (kind in ('loan_interest', 'lease', 'amortization')),
  amount bigint not null check (amount >= 0),
  basis text not null default '' check (length(basis) <= 500),
  created_at timestamptz not null default now(),
  unique (clinic_id, obligation_id, month, kind),
  foreign key (obligation_id, clinic_id) references public.obligations (id, clinic_id) on delete cascade
);
create index obligation_charges_clinic_month_idx on public.obligation_charges (clinic_id, month);

-- stock (function 17). The Vetmanager loader does not read it yet: until the test account is available the
-- tables are filled from the seed of golden set 4. No personal data. ------------------------------------------
create table public.stock_items (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  external_id text not null,
  name text not null check (length(name) between 1 and 300),
  unit text not null default 'шт' check (length(unit) between 1 and 20),
  -- the last sale or write-off for a visit; null: no movement known
  last_movement_on date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (clinic_id, external_id),
  unique (id, clinic_id)
);
create trigger stock_items_updated_at before update on public.stock_items
  for each row execute function public.set_updated_at();

create table public.stock_batches (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  external_id text not null,
  item_id uuid not null,
  qty numeric(14, 3) not null check (qty >= 0),
  unit_cost bigint not null check (unit_cost >= 0),
  expires_on date,
  received_on date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (clinic_id, external_id),
  foreign key (item_id, clinic_id) references public.stock_items (id, clinic_id) on delete cascade
);
create index stock_batches_clinic_expires_idx on public.stock_batches (clinic_id, expires_on) where qty > 0;
create index stock_batches_item_idx on public.stock_batches (item_id);
create trigger stock_batches_updated_at before update on public.stock_batches
  for each row execute function public.set_updated_at();

create table public.stock_writeoffs (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  external_id text not null,
  date date not null,
  item_id uuid,
  item_name text not null check (length(item_name) between 1 and 300),
  qty numeric(14, 3) not null check (qty > 0),
  amount bigint not null check (amount >= 0),
  reason text not null check (reason in ('expired', 'damaged', 'other')),
  created_at timestamptz not null default now(),
  unique (clinic_id, external_id),
  foreign key (item_id, clinic_id) references public.stock_items (id, clinic_id) on delete set null (item_id)
);
create index stock_writeoffs_clinic_date_idx on public.stock_writeoffs (clinic_id, date);

-- consumption at the purchase price: sales and use at visits. A day total (kind = 'total', no item) is enough
-- for turnover; per-item rows (qty) are needed later for the write-off risk of a batch.
create table public.stock_consumption (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  date date not null,
  kind text not null default 'total' check (kind in ('sale', 'visit', 'total')),
  item_id uuid,
  qty numeric(14, 3) check (qty is null or qty >= 0),
  amount bigint not null check (amount >= 0),
  created_at timestamptz not null default now(),
  foreign key (item_id, clinic_id) references public.stock_items (id, clinic_id) on delete cascade
);
create unique index stock_consumption_key_uq on public.stock_consumption (
  clinic_id, date, kind, coalesce(item_id, '00000000-0000-0000-0000-000000000000'::uuid)
);

-- RLS ----------------------------------------------------------------------------------------------------------------
-- Same membership predicate as in stages 0 and 1; read-only for API roles (see the header).
do $$
declare
  tbl text;
  predicate constant text :=
    'clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid()))';
begin
  foreach tbl in array array['obligations', 'obligation_charges', 'stock_items', 'stock_batches',
                             'stock_writeoffs', 'stock_consumption']
  loop
    execute format('alter table public.%I enable row level security', tbl);
    execute format('revoke all on public.%I from anon', tbl);
    execute format('grant select on public.%I to authenticated', tbl);
    execute format('create policy %I on public.%I for select to authenticated using (%s)',
      tbl || '_select', tbl, predicate);
  end loop;
end;
$$;

-- benchmarks: the industry rows (clinic_id null) are visible to every signed-in user, own rows only to the clinic.
alter table public.benchmarks enable row level security;
revoke all on public.benchmarks from anon;
grant select on public.benchmarks to authenticated;
create policy benchmarks_select on public.benchmarks for select to authenticated
  using (
    clinic_id is null
    or clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid()))
  );
