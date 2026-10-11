# VetFinance: frontend

React + TypeScript (strict) + Vite, React Router, TanStack Query. Без UI-библиотек: стили на CSS-переменных из `design/tokens.css`, шрифт Onest из `@fontsource/onest`. Состояние этапа 0: вход, оболочка с меню, Рабочий стол с карточками «Остаток на счетах» и «В банке» и подсказкой `FigureTip`.

## Запуск

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, mock-сервер включён, вход принимает любую почту и пароль
```

| Скрипт | Что делает |
| --- | --- |
| `npm run dev` | Vite dev server |
| `npm run build` | `tsc --noEmit` и `vite build` в `dist/` |
| `npm run preview` | Раздаёт собранный `dist/` |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint (flat config, `jsx-a11y`, `react-hooks`) |
| `npm test` | Vitest + Testing Library + MSW |
| `npm run gen:api` | Типы API из `../backend/openapi.json` в `src/api/schema.gen.ts` |
| `npm run sync:design` | Копирует `design/tokens.css` и `design/icons.svg` в `src/` |

Node 20+ (проверено на Node 24, npm 11).

## Переменные окружения

Файл `.env.example` содержит список без значений. Реальные `.env*` не коммитятся (`frontend/.gitignore`). Переменные `VITE_*` попадают в бандл и публичны: в них только URL и публичный anon-ключ Supabase, секретов нет.

| Переменная | Назначение |
| --- | --- |
| `VITE_API_URL` | Адрес backend (`https://api.example.com`, без `/v1`). **Не задана: работает mock-сервер**, вход без Supabase |
| `VITE_SUPABASE_URL` | Адрес проекта Supabase (нужен, когда задан `VITE_API_URL`) |
| `VITE_SUPABASE_ANON_KEY` | Публичный anon-ключ Supabase (то же условие) |

## Mock-режим

Без `VITE_API_URL` в браузере поднимается MSW (`src/mocks/`), запросы `/v1/clinic`, `/v1/accounts`, `/v1/dashboard` отвечают данными из `tests/golden/set01` (клиника A, 2026-09-09: всего 2 282 658,55 ₽, в банке 2 149 716,25 ₽). Без заголовка `Authorization: Bearer` mock отвечает `401`, как backend. Тот же набор обработчиков работает в Vitest.

Состояния для проверки глазами: откройте кабинет с `?mock=<имя>` (запоминается до закрытия вкладки):

| `?mock=` | Что показывает |
| --- | --- |
| `default` | Данные клиники A |
| `empty` | Нет счетов (`breakdown` пуст) |
| `zero` | Счета есть, остаток 0 |
| `negative` | Отрицательный остаток |
| `error` | `500 sync_failed` на дашборде |
| `network` | Обрыв сети |
| `slow` | Ответ через 10 с (подсказка «дольше обычного») |
| `noclinic` | `403 forbidden`, «почта не привязана к клинике» |
| `expired` | `401`, возврат на вход с сообщением |

В mock-режиме пароль `wrong` имитирует неверные данные. Сессия mock-входа хранится в `sessionStorage` (только в mock-режиме).

Реальный API: задайте `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`. Токен Supabase-сессии уходит в `Authorization: Bearer`. Backend должен разрешить CORS для адреса фронтенда (запрос в `docs/handoff.md`).

**Внимание:** сборка без `VITE_API_URL` запускает mock даже в production. Для деплоя переменная обязательна.

## Токены и шрифт

Источник правды: `design/tokens.css` и `design/icons.svg`; в `frontend/` они **копируются** скриптом `npm run sync:design` в `src/styles/tokens.css` и `src/assets/icons.svg` и лежат в git. Причина: сборка должна работать, даже если на хостинге корнем задана только папка `frontend/`. Тест `src/styles/design-sync.test.ts` падает, если копия разошлась с `design/`. Правки токенов делаются только в `design/`, затем `npm run sync:design`.

## Типы API

`src/api/schema.gen.ts` генерируется из `backend/openapi.json` (`npm run gen:api`), руками не правится. Все типы ответов, `Figure` и формат ошибок собраны в одном модуле `src/api/types.ts`. Деньги форматирует только `formatMoney` в `src/lib/format.ts` (копейки в строку, вычислений сумм нет).

## Структура

```
src/
  api/        клиент (Bearer, ошибки по контракту, 401), типы, запросы TanStack Query
  auth/       Supabase Auth и mock-вход за одним интерфейсом AuthClient
  components/ KpiCard, FigureTip, Pill, PageHeader, Icon
  lib/        format (formatMoney и др.), config, хуки
  mocks/      MSW: фикстуры из set01, обработчики, сценарии ?mock=
  pages/      LoginPage, DashboardPage, заглушки
  shell/      оболочка, меню (данные со status ready|soon|hidden), боковая панель
```

Раздел меню открывается правкой `status` в `src/shell/menu.ts` и добавлением маршрута в `src/App.tsx`.

## Тестовые идентификаторы для e2e (`tests/e2e/smoke.spec.ts`)

`balance-total` (карточка остатка, есть только когда данные загружены), `balance-bank`, `figure-tip-trigger` (кнопка внутри карточки), `figure-tip` (подсказка, рисуется в корне документа). Поля входа находятся по label «Почта» и «Пароль», кнопка «Войти».

## Деплой (статический сайт)

Решение о хостинге за главным агентом. Подходит любой статический хостинг (Railway static, Nginx, Cloudflare Pages и т. п.).

```bash
cd frontend
npm ci
npm run build          # результат в frontend/dist
```

Переменные нужны **на этапе сборки** (Vite вшивает их в бандл): `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`. Корень сборки: `frontend/`; директория публикации: `dist`. Нужен SPA-fallback: любой неизвестный путь отдаёт `index.html` (иначе прямой заход на `/transactions` даёт 404). Для Railway: сервис со статической раздачей `dist` (например `npx serve -s dist -l $PORT` после сборки). Файл `public/mockServiceWorker.js` в сборку попадает, но без `VITE_API_URL` не используется.
