# Контракт API VetFinance, версия 0

Владелец: backend-developer. Frontend строит mock-сервер из примеров этого файла. Изменение контракта: правка здесь, затем `backend/openapi.json`, затем запись в `docs/handoff.md`, если изменение ломающее.

## Общие правила

- Базовый путь `/v1`. Аутентификация: Supabase JWT в `Authorization: Bearer`. Клиника определяется по токену, в путях её нет.
- Деньги: целое число **копеек**. Проценты: число с одним знаком после запятой в долях процента, поле называется `*_pct` (`15.0` значит 15,0%). Даты: `YYYY-MM-DD`, время: ISO 8601 с часовым поясом.
- Часовой пояс клиники хранится в `clinic.timezone`. «Сегодня» считает backend и отдаёт в `as_of`.
- Ошибки: `{ "error": { "code": "string", "message": "по-русски", "details": {} } }`. Коды: `unauthorized`, `forbidden`, `not_found`, `validation`, `conflict`, `sync_failed`.
- Списки: `?limit=50&cursor=...`, ответ `{ "items": [], "next_cursor": null }`.

## Объект Figure

Каждый числовой показатель, который можно раскрыть подсказкой, отдаётся так:

```json
{
  "value": 124000000,
  "unit": "rub",
  "breakdown": [
    { "label": "Услуги врачей", "value": 75640000, "unit": "rub" },
    { "label": "Продажа кормов", "value": 32160000, "unit": "rub" }
  ],
  "source": ["vetmanager", "bank"],
  "note": "Данные из Ветменеджера, сверены с эквайрингом и кассой."
}
```

`unit`: `rub` | `pct` | `count` | `days`. `source`: массив из `bank`, `vetmanager`, `bot`, `manual`, `calc`. `note` собирает backend по шаблону, клиент его не формирует.

Правило `source` для остатков (`balance.total`, `balance.bank`, `balance.cash`): объединение `source` операций, вошедших в сумму этой Figure, без повторов, в порядке `bank`, `vetmanager`, `bot`, `manual`. Если во всей Figure нет ни одной вошедшей операции, `source` равен `["manual"]` (остаток из начального остатка, введённого вручную). В остаток входят операции со `status` `ok` и `check`, не входят `duplicate`, операции позже `as_of` и раньше `opening_date` счёта.

## Эндпоинты первой очереди

Пометка «Этап N» у раздела: на каком этапе из `docs/stages.md` эндпоинт реализуется. Заглушку с примером ответа backend публикует в контракте и `backend/openapi.json` на предыдущем этапе или в начале своего.

### Рабочий стол (функции 1–5) · Этап 2; на этапе 0 только `balance.total` и `balance.bank`

`GET /v1/dashboard?as_of=YYYY-MM-DD` (необязательный параметр `as_of`, по умолчанию «сегодня» в часовом поясе клиники; нужен для сверки с эталонными данными) →

```json
{
  "as_of": "2026-09-09",
  "data_as_of": "2026-09-09T04:12:00+03:00",
  "balance": { "total": Figure, "bank": Figure, "cash": Figure, "week_change": Figure, "runway_days": Figure },
  "month": { "revenue": Figure, "expenses": Figure, "profit": Figure, "profit_margin_pct": Figure, "days_passed": 8, "days_total": 30 },
  "balance_trend": [{ "date": "2026-08-27", "value": 39740000 }],
  "advice": [
    { "id": "string", "severity": "alert|warning|good", "icon": "🩸", "title": "string", "text": "string",
      "why": { "summary": "string", "steps": ["string"], "sources": ["string"] } }
  ]
}
```

`why` собирается из результата движка по шаблону.

**Этап 0:** ответ содержит только `as_of`, `data_as_of` и `balance` с полями `total` и `bank`; остальные поля (`cash`, `week_change`, `runway_days`, `month`, `balance_trend`, `advice`) отсутствуют в ответе (не `null`), frontend не должен на них рассчитывать до этапа 2. `data_as_of` на этапе 0 равен времени последней загруженной операции (`created_at`), `null`, если операций нет.

```json
{ "as_of": "2026-09-09", "data_as_of": "2026-09-09T04:12:00+03:00",
  "balance": { "total": Figure, "bank": Figure } }
```

### Транзакции (функции 6–10) · Этап 1

- `GET /v1/transactions?tab=all|check|duplicates&from=&to=&cursor=` → список `Transaction`.
- `PATCH /v1/transactions/{id}` тело `{ "category_id": "string", "create_rule": true }` → обновлённая `Transaction`; при `create_rule` создаётся правило.
- `POST /v1/transactions` ручная операция (расход или доход, счёт, категория, дата, сумма, комментарий).
- `POST /v1/transactions/{id}/resolve-duplicate` тело `{ "keep_id": "string" }`.
- `GET /v1/category-rules`, `DELETE /v1/category-rules/{id}`.
- `GET /v1/transactions/summary?month=YYYY-MM` → `{ "income": Figure, "expense": Figure, "balance": Figure }`.

```json
Transaction = {
  "id": "string", "date": "2026-09-09", "description": "string",
  "category": { "id": "string", "name": "string" } | null,
  "account": { "id": "string", "name": "string" },
  "source": "bank|vetmanager|bot|manual",
  "amount": -540000,
  "kind": "in|out|transfer",
  "status": "ok|check|duplicate"
}
```

### Отчёты (функции 14, 15, 17, 18, 20) · Этап 3

- `GET /v1/reports/pnl?month=YYYY-MM&view=clinic|direction` → строки `{ "key", "label", "kind": "revenue|expense|subtotal|total", "amount": Figure, "share_pct": Figure }` в порядке: выручка, переменные расходы, маржинальная прибыль, постоянные расходы, налоги и взносы, **обязательства и амортизация**, чистая прибыль. Для `view=direction`: `{ "direction", "revenue", "profit" }`.
- `GET /v1/reports/norm?month=YYYY-MM` → `{ "items": [{ "key", "label", "norm": { "min_pct", "max_pct", "source" }, "actual_pct": Figure, "status": "ok|above|below", "deviation_pp": Figure, "deviation_rub": Figure }] }`.
- `GET /v1/reports/stock` → `{ "frozen": Figure, "expiring_60d": Figure, "written_off_month": Figure, "turnover_days": Figure, "norm_turnover_days": 45, "expiring": [{ "item", "expires_on", "days_left", "qty", "amount": Figure }] }`.
- Экспорт любого отчёта: `GET /v1/reports/{name}/export?format=xlsx|pdf&month=`.

### Прайс услуг (функции 11, 12, 18) · Этап 5

- `GET /v1/services?sort=margin` → список услуг `{ "id", "name", "direction", "price": Figure, "visits_month": Figure, "margin_pct": Figure }`.
- `GET /v1/services/{id}/cost` → `{ "price": Figure, "net_profit": Figure, "net_margin_pct": Figure, "parts": [{ "key": "doctor_pay|drugs|anesthesia|supplies|acquiring|fixed", "label", "amount": Figure, "share_pct": Figure }], "monthly_profit": Figure }`.

### Планирование (функции 21–23) · Этап 4

- `GET /v1/calendar?days=22` → `{ "safe_balance": Figure, "summary": { "income": Figure, "expense": Figure, "payments_count": 11, "lowest": { "date", "balance": Figure } }, "alerts": [CalendarAlert], "days": [CalendarDay] }`.
- `CalendarDay`: `{ "date", "weekday", "opening": Figure, "income_forecast": Figure, "payments": [{ "name", "amount": Figure, "source": "recurring|obligation|manual" }], "closing": Figure, "below_safe": true }`.
- `CalendarAlert`: `{ "date", "title", "text", "shortfall": Figure, "suggestion": { "text", "closes_gap": true }, "why": { "summary", "steps", "sources" } }`. `suggestion` считает движок перебором переносов платежей в пределах допустимой отсрочки.
- `GET /v1/obligations` → `{ "debt_total": Figure, "monthly_payment": Figure, "amortization_month": Figure, "loans": [{ "name", "lender", "until", "paid_pct": Figure, "remaining": Figure, "payment": Figure }], "equipment": [{ "name", "cost": Figure, "life_years", "monthly": Figure }] }`.
- `POST /v1/obligations`, `PATCH /v1/obligations/{id}`.

### Аналитика (функции 24–28, 31, 33, 34) · Этап 6 (`/v1/efficiency` — этап 5)

- `GET /v1/forecast?scenario=base|growth|cautious` → `{ "scenario": { "key", "name", "description" }, "confidence": "high|medium|low", "history_months": 18, "actual": [{ "period": "2025-Q4", "revenue": Figure }], "plan": [{ "period": "2026-Q4", "revenue": Figure, "growth_pct": Figure, "lines": [{ "key", "label", "norm_pct": { "min", "max" }, "amount": Figure }], "net_profit": Figure, "margin_pct": Figure }] }`. Рост считается к предыдущему кварталу.
- `GET /v1/forecast/assumptions` и `PUT /v1/forecast/assumptions` тело: доли статей, индексация, допущения сценария. Ответ `PUT` содержит пересчитанный прогноз.
- `GET /v1/forecast/levers?scenario=growth` → список рычагов `{ "key", "title", "effect_month": Figure, "constraint": "string" }`. В MVP набор рычагов фиксирован в коде.
- `GET /v1/forecast/plan-vs-fact?month=` → отклонение по строкам и по рычагам, текст по шаблону.
- `GET /v1/efficiency` → `{ "visits": Figure, "load_pct": Figure, "avg_check": Figure, "rooms": [{ "name", "load_pct": Figure }], "hour_cost": Figure, "hour_cost_parts": [Figure] }`. Если расписание с кабинетами недоступно, `rooms` пуст, а `load_by` равно `"doctors"`.

### Настройки и подключения (функции 36–41) · Этапы 0, 1 и 7

Этап 0: `GET|PATCH /v1/clinic`, `GET /v1/accounts`. Этап 1: подключения, импорт выписки, категории, направления, `shifts/close`. Этап 7: `audit-log`, `billing`.

- `GET|PATCH /v1/clinic` (название, юрлицо, налоговый режим, часовой пояс, `safe_balance`). Объект: `{ "id", "name", "legal_entity": string|null, "tax_regime": string|null, "timezone": "Europe/Moscow", "safe_balance": 15000000 }`. `PATCH`: любое подмножество `name`, `legal_entity`, `tax_regime`, `timezone` (IANA), `safe_balance` (целые копейки, ≥ 0); неизвестные поля дают `validation`.
- `GET|POST|PATCH /v1/accounts`. Этап 0: только `GET` → `{ "items": [Account], "next_cursor": null }`, `Account = { "id", "name", "kind": "bank|cash", "opening_balance": 12500003, "opening_date": "2026-08-01" }` (копейки, на начало дня `opening_date`).
- Без токена или с недействительным токеном любой `/v1/*` отвечает `401` с кодом `unauthorized`. Пользователь без клиники получает `403 forbidden`. `GET /healthz` без авторизации: `{ "status": "ok" }` (вне `/v1`).
- `GET|PATCH /v1/categories` (статья, тип переменная/постоянная, норма).
- `GET|PATCH /v1/directions` (привязка услуг и товарных групп).
- `GET /v1/connections`, `PUT /v1/connections/vetmanager` (адрес, ключ), `PUT /v1/connections/bank`, `POST /v1/connections/{id}/sync`.
- `POST /v1/imports/bank-statement` загрузка выписки 1С файлом.
- `POST /v1/shifts/close` закрытие смены: `{ "date", "cash_amount", "revenue_amount" }`.
- `GET /v1/audit-log`, `POST /v1/audit-log/{id}/undo`. Откат доступен 7 дней, журнал хранится 90 дней.
- `GET /v1/billing`, `POST /v1/billing/checkout` (ссылка на оплату в ЮКассе).

## Вне контракта первой очереди

Telegram-бот (42–49), живые ответы Claude, экран «Врачи» (16), рекомендации по цене (13), сценарий из вопроса (30), уточнение прогноза (32), админка основателя (50–52) подробно описываются перед своим этапом.
