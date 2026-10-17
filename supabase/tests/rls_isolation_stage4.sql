-- RLS isolation check for the stage 4 tables (calendar, obligations). Run after seed.sql (clinics A and B, users
-- test-a@ and test-b@) and after the stage 4 migration. Execute as postgres (SQL editor / MCP execute_sql).
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
  plan_b uuid := gen_random_uuid();
begin
  if ua is null or ub is null or clinic_a is null or clinic_b is null then
    raise exception 'test users or clinics are missing';
  end if;

  -- one row per clinic in every table (as the service role)
  insert into public.obligations (id, clinic_id, code, name, kind, payment, payment_day, principal, annual_rate_bp,
                                  first_payment_date, payments_total)
  values (obl_a, clinic_a, 'rls4-a', 'rls4 a', 'loan', 100000, 10, 1000000, 1200, date '2026-10-10', 12),
         (obl_b, clinic_b, 'rls4-b', 'rls4 b', 'loan', 100000, 10, 1000000, 1200, date '2026-10-10', 12);
  insert into public.planned_payments (id, clinic_id, date, name, amount)
  values (gen_random_uuid(), clinic_a, date '2026-10-10', 'rls4 a', 100), (plan_b, clinic_b, date '2026-10-10', 'rls4 b', 100);
  insert into public.counterparties (clinic_id, key, name) values (clinic_a, 'rls4-a', 'rls4 a'), (clinic_b, 'rls4-b', 'rls4 b');

  perform set_config('request.jwt.claims', json_build_object('sub', ua, 'role', 'authenticated')::text, true);
  set local role authenticated;

  -- 1. only rows of the user's clinic
  foreach tbl in array array['obligations', 'planned_payments', 'counterparties'] loop
    execute format('select count(*) from public.%I where clinic_id <> $1', tbl) into n using clinic_a;
    if n <> 0 then raise exception 'user A sees foreign rows in %', tbl; end if;
    execute format('select count(*) from public.%I where clinic_id = $1', tbl) into n using clinic_a;
    if n = 0 then raise exception 'user A does not see own rows in %', tbl; end if;
  end loop;

  -- 2. writes into the own clinic work, into another clinic are rejected
  insert into public.planned_payments (clinic_id, date, name, amount) values (clinic_a, date '2026-10-11', 'own', 5);
  insert into public.counterparties (clinic_id, key, name) values (clinic_a, 'rls4-own', 'own');
  update public.counterparties set max_deferral_days = 3 where clinic_id = clinic_a and key = 'rls4-own';
  update public.obligations set closed_from = date '2026-10-01' where id = obl_a;
  begin
    insert into public.planned_payments (clinic_id, date, name, amount) values (clinic_b, date '2026-10-11', 'x', 5);
    raise exception 'user A inserted a planned payment into clinic B';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.obligations (clinic_id, code, name, kind) values (clinic_b, 'hack', 'hack', 'loan');
    raise exception 'user A inserted an obligation into clinic B';
  exception when insufficient_privilege then null;
  end;
  update public.obligations set name = 'hacked' where id = obl_b;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'user A changed an obligation of clinic B'; end if;
  delete from public.planned_payments where id = plan_b;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'user A deleted a planned payment of clinic B'; end if;
  update public.counterparties set max_deferral_days = 9 where clinic_id = clinic_b;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'user A changed a counterparty of clinic B'; end if;

  -- 3. what is not meant to be written: no delete of obligations, no update of frozen charges, no truncate
  begin
    delete from public.obligations where id = obl_a;
    raise exception 'user A deleted an obligation';
  exception when insufficient_privilege then null;
  end;
  begin
    update public.obligation_charges set amount = 1 where clinic_id = clinic_a;
    raise exception 'user A updated an accrual';
  exception when insufficient_privilege then null;
  end;
  begin
    truncate public.planned_payments;
    raise exception 'user A truncated planned payments';
  exception when insufficient_privilege then null;
  end;
  reset role;

  perform set_config('request.jwt.claims', json_build_object('sub', ub, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n from public.obligations where clinic_id = clinic_a;
  if n <> 0 then raise exception 'user B sees obligations of clinic A'; end if;
  reset role;

  -- 4. rules of the new columns
  begin
    insert into public.obligations (clinic_id, code, name, kind, closed_from) values (clinic_a, 'bad', 'bad', 'loan', date '2026-10-15');
    raise exception 'closed_from that is not the 1st was accepted';
  exception when check_violation then null;
  end;
  begin
    insert into public.planned_payments (clinic_id, date, name, amount) values (clinic_a, date '2026-10-11', 'x', 0);
    raise exception 'a planned payment of 0 was accepted';
  exception when check_violation then null;
  end;
  begin
    insert into public.counterparties (clinic_id, key, name, max_deferral_days) values (clinic_a, 'bad', 'bad', 31);
    raise exception 'a deferral of 31 days was accepted';
  exception when check_violation then null;
  end;
  raise notice 'RLS isolation (stage 4) OK';
end $$;
rollback;
