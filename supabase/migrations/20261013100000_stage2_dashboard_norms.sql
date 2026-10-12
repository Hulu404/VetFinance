-- Stage 2 (Рабочий стол): clinic norms used by the advice rules until the `benchmarks` table arrives (stage 3).
-- drugs_category: name of the expense category that counts as drugs; drugs_max_pct: the share of revenue above
-- which the advice "drug_share" fires; margin_min_pct: the lower border of the profit margin norm ("margin_ok").
-- Whole percents. Existing RLS policies and grants of public.clinics cover the new columns.

alter table public.clinics
  add column drugs_category text not null default 'Препараты и расходники'
    check (length(drugs_category) between 1 and 200),
  add column drugs_max_pct smallint not null default 25 check (drugs_max_pct between 1 and 100),
  add column margin_min_pct smallint not null default 12 check (margin_min_pct between 0 and 100);
