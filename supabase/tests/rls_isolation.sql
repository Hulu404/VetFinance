-- RLS isolation check. Run after seed.sql with users test-a@ and test-b@ created.
-- Execute as postgres (SQL editor / MCP execute_sql). Raises an exception on failure; rolls back.
begin;
do $$
declare
  ua uuid := (select id from auth.users where email = 'test-a@vetfinance.test');
  ub uuid := (select id from auth.users where email = 'test-b@vetfinance.test');
  n int;
begin
  if ua is null or ub is null then raise exception 'test users are missing'; end if;

  perform set_config('request.jwt.claims', json_build_object('sub', ua, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n from public.clinics;
  if n <> 1 then raise exception 'user A sees % clinics, expected 1', n; end if;
  select count(*) into n from public.accounts where name = 'Касса' and clinic_id <> (select id from public.clinics);
  if n <> 0 then raise exception 'user A sees foreign accounts'; end if;
  select count(*) into n from public.transactions t join public.accounts a on a.id = t.account_id
    where a.clinic_id <> t.clinic_id;
  if n <> 0 then raise exception 'inconsistent rows'; end if;
  -- cannot write into a foreign clinic
  begin
    insert into public.accounts (clinic_id, name, kind, opening_date)
    select c.id, 'x', 'cash', current_date from public.clinics c;  -- own clinic: allowed
    insert into public.accounts (clinic_id, name, kind, opening_date)
    values ('945d2d86-c58b-5c70-bbfe-b15587e537a2', 'x', 'cash', current_date);  -- clinic B
    raise exception 'user A inserted into clinic B';
  exception when insufficient_privilege or others then
    if sqlerrm like 'user A inserted%' then raise; end if;
  end;
  reset role;

  perform set_config('request.jwt.claims', json_build_object('sub', ub, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n from public.clinics where id = '97527e2f-da0c-588c-b2fc-34fdf39e60a7';
  if n <> 0 then raise exception 'user B sees clinic A'; end if;
  select count(*) into n from public.transactions;
  if n <> 16 then raise exception 'user B sees % transactions, expected 16', n; end if;
  update public.clinics set name = 'hack' where id = '97527e2f-da0c-588c-b2fc-34fdf39e60a7';
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'user B updated clinic A'; end if;
  reset role;
  raise notice 'RLS isolation OK';
end $$;
rollback;
