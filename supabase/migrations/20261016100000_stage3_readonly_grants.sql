-- Stage 3 tables are read-only for API roles. Supabase default privileges grant everything (including TRUNCATE,
-- which RLS does not cover) to anon and authenticated on new tables; `grant select` in 20261014100000 did not take
-- the rest away. Without a write policy an UPDATE silently touched 0 rows instead of failing.
do $$
declare
  tbl text;
begin
  foreach tbl in array array['benchmarks', 'obligations', 'obligation_charges', 'stock_items', 'stock_batches',
                             'stock_writeoffs', 'stock_consumption']
  loop
    execute format('revoke insert, update, delete, truncate, references, trigger on public.%I from authenticated', tbl);
    execute format('revoke all on public.%I from anon', tbl);
  end loop;
end;
$$;
