-- RLS isolation check for the stage 3 tables (reports). Run after seed.sql (clinics A and B, users test-a@ and
-- test-b@) and after the stage 3 migration. Execute as postgres (SQL editor / MCP execute_sql).
-- Raises an exception on failure; rolls back, nothing stays in the database.
begin;
do $$
declare
  ua uuid := (select id from auth.users where email = 'test-a@vetfinance.test');
  ub uuid := (select id from auth.users where email = 'test-b@vetfinance.test');
  clinic_a uuid := (select m.clinic_id from public.memberships m where m.user_id = ua limit 1);
  clinic_b uuid := (select m.clinic_id from public.memberships m where m.user_id = ub limit 1);
  tbl text;
  n int;
  obl_a uuid := gen_random_uuid();
  obl_b uuid := gen_random_uuid();
  item_a uuid := gen_random_uuid();
  item_b uuid := gen_random_uuid();
begin
  if ua is null or ub is null or clinic_a is null or clinic_b is null then
    raise exception 'test users or clinics are missing';
  end if;

  -- one row per clinic in every new table (as the service role)
  insert into public.obligations (id, clinic_id, code, name, kind) values
    (obl_a, clinic_a, 'rls-a', 'rls check a', 'loan'), (obl_b, clinic_b, 'rls-b', 'rls check b', 'loan');
  insert into public.obligation_charges (clinic_id, obligation_id, month, kind, amount) values
    (clinic_a, obl_a, date '2026-09-01', 'loan_interest', 100), (clinic_b, obl_b, date '2026-09-01', 'loan_interest', 100);
  insert into public.stock_items (id, clinic_id, external_id, name) values
    (item_a, clinic_a, 'rls-a', 'rls a'), (item_b, clinic_b, 'rls-b', 'rls b');
  insert into public.stock_batches (clinic_id, external_id, item_id, qty, unit_cost) values
    (clinic_a, 'rls-a', item_a, 1, 100), (clinic_b, 'rls-b', item_b, 1, 100);
  insert into public.stock_writeoffs (clinic_id, external_id, date, item_name, qty, amount, reason) values
    (clinic_a, 'rls-a', date '2026-09-01', 'rls a', 1, 100, 'expired'),
    (clinic_b, 'rls-b', date '2026-09-01', 'rls b', 1, 100, 'expired');
  insert into public.stock_consumption (clinic_id, date, amount) values
    (clinic_a, date '2026-09-01', 100), (clinic_b, date '2026-09-01', 100);
  insert into public.benchmarks (clinic_id, key, label, kind, min_pct, max_pct, doctors_min, doctors_max, sort, source) values
    (clinic_a, 'rls_a', 'rls a', 'expense', 1, 2, 2, 6, 90, 'rls'), (clinic_b, 'rls_b', 'rls b', 'expense', 1, 2, 2, 6, 91, 'rls');

  perform set_config('request.jwt.claims', json_build_object('sub', ua, 'role', 'authenticated')::text, true);
  set local role authenticated;

  -- 1. only rows of the user's clinic
  foreach tbl in array array['obligations', 'obligation_charges', 'stock_items', 'stock_batches',
                             'stock_writeoffs', 'stock_consumption'] loop
    execute format('select count(*) from public.%I where clinic_id <> $1', tbl) into n using clinic_a;
    if n <> 0 then raise exception 'user A sees foreign rows in %', tbl; end if;
    execute format('select count(*) from public.%I where clinic_id = $1', tbl) into n using clinic_a;
    if n = 0 then raise exception 'user A does not see own rows in %', tbl; end if;
  end loop;

  -- 2. benchmarks: industry rows (clinic_id null) are visible, rows of another clinic are not
  select count(*) into n from public.benchmarks where clinic_id is null;
  if n < 8 then raise exception 'industry benchmarks are not visible (% rows)', n; end if;
  select count(*) into n from public.benchmarks where clinic_id = clinic_b;
  if n <> 0 then raise exception 'user A sees benchmarks of clinic B'; end if;
  select count(*) into n from public.benchmarks where clinic_id = clinic_a;
  if n <> 1 then raise exception 'user A does not see own benchmark'; end if;

  -- 3. API roles do not write into the new tables
  begin
    insert into public.obligations (clinic_id, code, name, kind) values (clinic_a, 'hack', 'hack', 'loan');
    raise exception 'user A inserted an obligation';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.stock_items (clinic_id, external_id, name) values (clinic_a, 'hack', 'hack');
    raise exception 'user A inserted a stock item';
  exception when insufficient_privilege then null;
  end;
  begin
    update public.benchmarks set max_pct = 99 where clinic_id is null;
    raise exception 'user A changed an industry benchmark';
  exception when insufficient_privilege then null;
  end;
  reset role;

  perform set_config('request.jwt.claims', json_build_object('sub', ub, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n from public.stock_items where clinic_id = clinic_a;
  if n <> 0 then raise exception 'user B sees stock items of clinic A'; end if;
  reset role;

  -- 4. rules of the new article attributes
  insert into public.categories (clinic_id, name, type) values (clinic_a, 'rls-tax', 'tax');
  begin
    insert into public.categories (clinic_id, name, type, direction) values (clinic_a, 'rls-bad-dir', 'fixed', 'goods');
    raise exception 'direction was accepted on a fixed article';
  exception when check_violation then null;
  end;
  begin
    insert into public.categories (clinic_id, name, type) values (clinic_a, 'rls-bad-type', 'bonus');
    raise exception 'unknown article type was accepted';
  exception when check_violation then null;
  end;
  begin
    insert into public.obligation_charges (clinic_id, obligation_id, month, kind, amount)
    values (clinic_a, obl_a, date '2026-09-15', 'amortization', 1);
    raise exception 'a charge with a month that is not the 1st was accepted';
  exception when check_violation then null;
  end;
  begin
    insert into public.obligation_charges (clinic_id, obligation_id, month, kind, amount)
    values (clinic_a, obl_b, date '2026-09-01', 'amortization', 1);  -- obligation of clinic B
    raise exception 'a charge pointing at an obligation of another clinic was accepted';
  exception when foreign_key_violation then null;
  end;
  raise notice 'RLS isolation (stage 3) OK';
end $$;
rollback;
