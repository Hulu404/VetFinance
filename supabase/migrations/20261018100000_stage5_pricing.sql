-- Stage 5: price list and service cost (functions 11, 12, 33, 34). docs/api-contract.md, "Прайс услуг", "Аналитика".
-- Not applied anywhere yet. Every table has clinic_id and RLS with the same membership predicate as stages 0-4.
--
-- 1. services: the list of services. `vetmanager` rows are written by the synchronisation (service connection),
--    `manual` rows by the owner in the app (name, group, price).
-- 2. service_settings (minutes in the cabinet, percent to the doctor) and techcards with lines (stock item, part, qty).
-- 3. doctors.hours_per_week and clinics.avg_visit_minutes: the inputs of the fallback "by doctors" load.
-- 4. rooms, their weekly schedule and booked minutes: written only by the synchronisation, when Vetmanager gives them.
-- 5. categories.in_service_recipes / doctor_percent: flags of articles for the hour cost and the clinic-average percent.
-- Variable names of the DO block avoid the column names of system views (pg_policies has `cmd`, `policyname`, ...).
-- Supabase grants everything (TRUNCATE included) to new tables, so privileges are reset first.

-- services -----------------------------------------------------------------------------------------------------------
create table public.services (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  source text not null check (source in ('vetmanager', 'manual')),
  external_id text,
  name text not null check (length(name) between 1 and 300),
  group_name text check (group_name is null or length(group_name) between 1 and 80),
  -- kopecks: the price the owner entered (manual services); null for services from Vetmanager
  manual_price bigint check (manual_price is null or (manual_price > 0 and manual_price <= 10000000000)),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, clinic_id),
  check ((source = 'vetmanager' and external_id is not null and manual_price is null)
         or (source = 'manual' and external_id is null and manual_price is not null))
);
create unique index services_clinic_external_idx on public.services (clinic_id, external_id) where external_id is not null;
create index services_clinic_name_idx on public.services (clinic_id, lower(name));
create trigger services_updated_at before update on public.services
  for each row execute function public.set_updated_at();

-- service settings and techcards -------------------------------------------------------------------------------------
create table public.service_settings (
  service_id uuid primary key,
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  -- null: the average visit length of the clinic is used
  minutes integer check (minutes is null or minutes between 1 and 1440),
  -- percent of the price to the doctor in basis points (3000 = 30%); null: the clinic average
  doctor_pct_bp integer check (doctor_pct_bp is null or doctor_pct_bp between 0 and 10000),
  updated_at timestamptz not null default now(),
  foreign key (service_id, clinic_id) references public.services (id, clinic_id) on delete cascade
);
create trigger service_settings_updated_at before update on public.service_settings
  for each row execute function public.set_updated_at();

-- a row here is a RECORDED techcard (possibly without lines); no row means "no techcard"
create table public.techcards (
  service_id uuid primary key,
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  updated_at timestamptz not null default now(),
  unique (service_id, clinic_id),
  foreign key (service_id, clinic_id) references public.services (id, clinic_id) on delete cascade
);
create trigger techcards_updated_at before update on public.techcards
  for each row execute function public.set_updated_at();

create table public.techcard_lines (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  service_id uuid not null,
  item_id uuid not null,
  part text not null check (part in ('drugs', 'anesthesia', 'supplies')),
  qty numeric(14, 3) not null check (qty > 0 and qty <= 1000000),
  sort_order integer not null default 0,
  unique (service_id, item_id),
  foreign key (service_id, clinic_id) references public.techcards (service_id, clinic_id) on delete cascade,
  foreign key (item_id, clinic_id) references public.stock_items (id, clinic_id) on delete cascade
);
create index techcard_lines_clinic_idx on public.techcard_lines (clinic_id, service_id);

-- hours of doctors, average visit length, flags of articles ----------------------------------------------------------
alter table public.doctors
  add column hours_per_week numeric(3, 1) check (hours_per_week is null or (hours_per_week between 0 and 80
                                                  and hours_per_week * 2 = trunc(hours_per_week * 2)));
alter table public.clinics
  add column avg_visit_minutes integer not null default 30 check (avg_visit_minutes between 5 and 240);
alter table public.categories
  add column in_service_recipes boolean not null default false,
  add column doctor_percent boolean not null default false;
update public.categories set in_service_recipes = true where name = 'Расходные материалы';
update public.categories set doctor_percent = true where name = 'Проценты врачам';

-- rooms (from Vetmanager, when it gives schedules) -------------------------------------------------------------------
create table public.rooms (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  external_id text not null,
  name text not null check (length(name) between 1 and 200),
  -- false: Vetmanager gave no schedule of this room (one such room switches the screen to the "by doctors" mode)
  has_schedule boolean not null default false,
  created_at timestamptz not null default now(),
  unique (clinic_id, external_id),
  unique (id, clinic_id)
);

create table public.room_schedule_slots (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  room_id uuid not null,
  weekday integer not null check (weekday between 0 and 6),
  from_min integer not null check (from_min between 0 and 1440),
  to_min integer not null check (to_min between 0 and 1440),
  check (to_min > from_min),
  foreign key (room_id, clinic_id) references public.rooms (id, clinic_id) on delete cascade
);
create index room_schedule_slots_room_idx on public.room_schedule_slots (clinic_id, room_id);

create table public.room_bookings (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id) on delete cascade,
  external_id text not null,
  date date not null,
  room_id uuid not null,
  minutes integer not null check (minutes between 1 and 1440),
  unique (clinic_id, external_id),
  foreign key (room_id, clinic_id) references public.rooms (id, clinic_id) on delete cascade
);
create index room_bookings_clinic_date_idx on public.room_bookings (clinic_id, date);

-- RLS and privileges -------------------------------------------------------------------------------------------------
do $$
declare
  spec record;
  op text;
  predicate constant text :=
    'clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid()))';
  manual_only constant text := ' and source = ''manual''';
begin
  for spec in
    select * from (values
      ('services', array['select', 'insert', 'update', 'delete']),
      ('service_settings', array['select', 'insert', 'update']),
      ('techcards', array['select', 'insert', 'update']),
      ('techcard_lines', array['select', 'insert', 'delete']),
      ('rooms', array['select']),
      ('room_schedule_slots', array['select']),
      ('room_bookings', array['select'])
    ) as t (tbl, ops)
  loop
    execute format('alter table public.%I enable row level security', spec.tbl);
    execute format('revoke all on public.%I from anon', spec.tbl);
    execute format('revoke all on public.%I from authenticated', spec.tbl);
    foreach op in array spec.ops loop
      execute format('grant %s on public.%I to authenticated', op, spec.tbl);
      if op = 'select' then
        execute format('create policy %I on public.%I for select to authenticated using (%s)',
          spec.tbl || '_select', spec.tbl, predicate);
      elsif op = 'delete' then
        execute format('create policy %I on public.%I for delete to authenticated using (%s%s)',
          spec.tbl || '_delete', spec.tbl, predicate, case when spec.tbl = 'services' then manual_only else '' end);
      elsif op = 'insert' then
        execute format('create policy %I on public.%I for insert to authenticated with check (%s%s)',
          spec.tbl || '_insert', spec.tbl, predicate, case when spec.tbl = 'services' then manual_only else '' end);
      else
        execute format('create policy %I on public.%I for update to authenticated using (%s%s) with check (%s%s)',
          spec.tbl || '_update', spec.tbl, predicate, case when spec.tbl = 'services' then manual_only else '' end,
          predicate, case when spec.tbl = 'services' then manual_only else '' end);
      end if;
    end loop;
  end loop;
end;
$$;

-- doctors: the owner may change only the hours of reception (column grant), the rest comes from Vetmanager.
-- Supabase granted UPDATE on the whole table by default; with the policy below it would open every column.
revoke update on public.doctors from authenticated, anon;
grant update (hours_per_week) on public.doctors to authenticated;
create policy doctors_update on public.doctors for update to authenticated
  using (clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())))
  with check (clinic_id in (select m.clinic_id from public.memberships m where m.user_id = (select auth.uid())));
