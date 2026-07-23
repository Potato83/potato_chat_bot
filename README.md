# 🥔 Potato Chat Bot

Telegram-бот для групп на aiogram 3. Экономика, магазин, займы и игры работают
поверх транзакционного SQLite-ledger: ставки резервируются заранее, а повторный
callback или рестарт процесса не может повторно начислить выигрыш.

## Что умеет бот

- `/dig` — добыча 1–10 🥔 с настраиваемым кулдауном.
- `/give` — атомарный перевод ответом на сообщение.
- `/top` — баланс и винрейт участников.
- `/flip`, `/roulette`, `/bj` — казино с целыми ставками и серверной проверкой.
- `/pvp`, `/rps` — персистентные вызовы со ставками в резерве.
- `/shop`, `/settitle`, `/sleep` — предметы, титулы и игровая модерация.
- `/zaim` — 50 🥔 сейчас, автоматический возврат 55 🥔 через 30 минут.
  При нехватке средств баланс становится отрицательным долгом. Следующий займ
  доступен через 60 минут после срока возврата и только после погашения долга.
- `/admin` в личном чате — настройки групп и безопасный сброс с backup.

## Быстрый запуск

Требуются Docker и Docker Compose.

```bash
git clone https://github.com/Potato83/potato_chat_bot.git
cd potato_chat_bot
cp .env.example .env
```

Укажите в `.env`:

```env
BOT_TOKEN=токен_от_BotFather
MY_ID=ваш_telegram_id
TLS_VERIFY=true
```

Запуск:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f potato_bot
```

База и автоматические backup хранятся в Docker volume `potato_bot_data`.
Контейнер работает без root, с read-only root filesystem и healthcheck.

### Перенос старой `bot_database.db`

Остановите старого бота и сделайте отдельную копию файла. Затем:

```bash
docker compose up -d --build
docker compose stop potato_bot
docker compose run --rm \
  -v "$PWD/bot_database.db:/tmp/legacy.db:ro" \
  potato_bot sh -c 'cp /tmp/legacy.db /app/data/bot_database.db'
docker compose up -d
```

На первом старте перед миграцией бот сам создаст дополнительный backup. Схема
обновляется версионированно и сохраняет существующие балансы, инвентарь и
настройки.

## VPN, proxy и TLS

Проверка сертификатов включена по умолчанию и применяется только к HTTP-сессии
Telegram:

```env
PROXY_URL=socks5://host:port
TLS_VERIFY=true
TLS_CA_FILE=/app/data/custom-ca.pem
```

Для локального VPN с подменным сертификатом лучше передать его CA через
`TLS_CA_FILE`. Если это невозможно, можно явно установить `TLS_VERIFY=false`;
глобальные настройки `aiohttp` при этом не меняются.

## Локальная разработка

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
python -m pytest -q
bandit -r . -x ./tests
python main.py
```

Настройки:

| Переменная | По умолчанию | Назначение |
| --- | ---: | --- |
| `DATABASE_PATH` | `./bot_database.db` | Абсолютный или относительный путь БД |
| `BACKUP_DIR` | `./backups` | Каталог автоматических backup |
| `MIN_BET` | `1` | Минимальная ставка |
| `MAX_BET` | `1000000` | Максимальная ставка |
| `MAX_BALANCE` | `9000000000000000` | Защитная граница целого баланса |
| `GAME_TTL_SECONDS` | `900` | Срок жизни незавершённой игры |

## Гарантии экономики

- все денежные изменения проходят через таблицу `operations`;
- `operation_key` уникален, поэтому retry не дублирует списание или выплату;
- transfer и игровые расчёты выполняются через `BEGIN IMMEDIATE`;
- ставки PvP/RPS/блэкджека вычитаются из доступного баланса до начала игры;
- просроченная незавершённая игра возвращает резерв;
- игры используют `secrets.SystemRandom`, дробные балансы запрещены;
- отрицательный баланс создаёт только разрешённое взыскание займа или действие
  владельца; тратить деньги из долга нельзя.

SQLite-конфигурация рассчитана на один контейнер бота с общей локальной БД. Для
нескольких реплик нужен общий PostgreSQL/Redis deployment, а не копии SQLite.

## Backup и восстановление

Админский сброс чата всегда создаёт полный backup. Для ручной копии:

```bash
docker compose exec potato_bot \
  python -m scripts.backup_db
```

Восстановление выполняйте только при остановленном боте. Скрипт проверит backup,
сохранит текущую БД и применит миграции:

```bash
python -m scripts.restore_db /путь/к/backup.db \
  --target /путь/к/bot_database.db
```

## CI/CD

Runtime-зависимости зафиксированы в `requirements.lock`, а инструменты разработки
отделены в `requirements-dev.txt`.

Workflow компилирует проект, запускает Bandit без отключения `B311`, выполняет
тесты, собирает один образ с тегом полного commit SHA и публикует его в GHCR.
Production разворачивает именно этот образ и проверяет healthcheck.

Для deploy нужны secrets:

- `HOST`, `USERNAME`, `SSH_KEY`, `PORT`, `WORK_DIR`;
- `GHCR_USERNAME`, `GHCR_TOKEN` с правом чтения образа.

На сервере в `WORK_DIR` должны находиться `docker-compose.yml` и production
`.env`.
