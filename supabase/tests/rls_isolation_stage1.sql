-- RLS isolation check for the stage 1 tables. Run after seed.sql (clinics A and B, users test-a@ and
-- test-b@) and after at least one row exists in some of the tables (otherwise the checks are trivially true).
-- Execute as postgres (SQL editor / MCP execute_sql). Raises an exception on failure; rolls back.
begin;
do $$
declare
  ua uuid := (select id from auth.users where email = 'test-a@vetfinance.test');
  ub uuid := (select id from auth.users where email = 'test-b@vetfinance.test');
  clinic_a uuid := (select m.clinic_id from public.memberships m where m.user_id = ua limit 1);
  clinic_b uuid := (select m.clinic_id from public.memberships m where m.user_id = ub limit 1);
  tbl text;
  n int;
  conn_b uuid;
  cat_a uuid := gen_random_uuid();
  cat_b uuid := gen_random_uuid();
begin
  if ua is null or ub is null or clinic_a is null or clinic_b is null then
    raise exception 'test users or clinics are missing';
  end if;

  -- prepare one category per clinic and a connection secret of clinic B (as the service role)
  insert into public.categories (id, clinic_id, name, type) values
    (cat_a, clinic_a, 'rls-check-a', 'fixed'), (cat_b, clinic_b, 'rls-check-b', 'fixed');
  select c.id into conn_b from public.connections c where c.clinic_id = clinic_b and c.type = 'vetmanager';
  if conn_b is null then raise exception 'clinic B has no default connections (trigger missing)'; end if;
  insert into public.connection_secrets (connection_id, clinic_id, key_cipher)
    values (conn_b, clinic_b, 'cipher') on conflict (connection_id) do nothing;

  perform set_config('request.jwt.claims', json_build_object('sub', ua, 'role', 'authenticated')::text, true);
  set local role authenticated;

  -- 1. every stage 1 table shows only rows of the user's clinic
  foreach tbl in array array['categories', 'category_rules', 'raw_events', 'connections', 'sync_runs',
                             'doctors', 'visits', 'sales', 'payments', 'acquiring_reviews'] loop
    execute format('select count(*) from public.%I where clinic_id <> $1', tbl) into n using clinic_a;
    if n <> 0 then raise exception 'user A sees foreign rows in %', tbl; end if;
  end loop;

  -- 2. the encrypted key is not readable through the tables or through the functions of another clinic
  begin
    perform 1 from public.connection_secrets;
    raise exception 'user A can read connection_secrets';
  exception when insufficient_privilege then null;
  end;
  if public.get_connection_secret(conn_b) is not null then
    raise exception 'user A read the secret of clinic B';
  end if;
  begin
    perform public.set_connection_secret(conn_b, 'hacked');
    raise exception 'user A wrote the secret of clinic B';
  exception when insufficient_privilege then null;
  end;

  -- 3. no writes into the other clinic, and no references across clinics
  begin
    insert into public.category_rules (clinic_id, match, value, category_id)
    values (clinic_b, 'inn', '1234567890', cat_b);
    raise exception 'user A inserted a rule into clinic B';
  exception when insufficient_privilege or others then
    if sqlerrm like 'user A inserted%' then raise; end if;
  end;
  begin
    insert into public.category_rules (clinic_id, match, value, category_id)
    values (clinic_a, 'inn', '1234567890', cat_b);  -- own clinic, category of clinic B
    raise exception 'user A used a category of clinic B';
  exception when foreign_key_violation or insufficient_privilege or others then
    if sqlerrm like 'user A used%' then raise; end if;
  end;
  update public.connections set address = 'hack.example' where clinic_id = clinic_b;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'user A updated a connection of clinic B'; end if;
  reset role;

  perform set_config('request.jwt.claims', json_build_object('sub', ub, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n from public.categories where id = cat_a;
  if n <> 0 then raise exception 'user B sees a category of clinic A'; end if;
  reset role;
  raise notice 'RLS isolation (stage 1) OK';
end $$;
rollback;
