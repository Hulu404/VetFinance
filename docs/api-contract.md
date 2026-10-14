# Контракт API VetFinance, версия 1 (этап 1)

Владелец: backend-developer. Frontend строит mock-сервер из примеров этого файла. Изменение контракта: правка здесь, затем `backend/openapi.json`, затем запись в `docs/handoff.md`, если изменение ломающее.

## Общие правила

- Базовый путь `/v1`. Аутентификация: Supabase JWT в `Authorization: Bearer`. Клиника определяется по токену, в путях её нет.
- Деньги: целое число **копеек**. Проценты: число с одним знаком после запятой в долях процента, поле называется `*_pct` (`15.0` значит 15,0%). Даты: `YYYY-MM-DD`, время: ISO 8601 с часовым поясом.
- Часовой пояс клиники хранится в `clinic.timezone`. «Сегодня» считает backend и отдаёт в `as_of`.
- Ошибки: `{ "error": { "code": "string", "message": "по-русски", "details": {} } }`. Коды: `unauthorized`, `forbidden`, `not_found`, `validation`, `conflict`, `rate_limited` (HTTP 429, заголовок `Retry-After` в секундах), `sync_failed`.
- Ошибка `validation` (HTTP 422): `details.fields` это объект `{ "имя_поля": "причина" }`, причины: `required`, `invalid`, `must_be_positive`, `too_many_decimals`, `too_large`, `in_future`, `before_opening`, `too_long`, `unknown_field`, а для подключений `unreachable` (адрес) и `invalid` (ключ). Если ошибка относится не к полю, а к целому запросу (файл выписки), причина лежит в `details.reason`. Тексты ошибок пользователю показывает клиент по этим кодам, `error.message` предназначен для логов и отладки.
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

Необязательные поля (с этапа 2; когда не нужны, в ответе их нет):

- `delta: true` у `Figure` и у строки `breakdown`: значение это изменение, а не слагаемое итога. Клиент показывает знак (`+15 400 ₽`, `−3,2%`) и цвет по знаку. Без `delta` положительное число читается как обычное значение.
- `details`: массив `{ "label", "value", "unit" }` справочных строк подсказки. Они не входят в сумму `breakdown` (например, «Средний чек» и «Приёмов» в подсказке выручки). Клиент показывает их под чертой после `breakdown`.
- Для `unit = pct` `value` это JSON-число с одним знаком после запятой (`14.8`, `-30.6`), не строка. Для `rub`, `count`, `days` только целое.

Правило `source` для остатков (`balance.total`, `balance.bank`, `balance.cash`): объединение `source` операций, вошедших в сумму этой Figure, без повторов, в порядке `bank`, `vetmanager`, `bot`, `manual`. Если во всей Figure нет ни одной вошедшей операции, `source` равен `["manual"]` (остаток из начального остатка, введённого вручную). В остаток входят операции со `status` `ok` и `check`, не входят `duplicate`, операции позже `as_of` и раньше `opening_date` счёта.

## Эндпоинты первой очереди

Пометка «Этап N» у раздела: на каком этапе из `docs/stages.md` эндпоинт реализуется. Заглушку с примером ответа backend публикует в контракте и `backend/openapi.json` на предыдущем этапе или в начале своего.

### Рабочий стол (функции 1–5) · Этап 2; на этапе 0 только `balance.total` и `balance.bank`

`GET /v1/dashboard?as_of=YYYY-MM-DD` (необязательный параметр `as_of`, по умолчанию «сегодня» в часовом поясе клиники; нужен для сверки с эталонными данными) →

```json
{
  "as_of": "2026-09-09",
  "data_as_of": "2026-09-09T04:12:00+03:00",
  "data_stale": false,
  "balance": {
    "total": Figure, "bank": Figure, "cash": Figure,
    "week_change": Figure | null, "week_change_pct": Figure | null,
    "runway_days": Figure
  },
  "month": {
    "days_passed": 9, "days_total": 30,
    "revenue": Figure, "expenses": Figure, "profit": Figure,
    "profit_margin_pct": Figure, "visits": Figure, "avg_check": Figure
  },
  "balance_trend": [{ "date": "2026-08-27", "value": 50742296 }],
  "balance_trend_info": { "note": "string", "source": ["bank", "vetmanager", "bot", "manual"] },
  "advice": [
    { "id": "cash_runway", "severity": "alert|warning|good", "icon": "🩸", "title": "string", "text": "string",
      "why": { "summary": "string", "steps": ["string"], "sources": ["string"] } }
  ],
  "advice_status": "ready|not_enough_data"
}
```

Все суммы целые копейки, проценты числом с одним знаком. `as_of` вне данных (раньше самого раннего `opening_date` или до первой операции): `200`, нулевые значения, пустой `advice`. Неверный `as_of`: `422 validation`.

**Период и определения** (решение владельца 2026-10-12, правила в `tests/golden/set03/README.md`):

- Всё считается на конец `as_of` включительно: остатки, месяц (с 1-го числа по `as_of`), `days_passed = as_of.day` («9 дней из 30»). Операции дня `as_of` входят и в остаток, и в месяц. В расчёт не входят дубли (`duplicate`), операции позже `as_of` и раньше `opening_date` счёта; переводы между своими счетами не доходы и не расходы; `check` входит.
- `balance.total = bank + cash`; `balance.*.breakdown` по счетам (подпись это название счёта), `source` по правилу остатков (см. «Объект Figure»).
- `balance.week_change` (рубли, `delta: true`): остаток на конец `as_of` минус остаток на конец `as_of − 7` дней. `breakdown`: изменение по каждому счёту (`delta: true`, сумма равна `value`); `details`: «Неделю назад (2 сентября)» и «Сейчас». `balance.week_change_pct` (`unit = pct`, `delta: true`): то же изменение к остатку неделю назад; `breakdown`: «Неделю назад (2 сентября)» и «Сейчас» в рублях. Если `as_of − 7` раньше самого раннего `opening_date`, оба поля равны `null` (ключ есть); `week_change_pct` равен `null` также при остатке неделю назад ≤ 0.
- `balance.runway_days` («Хватит на», `unit = days`): `floor(остаток total × окно ÷ расходы за окно)`, окно 28 дней (меньше, если история короче: дни от самого раннего `opening_date` до `as_of`). Расходы окна: операции `kind = out` без дублей и переводов, `check` входит. Остаток ≤ 0 даёт 0. `breakdown` (по порядку): «Остаток на счетах», «Расходы за N дней», «Расходы в день, в среднем» (рубли), «Окно расчёта» (`days`); в `note` формула с цифрами и фраза, что платежи вперёд не учитываются. Если расходов в окне нет, поля нет (ключа нет в ответе). Целая часть берётся вниз: 17,6 дня показываем как 17.
- `month.revenue`: закрытые счета Ветменеджера (`exec`) с датой в месяце, черновики (`save`) не входят. `breakdown` всегда две строки: «Услуги», «Товары». `details`: «Средний чек» и «Приёмов» (если есть). `source = ["vetmanager"]`.
- `month.expenses`: деньги банка и кассы, операции `kind = out` в месяце; `breakdown` по статьям (без статьи: «Без статьи»), по убыванию суммы, при равенстве по названию. Закупка впрок целиком попадает в расходы месяца закупки: это не ОПиУ (отчёт этапа 3).
- `month.profit = revenue − expenses`, `breakdown`: «Выручка» (+), «Расходы» (−). Налоги и амортизацию начисляет отчёт «Прибыль и убытки» при закрытии месяца (этап 3), поэтому число может отличаться от «Чистой прибыли» отчёта; это сказано в `note`.
- `month.profit_margin_pct = прибыль ÷ выручка` (`pct`), `breakdown`: «Прибыль», «Выручка»; при выручке 0 поля нет. `month.visits` (`count`): приёмы месяца, `breakdown` по врачам («Фамилия И.»; при нуле одна строка «Нет приёмов»). `month.avg_check` (`rub`): выручка ÷ число закрытых счетов; `breakdown`: «Выручка» (рубли), «Счетов» (`count`); при отсутствии счетов поля нет.
- `source` производных цифр: объединение источников операций и счетов, из которых получена цифра, в порядке `bank`, `vetmanager`, `bot`, `manual` (без `calc`). Если вошедших данных нет, `["manual"]`.
- `balance_trend`: остаток `total` на конец каждого из 14 дней, оканчивая `as_of`, от старых к новым; дни раньше самого раннего `opening_date` не отдаются (на четвёртый день жизни клиники 4 точки). Последняя точка равна `balance.total.value`. `balance_trend_info`: подсказка точки (`note`, `source`), на каждую точку `Figure` не выдаётся.
- `month.revenue_forecast` и `month.expenses_change_pct` (запрос designer) на этапе 2 не отдаются: нет эталона; клиент работает без них.
- `advice_status` (с 2026-10-14, по запросу frontend): `not_enough_data`, если от самого раннего `opening_date` до `as_of` меньше 7 дней или счетов нет (советы не строились, экран пишет «Пока мало данных»); `ready`, если правила отработали (пустой `advice` тогда значит «отклонений нет»). Клиент не выводит это сам из длины `balance_trend`.
- `advice` всегда есть (может быть пустым), не больше 5 советов, порядок `alert`, `warning`, `good`, внутри по порядку правил. Советов нет, пока данных меньше 7 дней; месячные правила работают с 7-го числа. Правила и пороги (настройки клиники до таблицы `benchmarks`):

| `id` | Условие | `severity` | `icon` |
| --- | --- | --- | --- |
| `cash_runway` | «хватит на» меньше 14 дней / меньше 30 дней | `alert` / `warning` | 🩸 |
| `drug_share` | препараты (статья «Препараты и расходники») больше нормы клиники от выручки (по умолчанию 25%) | `warning` | 💊 |
| `revenue_drop` | выручка месяца меньше 85% выручки тех же первых дней прошлого месяца (если прошлый месяц есть в данных) | `warning` | 📈 |
| `margin_ok` | рентабельность не ниже 12% | `good` | 📈 |

- У каждого совета непустые `why.summary`, `why.steps` (2–5 шагов с числами расчёта), `why.sources`. `id` стабильный. Пределы: `title` до 80 знаков, `text` до 200, шаг до 240. Деньги в текстах как на клиенте («412 800 ₽» с неразрывными пробелами, минус U+2212). В текстах нет слов «ИИ» и «нейросеть», нет фамилий врачей и владельцев животных. Тексты собираются по шаблонам из результата движка (в MVP модели нет), структура `why` та же, что будет у ответа модели.
- Ключи в ответе: `balance.week_change` и `balance.week_change_pct` присутствуют всегда (`null`, если данных нет); `balance.runway_days`, `month.profit_margin_pct`, `month.avg_check` при отсутствии данных не возвращаются (ключа нет).

**Этап 0–1 (история):** ответ содержал только `as_of`, `data_as_of`, `data_stale` (с этапа 1) и `balance` с `total` и `bank`. С этапа 2 все поля выше есть всегда (кроме перечисленных необязательных); `data_as_of` равен времени последней загруженной операции (`created_at`), `null`, если операций нет. `data_stale`: см. «Признак устаревших данных».

Полный пример ответа (эталон №3, `as_of = 2026-09-09`) лежит в `backend/openapi.json` (`components.schemas.DashboardOut.example`).

### Транзакции (функции 6–10) · Этап 1

Статусы операции: `ok` (учитывается), `check` («на проверку»: статьи нет), `duplicate` (не входит в остаток, отчёты и итоги). Остаток исключает только помеченную копию, а не обе операции пары.

```json
Transaction = {
  "id": "b7a1…", "date": "2026-09-09", "description": "Оплата по счёту 12 за аренду, сентябрь",
  "category": { "id": "…", "name": "Аренда" } | null,
  "account": { "id": "…", "name": "Расчётный счёт" },
  "source": "bank|vetmanager|bot|manual",
  "amount": -8500000,
  "kind": "in|out|transfer",
  "status": "ok|check|duplicate",
  "duplicate_state": null | "pending" | "confirmed",
  "duplicate_of": TransactionBrief | null,
  "duplicate_reason": "одинаковая сумма 5 400 ₽, дата 6 сен, разные источники" | null,
  "suggestion": { "category": { "id": "…", "name": "Аренда" }, "reason": "rule|similar",
                  "text": "так же разнесено 3 операции по «ИП Волков»" } | null,
  "figure": {
    "value": -8500000, "unit": "rub",
    "breakdown": [{ "label": "Выписка банка · Расчётный счёт", "value": -8500000, "unit": "rub" }],
    "source": ["bank"],
    "note": "Операция от 9 сентября 2026, счёт «Расчётный счёт». Статья назначена правилом «ИП Волков»."
  }
}
```

- `TransactionBrief` это та же `Transaction` без полей `duplicate_of`, `duplicate_reason` и `suggestion` (вложенность в один уровень).
- `amount`: целые копейки со знаком (`in` положительная, `out` отрицательная, у `transfer` знак своей стороны). Фамилии физических лиц в `description` не хранятся: их вырезает загрузчик, комментарий ручной операции чистится так же.
- `duplicate_state`: у `status = duplicate` значение `pending` (пара не разобрана) или `confirmed` (разобрана, копия осталась в учёте как дубль); у остальных `null`. `duplicate_of` это операция пары, которая остаётся в учёте; для старых данных без пары `null`.
- `suggestion` заполнен только у `status = check` (поиск по правилам и по уже разнесённым операциям того же контрагента, без ИИ). `reason = rule`: статью даёт действующее правило; `reason = similar`: статья, которой чаще всего разнесены операции того же контрагента. Слова «Предлагаем «…»:» добавляет клиент, `text` содержит только продолжение.
- `figure`: `value = amount`, `breakdown` в сумме даёт `value`.

#### `GET /v1/transactions`

Параметры: `tab=all|check|duplicates` (по умолчанию `all`), `from=YYYY-MM-DD`, `to=YYYY-MM-DD`, `limit` (1–200, по умолчанию 50), `cursor`. Ответ `{ "items": [Transaction], "next_cursor": "…" | null }`, порядок: дата от новых к старым, затем стабильный по `id`.

- `all`: все операции, включая `check` и `duplicate`. `check`: только `status = check`. `duplicates`: только неразобранные дубли (`duplicate_state = pending`). Вкладки `check` и `duplicates` без `from/to` возвращают операции за все месяцы; `from/to` применяются, если переданы.
- Неверные `tab`, `from`, `to`, `limit`, `cursor` дают `422 validation`.

#### `GET /v1/transactions/counts`

Счётчики вкладок по всем месяцам: `{ "all": 148, "check": 12, "duplicates": 3 }` (`duplicates` это неразобранные пары). Целые числа без `Figure`: каждое число это длина списка, который открывается рядом.

#### `GET /v1/transactions/summary?month=YYYY-MM`

```json
{ "income": { "value": 29640000, "unit": "rub",
              "breakdown": [{ "label": "Выручка", "value": 16000000, "unit": "rub" }, { "label": "Выручка (эквайринг)", "value": 13640000, "unit": "rub" }],
              "source": ["bank", "vetmanager"], "note": "Доходы за сентябрь 2026: операции со статусами «учтено» и «на проверку», без дублей и переводов между счетами." },
  "expense": { "value": 28100000, "unit": "rub",
               "breakdown": [{ "label": "Аренда", "value": 18000000, "unit": "rub" }, { "label": "Без статьи", "value": 10100000, "unit": "rub" }],
               "source": ["bank", "manual"], "note": "Расходы за сентябрь 2026: …" },
  "balance": { "value": 1540000, "unit": "rub",
               "breakdown": [{ "label": "Доходы", "value": 29640000, "unit": "rub" }, { "label": "Расходы", "value": -28100000, "unit": "rub" }],
               "source": ["bank", "manual"], "note": "Сальдо месяца: доходы минус расходы. Это не остаток на счетах; переводы между своими счетами не входят." } }
```

`balance` это сальдо месяца (доходы минус расходы), не остаток на счетах. В сумму входят операции `kind` `in`/`out` со статусом `ok` и `check` (операции без статьи под подписью «Без статьи»); дубли и переводы исключены; месяц по дате операции. Разбивка `income` и `expense` по статьям, сумма разбивки равна `value`. Если операций нет, `breakdown` содержит одну строку «Нет операций» со значением 0, `source = ["manual"]`. Неверный или отсутствующий `month` даёт `422 validation`.

#### `POST /v1/transactions` (ручная операция)

Тело: `{ "kind": "in|out", "account_id": "…", "category_id": "…" | null, "date": "2026-09-09", "amount": 540000, "comment": "Такси за анализами" | null }`. `amount` положительные копейки, знак ставит `kind`; `comment` до 200 знаков (становится `description`). Ответ `201` и `Transaction` (`source = manual`). Без `category_id` статус `check`; если найдена похожая операция другого источника (тот же счёт, та же сумма со знаком, разница дат не больше 3 дней), статус `duplicate`, `duplicate_state = pending`, в `duplicate_of` её пара. Ошибки `validation` по полям: `account_id`, `date`, `amount`, `kind`: `required`; `amount`: `must_be_positive`, `too_many_decimals`, `too_large` (больше 100 000 000 ₽); `date`: `in_future` (позже «сегодня» клиники), `before_opening` (раньше `opening_date` счёта); `comment`: `too_long`. Счёт или статья другой клиники: `404 not_found`. Операции, внесённые вручную, на этапе 1 не правятся и не удаляются.

#### `PATCH /v1/transactions/{id}`

Тело: `{ "category_id": "…", "create_rule": true }` (`create_rule` по умолчанию `false`). Меняется только статья. Ответ: `Transaction` и поле `rule`:

```json
{ "...": "поля Transaction",
  "rule": { "id": "…", "match_text": "ИП Волков", "category": { "id": "…", "name": "Аренда" }, "applied_count": 3 } }
```

`rule` равен `null`, если правило не создавали, его нельзя создать (нет ИНН контрагента) или такое правило уже есть.

- Статья сохраняется, статус `check` становится `ok`. `duplicate` остаётся `duplicate`. У переводов статьи нет: `422 validation`, `fields.category_id = "invalid"`.
- При `create_rule = true` и операции с известным контрагентом (у банковских операций есть его ИНН) создаётся правило «ИНН контрагента и направление операции → статья» и добавляется в конец списка. Оно применяется к уже загруженным операциям без статьи со статусом `check` (того же контрагента и направления) и ко всем новым. Операции с уже назначенной статьёй, в том числе разнесённые вручную, не меняются. `applied_count`: сколько других операций изменило правило.
- Чужая или неизвестная операция и статья: `404 not_found`. Тело не по схеме: `422 validation`.

#### `GET /v1/transactions/{id}/rule-preview?category_id=…`

```json
{ "can_create": true, "already_exists": false, "match_text": "ИП Волков", "matches_count": 3 }
```

`can_create = false`, если у операции нет ИНН контрагента (физлицо, ручной ввод, перевод). `already_exists = true`, если правило для этого контрагента и направления уже есть. `matches_count`: сколько других операций на проверку (без статьи) попадёт под правило. `match_text`: название контрагента без ИНН, `null`, если `can_create = false`.

#### `POST /v1/transactions/{id}/resolve-duplicate`

Тело: `{ "keep_id": "…" }` или `{ "keep_both": true }` (ровно одно из двух). `{id}` любая операция пары. `keep_id` (операция пары): она остаётся в учёте (`ok`, без пометки), остальные операции пары получают `status = duplicate`, `duplicate_state = confirmed`, `duplicate_of = keep_id`. `keep_both = true`: обе операции `ok`, пара больше не предлагается как дубль. Решение можно пересмотреть тем же запросом. Ответ `200`: `{ "kept": [Transaction], "duplicates": [Transaction] }`. `keep_id` не из пары: `422 validation`, `fields.keep_id = "invalid"`; чужая или неизвестная операция: `404 not_found`.

#### `GET /v1/category-rules`, `DELETE /v1/category-rules/{id}`

```json
{ "items": [{ "id": "…", "match": "inn", "match_text": "ИП Волков", "direction": "out",
              "category": { "id": "…", "name": "Аренда" },
              "applied_count": { "value": 41, "unit": "count",
                                 "breakdown": [{ "label": "В этом месяце", "value": 6, "unit": "count" }, { "label": "Раньше", "value": 35, "unit": "count" }],
                                 "source": ["manual"], "note": "Правило применилось к 41 операции." },
              "created_at": "2026-09-09T10:00:00+03:00" }],
  "next_cursor": null }
```

Порядок это порядок применения (первое подходящее правило срабатывает): старые сверху, новое правило последним (клиент вправе показать иначе). `match`: `inn` (по ИНН контрагента) или `text` (подстрока в назначении, без учёта регистра). `match_text`: для `inn` название контрагента (ИНН не отдаётся), для `text` сама подстрока. `direction`: `in`, `out` или `null` (любое). `applied_count` считает операции, которым статью назначило это правило (операция, по которой правило создано, не входит). `DELETE` отвечает `204`; уже разнесённые операции остаются в своих статьях; чужое или неизвестное правило: `404 not_found`.

#### `GET /v1/categories`

`{ "items": [{ "id": "…", "name": "Аренда", "type": "income|variable|fixed", "norm_min_pct": 5.0, "norm_max_pct": 12.0 }], "next_cursor": null }`; `norm_*_pct` могут быть `null`. Порядок: доходы, переменные, постоянные, внутри по названию.

#### `POST /v1/imports/bank-statement`

`multipart/form-data`: `file` (обязательно, до 10 МБ), `account_id` (необязательно: счёт клиники, для которого выписка; если указан, этот счёт должен быть в файле). Выписка в формате обмена 1С (`1CClientBankExchange`, кодировки windows-1251, cp866, UTF-8). Счета из файла сопоставляются со счетами клиники по номеру (поле `number` счёта задаёт команда). Загрузка выполняется целиком в одной транзакции: либо всё, либо ничего. Повторная загрузка того же файла ничего не создаёт.

```json
{ "import_id": "…", "account": { "id": "…", "name": "Расчётный счёт" },
  "period": { "from": "2026-09-01", "to": "2026-09-22" },
  "loaded": 30, "duplicates": 3, "to_check": 9, "already_loaded": 1, "skipped": 0 }
```

`loaded`: новые операции (включая `duplicates` и `to_check`; перевод между своими счетами даёт две проводки). `duplicates`: из них помечены дублем. `to_check`: из них без статьи. `already_loaded`: строки, уже бывшие в системе, плюс повторы внутри файла (при повторной загрузке файла `loaded = 0`). `skipped`: нечитаемые документы файла. `account`: выбранный счёт, иначе первый счёт файла. Фамилии физических лиц из назначения платежа вырезаются, контрагент-физлицо не сохраняется, сам файл не хранится.

Ошибки `422 validation` с `details.reason`: `unsupported_format` (не формат 1С; сообщение по-русски, содержит «1С»), `empty` (пустой файл), `too_large`, `account_mismatch` (счёта из файла нет в клинике или он не совпадает с `account_id`; `details.account_tail` последние 4 цифры номера из файла). Слишком частые загрузки: `429 rate_limited` (больше 10 загрузок в минуту на клинику).

#### Сверка эквайринга (функция 10)

`GET /v1/acquiring/reconciliation?month=YYYY-MM`

```json
{ "settlement_days": { "min": 1, "max": 3 },
  "rate_pct": 1.9,
  "bank_covered_to": "2026-09-30",
  "summary": { "card_payments": "Figure", "commission": "Figure", "credited": "Figure", "discrepancy": "Figure", "waiting": "Figure" },
  "days": [{
    "date": "2026-09-04", "date_from": "2026-09-04", "date_to": "2026-09-06",
    "card_payments": "Figure", "commission": "Figure", "expected": "Figure",
    "credited": "Figure | null", "discrepancy": "Figure | null",
    "status": "matched|mismatch|waiting|no_statement|no_payments",
    "expected_by": "2026-09-09", "reviewed": false,
    "members": [{ "date": "2026-09-04", "card_payments": "Figure", "commission": "Figure", "expected": "Figure" }]
  }] }
```

- Карточные оплаты из Ветменеджера по дням сравниваются с зачислениями банка (операции `in` со статьёй «Выручка (эквайринг)»). Тариф банка: настройка клиники (`acquiring_rate_bp`, по умолчанию 190, то есть 1,9%; `rate_pct` отдаётся для подписи). Зачисление ждём до 3 рабочих дней (`settlement_days`); расхождение до 100 копеек считается округлением банка; одно зачисление может закрывать до 3 подряд идущих дней продаж. Алгоритм в `backend/engine/acquiring.py`, эталон `tests/golden/set02`.
- Строка `days[]` это день или группа дней, закрытых одним зачислением (`date_from`, `date_to`; `date` равен `date_from`). Суммы строки общие по группе, по дням группы `members`. Порядок строк от новых к старым; в список попадают строки, у которых `date_from` в запрошенном месяце. Дни без оплат картой не возвращаются (`no_payments` в MVP не отдаётся).
- `commission` это ожидаемая комиссия по тарифу клиники; `expected = card_payments − commission`; `discrepancy = credited − expected` (отрицательное: банк зачислил меньше). Все суммы целые копейки, у Figure сумма `breakdown` равна `value`.
- `status`: `matched` (зачисление найдено, расхождение в пределах допуска); `mismatch` (зачисление отличается больше допуска; либо срок прошёл, выписка этот срок покрывает, а зачисления нет: тогда `credited.value = 0`, `discrepancy.value = −expected`); `waiting` (срок `expected_by` ещё не прошёл, `credited` и `discrepancy` равны `null`); `no_statement` (срок прошёл, а выписка загружена только до даты раньше срока, `credited` и `discrepancy` равны `null`).
- `summary.card_payments`, `summary.commission` суммы по всем строкам месяца; `summary.credited` сумма зачислений; `summary.discrepancy` сумма расхождений по строкам, где известно зачисление; `summary.waiting` сумма `expected` по строкам `waiting`.
- `bank_covered_to`: последняя дата выписок по банковским счетам клиники, `null`, если выписок не было. `reviewed`: строка отмечена проверенной.
- Источники Figure: оплаты, комиссия и «ожидаем» `["vetmanager"]`, зачислено `["bank"]`, расхождение `["bank", "vetmanager"]`. Неверный `month` даёт `422 validation`.

`GET /v1/acquiring/days/{date}` (`date` любой день строки; для группы отдаётся вся группа):

```json
{ "date_from": "2026-09-04", "date_to": "2026-09-06",
  "payments": [{ "date": "2026-09-04", "description": "Оплата картой · счёт № 403", "amount": 1240000 }],
  "credits": [{ "date": "2026-09-07", "description": "Поступление по операциям эквайринга", "amount": 2158200, "transaction_id": "…" }],
  "review": { "reviewed": false, "note": null } }
```

Без ФИО владельцев животных. День без оплат картой: `404 not_found`.

`POST /v1/acquiring/days/{date}/review`, тело `{ "note": "…" | null }` (до 200 знаков, фамилии вырезаются). Отмечает строку (группу) проверенной, повтор идемпотентен. Ответ: строка `days[]`. Ошибки: `422 validation` (`fields.note = "too_long"`), `404 not_found`.

#### Признак устаревших данных

`data_stale` (в `GET /v1/dashboard` и в `Connection`) считает backend. Ветменеджер подключён и последняя успешная синхронизация старше 36 часов. Банк: последняя выписка (`last_statement_to`) старше 7 дней от «сегодня» клиники (если выписки были). В `GET /v1/dashboard` `data_stale = true`, если устарело любое подключение. Порог клиент не считает. Ошибка синхронизации для полосы экрана «Транзакции»: `last_run` любого подключения в `GET /v1/connections` со статусом `failed` и `error_code`.

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

Этап 0: `GET|PATCH /v1/clinic`, `GET /v1/accounts`. Этап 1: подключения, импорт выписки, категории (чтение). Направления, `shifts/close`, правка категорий и счетов вместе с экранами «Настройки» (Основное, Счета, Категории, Направления) позже. Этап 7: `audit-log`, `billing`.

- `GET|PATCH /v1/clinic` (название, юрлицо, налоговый режим, часовой пояс, `safe_balance`). Объект: `{ "id", "name", "legal_entity": string|null, "tax_regime": string|null, "timezone": "Europe/Moscow", "safe_balance": 15000000 }`. `PATCH`: любое подмножество `name`, `legal_entity`, `tax_regime`, `timezone` (IANA), `safe_balance` (целые копейки, ≥ 0); неизвестные поля дают `validation`.
- `GET|POST|PATCH /v1/accounts`. Этап 0–1: только `GET` → `{ "items": [Account], "next_cursor": null }`, `Account = { "id", "name", "kind": "bank|cash", "opening_balance": 12500003, "opening_date": "2026-08-01" }` (копейки, на начало дня `opening_date`). Счета заводит команда; номер счёта (`number`) для привязки выписки в API не отдаётся.
- Без токена или с недействительным токеном любой `/v1/*` отвечает `401` с кодом `unauthorized`. Пользователь без клиники получает `403 forbidden`. `GET /healthz` без авторизации: `{ "status": "ok" }` (вне `/v1`).
- `GET /v1/categories`: см. «Транзакции». `PATCH /v1/categories` (тип и норма) и `GET|PATCH /v1/directions` (привязка услуг и товарных групп) позже (этап 3).
- `POST /v1/shifts/close` закрытие смены: `{ "date", "cash_amount", "revenue_amount" }` позже (экран не спроектирован).
- `GET /v1/audit-log`, `POST /v1/audit-log/{id}/undo`. Откат доступен 7 дней, журнал хранится 90 дней (этап 7).
- `GET /v1/billing`, `POST /v1/billing/checkout` (ссылка на оплату в ЮКассе, этап 7).

#### Подключения

`GET /v1/connections` → `{ "items": [Connection], "next_cursor": null }`. Всегда два элемента: Ветменеджер и банк.

```json
Connection = {
  "id": "…", "type": "vetmanager|bank", "connected": true,
  "address": "aibolit.vetmanager.ru" | null,
  "key_hint": "4a7f" | null,
  "schedule": { "kind": "nightly", "time": "04:00" } | null,
  "data_stale": false,
  "last_success_at": "2026-09-09T04:12:00+03:00" | null,
  "last_run": SyncRun | null,
  "runs": [SyncRun],
  "bank": { "accounts": [{ "account": { "id": "…", "name": "Расчётный счёт" }, "last_statement_to": "2026-09-22" | null }] } | null
}

SyncRun = {
  "id": "…", "status": "running|success|partial|failed",
  "started_at": "2026-09-09T04:00:03+03:00", "finished_at": "2026-09-09T04:12:00+03:00" | null,
  "error_code": "invalid_key|unreachable|rate_limited|unknown" | null,
  "counts": { "value": 24, "unit": "count",
              "breakdown": [{ "label": "Новых операций", "value": 21, "unit": "count" }, { "label": "Обновлено", "value": 3, "unit": "count" }],
              "source": ["vetmanager"], "note": "Новых 21, обновлено 3, пропущено как дубли 2." } | null
}
```

- Ветменеджер: `connected = true`, когда сохранены адрес и ключ. `key_hint`: последние 4 знака ключа; ключ целиком никогда не возвращается и не пишется в журналы (в базе хранится зашифрованным). `schedule` задан у подключённого Ветменеджера (расписание фиксированное, время в часовом поясе клиники), у банка `null`. `runs`: последние 5 запусков, новые сверху; `last_run` равен первому. `counts`: `value = новых + обновлено`; `null`, если запуск упал до загрузки или ещё идёт. «Пропущено как дубли» в `note` и не входит в `breakdown`, чтобы сумма разбивки равнялась `value`.
- Банк: `connected = true`, если по какому-либо банковскому счёту загружалась выписка. `bank.accounts` это банковские счета клиники (`kind = bank`) с датой последней выписки; у Ветменеджера `bank = null`, у банка `address`, `key_hint`, `schedule`, `last_run` и `runs` пустые.
- `last_success_at`: окончание последнего успешного запуска (Ветменеджер) либо дата загрузки последней выписки (банк).

`PUT /v1/connections/vetmanager`: тело `{ "address": "aibolit.vetmanager.ru", "key": "…" }` (`key` необязателен, если ключ не меняют; при первом подключении обязателен). Сервер проверяет адрес и ключ запросом в Ветменеджер. Адрес принимается только в доменах Ветменеджера (`*.vetmanager.ru`, `*.vetmanager.cloud`, `*.vetmanager2.ru`), схема `https://` и путь отбрасываются. Ошибки `422 validation`: `fields.address = "unreachable"` (адрес недоступен или не из доменов Ветменеджера) и `fields.key = "invalid"` (ключ не принят), `fields.key = "required"` (первое подключение без ключа). Успех: `200` и `Connection`; при первом подключении сразу запускается первая синхронизация (в ответе `last_run.status = running`). Ключ в ответах и логах не появляется.

`POST /v1/connections/{id}/sync`: `202` и `{ "run": SyncRun }` (запуск идёт в фоне, состояние смотрится в `GET /v1/connections`). `409 conflict`, если запуск уже идёт; `429 rate_limited` (с `Retry-After`), если предыдущий запуск начался меньше 5 минут назад; `422 validation` (`details.reason = "not_syncable"`), если подключение не Ветменеджер или не подключено; чужое подключение: `404 not_found`.

`PUT /v1/connections/bank` на этапе 1 не реализуется: банк это загрузка файла (`POST /v1/imports/bank-statement`), интерфейс подключения не использует.

`POST /v1/connections/vetmanager/import` (служебный, для тестов и ручной загрузки без живого Ветменеджера; включён переменной `VETMANAGER_IMPORT_ENABLED=true`, иначе `404`): тело `{ "entities": { "user": {…}, "admission": {…}, "invoice": {…}, "invoiceDocument": {…}, "good": {…}, "payment": {…}, "cassa": {…} } }`, где значение это полный JSON-ответ REST API Ветменеджера по сущности. Обрабатывается так же, как синхронизация; ответ `{ "run": SyncRun }` (запуск завершён). Данные клиентов (`client`, `pet`) не принимаются и не сохраняются.

#### Что загружается из Ветменеджера

Врачи (код `D1`, `D2`… и имя; имя не уходит в ИИ-слой), приёмы (дата, врач), счета (дата, статус, сумма, строки «услуга/товар»), платежи. Черновики счетов в выручку не входят, удалённые счета и приёмы отбрасываются. Платежи наличными становятся операциями кассы (`source = vetmanager`, статья «Выручка»); платежи картой операциями не становятся, они идут в сверку эквайринга. ФИО клиентов, телефоны, адреса и свободный текст приёмов не загружаются.

## Вне контракта первой очереди

Telegram-бот (42–49), живые ответы Claude, экран «Врачи» (16), рекомендации по цене (13), сценарий из вопроса (30), уточнение прогноза (32), админка основателя (50–52) подробно описываются перед своим этапом.
