-- RLS isolation check for the stage 5 tables (services, techcards, rooms). Run after seed.sql (clinics A and B, users
-- test-a@ and test-b@) and after the stage 5 migration. Execute as postgres (SQL editor / MCP execute_sql).
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
  svc_a uuid := gen_random_uuid();
  svc_b uuid := gen_random_uuid();
  vm_a uuid := gen_random_uuid();
  item_a uuid := gen_random_uuid();
  room_a uuid := gen_random_uuid();
  room_b uuid := gen_random_uuid();
  doc_a uuid := gen_random_uuid();
begin
  if ua is null or ub is null or clinic_a is null or clinic_b is null then
    raise exception 'test users or clinics are missing';
  end if;

  -- one row per clinic in every table (as the service role)
  insert into public.services (id, clinic_id, source, name, manual_price)
  values (svc_a, clinic_a, 'manual', 'rls5 a', 100000), (svc_b, clinic_b, 'manual', 'rls5 b', 100000);
  insert into public.services (id, clinic_id, source, external_id, name) values (vm_a, clinic_a, 'vetmanager', 'rls5-vm', 'rls5 vm');
  insert into public.service_settings (service_id, clinic_id, minutes) values (svc_a, clinic_a, 30), (svc_b, clinic_b, 30);
  insert into public.techcards (service_id, clinic_id) values (svc_a, clinic_a), (svc_b, clinic_b);
  insert into public.stock_items (id, clinic_id, external_id, name) values (item_a, clinic_a, 'rls5-item', 'rls5 item');
  insert into public.techcard_lines (clinic_id, service_id, item_id, part, qty) values (clinic_a, svc_a, item_a, 'drugs', 1.5);
  insert into public.rooms (id, clinic_id, external_id, name) values (room_a, clinic_a, 'rls5-a', 'rls5 a'), (room_b, clinic_b, 'rls5-b', 'rls5 b');
  insert into public.room_schedule_slots (clinic_id, room_id, weekday, from_min, to_min) values (clinic_a, room_a, 0, 600, 1080), (clinic_b, room_b, 0, 600, 1080);
  insert into public.room_bookings (clinic_id, external_id, date, room_id, minutes)
  values (clinic_a, 'rls5-a', date '2026-10-01', room_a, 30), (clinic_b, 'rls5-b', date '2026-10-01', room_b, 30);
  insert into public.doctors (id, clinic_id, external_id, code, name) values (doc_a, clinic_a, 'rls5-d', 'RLS5', 'rls5 doctor');

  perform set_config('request.jwt.claims', json_build_object('sub', ua, 'role', 'authenticated')::text, true);
  set local role authenticated;

  -- 1. only rows of the user's clinic
  foreach tbl in array array['services', 'service_settings', 'techcards', 'rooms', 'room_schedule_slots', 'room_bookings'] loop
    execute format('select count(*) from public.%I where clinic_id <> $1', tbl) into n using clinic_a;
    if n <> 0 then raise exception 'user A sees foreign rows in %', tbl; end if;
    execute format('select count(*) from public.%I where clinic_id = $1', tbl) into n using clinic_a;
    if n = 0 then raise exception 'user A does not see own rows in %', tbl; end if;
  end loop;

  -- 2. writes into the own clinic work for manual services, settings and techcards
  insert into public.services (clinic_id, source, name, manual_price) values (clinic_a, 'manual', 'own', 5000);
  update public.services set manual_price = 6000 where id = svc_a;
  update public.service_settings set minutes = 45 where service_id = svc_a;
  update public.techcards set updated_at = now() where service_id = svc_a;
  delete from public.techcard_lines where service_id = svc_a;
  insert into public.techcard_lines (clinic_id, service_id, item_id, part, qty) values (clinic_a, svc_a, item_a, 'supplies', 2);
  update public.doctors set hours_per_week = 36.5 where id = doc_a;
  get diagnostics n = row_count;
  if n <> 1 then raise exception 'user A could not set the hours of an own doctor'; end if;
  update public.clinics set avg_visit_minutes = 25 where id = clinic_a;
  get diagnostics n = row_count;
  if n <> 1 then raise exception 'user A could not set the average visit length'; end if;

  -- 3. nothing into another clinic, nothing for services from Vetmanager, no other columns of doctors
  begin
    insert into public.services (clinic_id, source, name, manual_price) values (clinic_b, 'manual', 'x', 5000);
    raise exception 'user A inserted a service into clinic B';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.services (clinic_id, source, external_id, name) values (clinic_a, 'vetmanager', 'rls5-x', 'x');
    raise exception 'user A inserted a service of Vetmanager';
  exception when insufficient_privilege then null;
  end;
  update public.services set name = 'hacked' where id = vm_a;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'user A changed a service of Vetmanager'; end if;
  delete from public.services where id = vm_a;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'user A deleted a service of Vetmanager'; end if;
  update public.services set name = 'hacked' where id = svc_b;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'user A changed a service of clinic B'; end if;
  update public.service_settings set minutes = 1 where service_id = svc_b;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'user A changed settings of clinic B'; end if;
  begin
    insert into public.techcard_lines (clinic_id, service_id, item_id, part, qty) values (clinic_b, svc_b, item_a, 'drugs', 1);
    raise exception 'user A inserted a techcard line into clinic B';
  exception when insufficient_privilege or foreign_key_violation then null;
  end;
  begin
    update public.doctors set name = 'hacked' where id = doc_a;
    raise exception 'user A changed the name of a doctor';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.rooms (clinic_id, external_id, name) values (clinic_a, 'x', 'x');
    raise exception 'user A inserted a room';
  exception when insufficient_privilege then null;
  end;
  begin
    truncate public.services;
    raise exception 'user A truncated services';
  exception when insufficient_privilege then null;
  end;
  reset role;

  perform set_config('request.jwt.claims', json_build_object('sub', ub, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n from public.services where clinic_id = clinic_a;
  if n <> 0 then raise exception 'user B sees services of clinic A'; end if;
  select count(*) into n from public.room_bookings where clinic_id = clinic_a;
  if n <> 0 then raise exception 'user B sees room bookings of clinic A'; end if;
  reset role;

  -- 4. rules of the new columns
  begin
    insert into public.services (clinic_id, source, name, manual_price) values (clinic_a, 'manual', 'bad', 0);
    raise exception 'a manual service with price 0 was accepted';
  exception when check_violation then null;
  end;
  begin
    insert into public.services (clinic_id, source, name) values (clinic_a, 'vetmanager', 'bad');
    raise exception 'a Vetmanager service without external id was accepted';
  exception when check_violation then null;
  end;
  begin
    insert into public.techcard_lines (clinic_id, service_id, item_id, part, qty) values (clinic_a, svc_a, item_a, 'sweets', 1);
    raise exception 'a techcard line of an unknown part was accepted';
  exception when check_violation then null;
  end;
  begin
    update public.doctors set hours_per_week = 36.3 where id = doc_a;
    raise exception 'hours that are not a multiple of 0.5 were accepted';
  exception when check_violation then null;
  end;
  begin
    update public.clinics set avg_visit_minutes = 4 where id = clinic_a;
    raise exception 'an average visit of 4 minutes was accepted';
  exception when check_violation then null;
  end;
  raise notice 'RLS isolation (stage 5) OK';
end $$;
rollback;
