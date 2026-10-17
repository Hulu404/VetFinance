# Проверки VetFinance

Команды выполняются из корня проекта; Python берётся из `backend/.venv`.

## Отчёты: сквозная локальная проверка этапа 3

```powershell
backend/.venv/Scripts/python.exe tests/run_reports_local.py
```

Скрипт поднимает API на свободном порту `127.0.0.1` и Vite на
`127.0.0.1:5173`, запускает 150 сценариев Playwright (1280, 820, 390 px),
затем 101 контрактную проверку. Браузер скачивает реальные Excel/PDF,
контрактные тесты сверяют эти файлы с JSON API. Серверы останавливаются
при завершении или ошибке; логи и файлы остаются в `test-results/reports-local/`.
Для каждого прогона создаётся отдельная папка скачанных файлов.

Нужны установленные зависимости backend (`.[dev]`), frontend, `tests/e2e`,
`tests/contract/requirements.txt` и Chromium для Playwright. Зависимости и браузер
скрипт сам не устанавливает. Порт 5173 должен быть свободен.

Более короткие прогоны:

```powershell
backend/.venv/Scripts/python.exe tests/run_reports_local.py --contracts-only
backend/.venv/Scripts/python.exe tests/run_reports_local.py --project mobile-390
```

`--grep "часть названия"` повторяет отдельные браузерные сценарии. Проверить
уже скачанные файлы можно с `--contracts-only --downloads <папка>`; для
выборочного e2e этот же параметр позволяет затем сверить файлы прошлого
полного прогона. Без явного `--downloads` старые файлы не используются.

Реализация маршрутов, движок, проверка JWT, клиент Supabase в браузере и экспорт
настоящие. Только хранилище и сервер входа заменены локальными фикстурами из
`backend/tests/report_server.py`: E — неизменённый набор №4, A — отдельная
клиника с другими начислениями, B — пустая. Время API зафиксировано на
30 сентября 2026 года. Лимит экспорта поднят до 1000 для массового прогона;
штатные 10 выгрузок в минуту проверяются в backend unit-тестах.

Внешняя база, её ключи и настоящие учётные записи не используются. Проверки
локального стенда **не заменяют** применение миграций и проверку RLS в Postgres.

## Данные для проверки с Postgres

```powershell
backend/.venv/Scripts/python.exe backend/scripts/make_seed_set04.py
```

Генератор собирает `supabase/seed_set04.sql` из `tests/golden/set04/data.json`.
SQL выполняется одной транзакцией, повторное применение не удваивает строки.
Сид не изменяет существующие клиники и общие отраслевые нормы. Нужны миграции
до `20261014100000_stage3_reports.sql` включительно. Для входа в клинику E
заранее создаётся тестовый пользователь `test-e@vetfinance.test`.

После применения к тестовой базе проверить `supabase/tests/rls_isolation_stage3.sql`
и запустить контрактные тесты с `VF_API_URL`, `VF_TOKEN_A`, `VF_TOKEN_B`,
`VF_TOKEN_E`, `VF_SEEDED_SET04=1`. Токены не сохранять в репозитории.

Для e2e с настоящим сервером задаются `VF_WEB_URL`, `VF_E2E_EMAIL`,
`VF_E2E_PASSWORD`, `VF_E2E_SET04=1`; запуск из `tests/e2e`:
`npm test -- reports.spec.ts --workers=1`.

## Этап 4: платёжный календарь и обязательства (эталон №5)

Эталон `tests/golden/set05` (клиника F «Сосна», `as_of = 2026-10-07`), правила в `set05/README.md`.
Пересчёт ожиданий: `backend/.venv/Scripts/python.exe tests/golden/tools/compute_expected_set05.py`
(данные: `tools/gen_set05.py`). Тесты движка: `tests/golden/test_calendar_set05.py` (80 сценариев по эталону) и
`tests/golden/test_calendar_rules_set05.py` (операции дня `as_of`, короткая история, закрытие обязательства; числа выводятся
из `expected.json` и `data.json` арифметикой в самом тесте). Они пропускаются, пока нет `engine.calendar` и `engine.obligations`.

Контрактные тесты: `tests/contract/test_stage4_contract.py`. Без Postgres их можно прогнать на локальном стенде backend
(настоящие маршруты и движок, данные в памяти: A почти пустая, B пустая, F это набор №5):

```powershell
cd backend
$env:VF_LOCAL_PLANNING_TESTS = "1"; .venv/Scripts/python.exe -m uvicorn tests.planning_server:app --port 8766   # в отдельном окне
.venv/Scripts/python.exe -m tests.planning_server        # печатает export VF_TOKEN_A/B/F
cd ..
$env:VF_API_URL = "http://127.0.0.1:8766"; $env:VF_SEEDED_SET05 = "1"; $env:VF_CONTRACT_WRITES = "1"
backend/.venv/Scripts/python.exe -m pytest tests/contract/test_stage4_contract.py -rs
```

С Postgres: `VF_TOKEN_F` (пользователь `test-f@vetfinance.test`, `VF_TEST_EMAIL_F` в `backend/.env`), `VF_SEEDED_SET05=1`.
Тесты, которые меняют данные (обязательства создаются и закрываются, ручной платёж, отсрочка контрагента, безопасный запас),
идут только с `VF_CONTRACT_WRITES=1` на тестовой клинике: закрытые обязательства остаются в списке (так задумано).
`VF_STAGE4_STUB=1` помечает ожидаемо падающими тесты, которым нужен настоящий движок (для сервера с заглушками шага 1).

e2e: `npm test -- calendar.spec.ts --workers=1` из `tests/e2e` (30 сценариев на каждую ширину 1280, 820, 390);
`VF_E2E_SET05=1` для клиники F, `VF_E2E_WRITE=1` для форм (создают, закрывают и восстанавливают данные).
