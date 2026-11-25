# Keitaro Campaign & Stream Wrapper

Веб-обёртка над Admin API трекера Keitaro для быстрого запуска кампаний и безопасного управления сплитом офферов в потоках.

## Функциональность

- **Создаватор кампаний:** создание кампании в Keitaro в один шаг (автоматический подбор домена, группы и источника трафика) с двумя потоками:
  - `Flow 1`: фильтр страны (`country`, `mode=accept`) с редиректом на `https://google.com`;
  - `Flow 2`: поток `schema=landings` с выбранным оффером со 100% долей.
- **Редактор потоков и офферов:**
  - отображение потоков кампании в порядке `position` (потоки без офферов показываются компактно, потоки `schema=landings` открываются в виде таблицы офферов);
  - локальный черновик изменений (`Unpublished changes`) с кнопками `ADD`, `REMOVE`, `BRING BACK`, `CANCEL` и `PUSH TO KT`;
  - мягкое удаление офферов: после `REMOVE` + `PUSH TO KT` оффер удаляется из Keitaro, но остаётся в локальной таблице со статусом `removed` (`0%`) для возврата в один клик через `BRING BACK`;
  - закрепление долей (`Pin`): перераспределение весов затрагивает только незакреплённые активные офферы; изменение пина не переводит поток в `is_dirty`;
  - синхронизация с Keitaro (`FETCH STREAMS FROM KT`): загрузка фактических долей из трекера без автоматического пересчёта, пометка исчезнувших в Keitaro офферов как `removed` и встроенное подтверждение перезаписи при наличии несохранённых черновиков.

## Стек

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2.0 (синхронный), Alembic, httpx, pydantic-settings, uv
- **Database:** PostgreSQL 16 (поддерживается также SQLite для локальных проверок и тестов)
- **Frontend:** React 19, TypeScript, Vite, lucide-react

## Настройка окружения

1. Скопируйте шаблон переменных окружения:
   ```bash
   cp .env.example .env
   ```
2. Заполните в `.env` параметры доступа к Keitaro:
   - `KEITARO_BASE_URL` — базовый URL Admin API (например, `https://keitaro-for-tests.etolegko.com/admin_api/v1`)
   - `KEITARO_ADMIN_URL` — URL админки для кнопки `VIEW IN KT` (например, `https://keitaro-for-tests.etolegko.com/admin`)
   - `KEITARO_API_KEY` — API-ключ из админки Keitaro (раздел **Профиль -> API ключи** или кнопка **API ключ** в верхней панели)

Файл `.env` добавлен в `.gitignore` и не должен попадать в репозиторий.

## Запуск через Docker (рекомендуемый)

Сборка и запуск одной командой:

```bash
docker compose up --build
```

Что происходит при запуске:
1. Поднимается контейнер PostgreSQL (`db`) с healthcheck.
2. Собирается фронтенд (`frontend/dist`) и backend-образ (`app`).
3. Контейнер `app` автоматически применяет миграции `alembic upgrade head` и запускает `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
4. Внутри Docker-сети для сервиса `app` переменная `DATABASE_URL` переопределяется на `db:5432`, поэтому приложение подключается к контейнеру `db` независимо от хостового значения в `.env`.

После старта приложение (API и собранный UI) доступно по адресу `http://localhost:8000`.

Если на хосте уже занят порт `5432` или `8000`, задайте в `.env` свободные порты:
```env
POSTGRES_HOST_PORT=5433
APP_HOST_PORT=8000
```

## Локальный запуск и миграции вручную

### 1. База данных

Поднимите PostgreSQL через Docker Compose:
```bash
docker compose up -d db
```
Либо переключите `DATABASE_URL` в `.env` на локальный SQLite:
```env
DATABASE_URL=sqlite:///./local.db
```

### 2. Backend и миграции Alembic

```bash
cd backend
uv sync
uv run alembic upgrade head
```

Основные команды Alembic:
- Применить все миграции: `uv run alembic upgrade head`
- Откатить последнюю миграцию: `uv run alembic downgrade -1`
- Сгенерировать новую миграцию по моделям: `uv run alembic revision --autogenerate -m "describe_change"`

Запуск API-сервера:
```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Frontend (dev-режим)

```bash
cd frontend
npm install
npm run dev
```

Dev-сервер Vite запускается на `http://localhost:5173` и проксирует запросы `/api` на `http://127.0.0.1:8000`.

## Архитектурные решения

- **Двухслойное состояние в `stream_offers`:** каждая строка хранит пару `published_state` / `published_share` и `draft_state` / `draft_share`. Поток считается изменённым (`is_dirty = true`), когда у любой строки `published_state != draft_state` или у активной строки `published_share != draft_share`. Это позволяет без потерь откатывать черновик (`CANCEL`) и сохранять удалённые строки (`removed`) для `BRING BACK`.
- **Сохранение `raw_payload` потока:** при синхронизации поток сохраняет исходный JSON из Keitaro в `streams.raw_payload`. При `PUSH TO KT` запрос `PUT /streams/{id}` строится на базе `raw_payload` с заменой только массива `offers`, чтобы не затирать фильтры и остальные настройки потока. Признак таблицы офферов (`has_offers`) определяется строго по `schema == "landings"`.
- **Математика весов с пинами (`app/services/weights.py`):** сумма `100 - sum(pinned_shares)` делится поровну в целых числах (`divmod`) между незакреплёнными активными офферами в стабильном порядке; закреплённые офферы сохраняют заданный вес. Перед `PUSH TO KT` проверяется непустота активных офферов, диапазон `1..100` и точная сумма `100%`.
- **Изоляция адаптера (`app/keitaro/`):** все URL, заголовки (`Api-Key`, явный `User-Agent`), маппинг payload и keep-alive пул с ретраями подключения инкапсулированы в `KeitaroClient` и `mapper.py`.

## Тесты и проверки качества

Backend (из директории `backend/`):
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -v
```

Frontend (из директории `frontend/`):
```bash
npx tsc --noEmit
npm run build
```
