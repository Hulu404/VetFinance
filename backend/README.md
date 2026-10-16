# VetFinance backend

Python 3.13 (минимум 3.12), FastAPI, SQLAlchemy 2 (async, psycopg3), Postgres в Supabase.

## Запуск

```
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"      # Windows; на Linux .venv/bin/python
cp .env.example .env                                  # заполнить значения
.venv/Scripts/uvicorn app.main:app --reload
.venv/Scripts/python -m pytest      # из backend/ или из корня репозитория
.venv/Scripts/ruff check . && .venv/Scripts/mypy app engine tests
```

Переменные окружения: см. `.env.example` (`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_JWT_SECRET`, `JWT_AUDIENCE`, `CORS_ORIGINS`). Секреты только из окружения.

## Миграции

Один путь: SQL-файлы Supabase CLI в `supabase/migrations/YYYYMMDDHHMMSS_name.sql`. Alembic не используется.
Применение: `supabase db push` или MCP `apply_migration` по порядку имён. Данные для разработки: `supabase/seed.sql`
(генерируется `python backend/scripts/make_seed.py` из `tests/golden/set01/data.json`; перед применением
создать пользователей `test-a@vetfinance.test` и `test-b@vetfinance.test`). Проверка RLS: `supabase/tests/rls_isolation.sql`.

## Аутентификация

Bearer-токен Supabase. Алгоритм берётся из заголовка токена: `RS256/ES256/EdDSA` проверяются по JWKS
`{SUPABASE_URL}/auth/v1/.well-known/jwks.json` (кэш), `HS256` по `SUPABASE_JWT_SECRET`. Проверяются `exp`, `sub`, `aud`.

## Как работает RLS

Backend подключается к Postgres по `DATABASE_URL` (пользователь `postgres`), но каждый запрос выполняется в одной
транзакции, где сразу делается `set local role authenticated` и `set_config('request.jwt.claims', <claims>, true)`.
Дальше Postgres сам применяет политики через `auth.uid()`; service_role не используется. Клиника пользователя
определяется запросом к `memberships` (видны только свои строки). Если нужна изоляция строгая, не давать
`DATABASE_URL` прав суперпользователя, достаточно членства в роли `authenticated`.

## Структура

- `engine/` чистые функции (`money.py` единственное место округления, `balance.py`, `figure.py`).
- `app/` FastAPI: `main.py` (эндпоинты), `auth.py`, `repo.py` (слой данных, подменяется в тестах), `schemas.py`, `errors.py`.
- `openapi.json` схема этапов 0–3 с примерами отчётов на наборе №4; экспорт: `python scripts/export_openapi.py`, контракт: `docs/api-contract.md`.

## Проверка отчётов (этап 3)

Локальная связка браузер → API → Excel/PDF и подготовка сида для Postgres
описаны в [`tests/README.md`](../tests/README.md). Локальный стенд запускается
из корня репозитория командой `.venv` Python: `backend/.venv/Scripts/python.exe tests/run_reports_local.py`.
Склад пока заполняется эталоном №4; загрузчик склада Ветменеджера отложен
до появления тестового аккаунта (решение владельца от 2026-10-14).

## Деплой (Railway)

Отдельный сервис, root directory = `backend/`, конфиг `railway.json` (healthcheck `/healthz`), зависимости из
`requirements.txt`, версия Python из `.python-version`. Переменные окружения из `.env.example`.
