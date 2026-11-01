# agent-tester

Универсальный автотестер диалоговых ИИ-агентов: голосовых и текстовых, на TWIN и других платформах.
Симулятор клиента ведёт диалоги по сценариям, судья оценивает ответы агента, тестер считает метрики качества
и задержки, сравнивает прогоны и подсказывает правки к промпту.

## Возможности

- **Подключения к платформам:** ИИ-агент TWIN, сценарный бот TWIN, OpenAI-совместимый API, универсальный HTTP,
  локальный агент на своей модели (Ollama и др.).
- **Ручной чат с агентом** с кнопками ▶ / ■, как в TWIN.
- **Режимы автотеста:**
  - шаблон — реплики клиента дословно из сценария;
  - LLM-помощник по шаблону — клиент говорит своими словами, но держится сценария;
  - свободный клиент — LLM играет клиента по описанию;
  - только судья — оценка готовых диалогов.
- **Судья** с цитатами из диалога, калибровка судьи на эталонных оценках.
- **Отчёт аналитика** с конкретными правками к промпту.
- **Метрики** качества и задержки, сравнение прогонов, экспорт в Excel и текст.
- **Анализ аудиозаписей звонков:** распознавание речи (faster-whisper), роли, паузы, таймлайн.
- **Автоподбор** модели, температуры и таймаута (Optuna).
- **Уведомления в Telegram** об окончании прогона и анализа аудио.
- **Вход по логину и паролю** с «Запомнить меня». Пользователей заводит администратор из консоли.

## Быстрый старт (локально, Windows)

Нужны Python 3.11+ и [Poetry](https://python-poetry.org/).

```bash
poetry install
copy .env.example .env          # Linux/macOS: cp .env.example .env
# заполнить .env (см. раздел «Настройки»)
poetry run python scripts/users.py add
poetry run python -m streamlit run app/Home.py
```

Откроется http://localhost:8501. Войди под пользователем, которого создал командой `users.py add`.

> Запускай именно через `python -m streamlit`, а не просто `streamlit run`.
> Иначе Python не найдёт пакет `app` и упадёт с ошибкой `No module named 'app'`.

## Настройки (`.env`)

Файл `.env` лежит в корне проекта и в git не попадает. Шаблон — `.env.example`.

| Переменная | Зачем |
|---|---|
| `MASTER_KEY` | Ключ шифрования паролей и API-ключей подключений в базе. Без него секреты хранятся открыто. |
| `DB_URL` | Путь к базе, по умолчанию `sqlite:///data/tester.db`. |
| `OLLAMA_URL` | Адрес Ollama для локальных моделей, например `http://100.110.207.76:11434`. |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_FALLBACK_MODELS` | Облачные модели для клиента и судьи через OpenRouter. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Уведомления в Telegram. |
| `AUTH_SECRET` | Ключ подписи cookie «Запомнить меня». Необязательный: без него ключ создаётся сам в `data/.auth_secret`. |
| `TAILSCALE_IP` | Только для Docker: адрес сервера в сети Tailscale, на котором открывается порт. |

Сгенерировать `MASTER_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> **Важно.** Если базу переносишь на другую машину, переноси вместе с ней и `MASTER_KEY`.
> С другим ключом сохранённые пароли подключений не расшифруются.

## Пользователи

Регистрации в интерфейсе нет: пользователей заводит администратор из консоли.

```bash
python scripts/users.py add       # создать пользователя или сменить пароль
python scripts/users.py delete    # удалить пользователя
python scripts/users.py list      # список пользователей и время последнего входа
```

Как устроена защита:
- Пароль вводится скрыто, нужен дважды и минимум 8 символов.
- Пароли хранятся как хэш PBKDF2-SHA256 с солью.
- После 5 неудачных попыток вход под этим именем блокируется на 5 минут.
- «Запомнить меня» хранит подписанный токен в cookie 30 дней.
- Смена пароля или удаление пользователя сразу закрывают все его сохранённые входы.

## Деплой на сервер (Docker + Tailscale)

Тестер доступен только из твоей сети Tailscale. Из интернета и локальной сети порт закрыт.

### 1. Подключить сервер к Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4                  # адрес сервера в сети, вида 100.x.y.z
```

В админке Tailscale (https://login.tailscale.com/admin/machines) у сервера выбери **Disable key expiry**.
Иначе примерно через 180 дней сервер выпадет из сети.

Чтобы после перезагрузки Docker стартовал после Tailscale и порт поднимался:

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
printf '[Unit]\nAfter=tailscaled.service\nWants=tailscaled.service\n' | sudo tee /etc/systemd/system/docker.service.d/tailscale.conf
sudo systemctl daemon-reload
```

### 2. Запустить тестер

```bash
cd ~/AI-agent-testing-automation
cp .env.example .env               # заполнить, добавить TAILSCALE_IP=100.x.y.z
mkdir -p data                      # при переносе положить сюда старую tester.db
docker compose up -d --build
docker compose exec app python scripts/users.py add
```

Тестер откроется по адресу `http://<TAILSCALE_IP>:8501` с любого устройства в сети Tailscale.

### Полезные команды

```bash
docker compose logs -f app                        # логи
docker compose ps                                 # статус и healthcheck
git pull && docker compose up -d --build          # обновить после изменений в коде
docker compose exec app python scripts/users.py list
```

### Что хранится вне контейнера

- `./data` — база, прогоны, аудио, ключ cookie. Его и нужно бэкапить.
- Том `hf_cache` — модели faster-whisper, чтобы не скачивать их после пересборки.

### Особенности

- **Адреса Ollama и Whisper.** В настройках тестера указывай `100.110.207.76:11434` и `:7860`, а не `localhost`.
  Внутри контейнера `localhost` означает сам контейнер.
- **Порт открыт только на `TAILSCALE_IP`.** Docker обходит ufw, поэтому вариант `"8501:8501"` открыл бы порт всем.
- **HTTPS (по желанию).** Включи в админке Tailscale MagicDNS и HTTPS Certificates, поставь в `.env`
  `TAILSCALE_IP=127.0.0.1` и выполни `sudo tailscale serve --bg 8501`.
  Тестер откроется по `https://<имя-сервера>.<tailnet>.ts.net`.
- **Ошибка сборки из-за `poetry.lock`.** Если `pyproject.toml` менялся, сделай `poetry lock` локально
  и закоммить новый `poetry.lock`.

## Запуск из терминала (CLI)

Для расписания и CI, без интерфейса:

```bash
poetry run python cli.py run "Елена" --mode scripted --repeats 2   # прогон проекта
poetry run python cli.py calibrate "Елена"                          # калибровка судьи
poetry run python cli.py tune "Елена" --trials 25                   # автоподбор параметров
poetry run python cli.py --help
```

Режимы: `scripted`, `guided`, `simulated`, `judge_only`. При ошибке прогона код выхода 1.

## Тесты

```bash
poetry install --extras dev
poetry run pytest
```

## Структура

```
app/                  интерфейс Streamlit
  Home.py             точка входа: вход, навигация
  components/         общие элементы: вход, чат, метрики, таймлайн, волна
  pages/              страницы: подключения, сценарии, запуск, чат, результаты, аудио…
core/                 ядро без UI, используется и интерфейсом, и CLI
  platforms/          подключения к агентам (TWIN, OpenAI-совместимые, HTTP, локальный)
  clients/            симуляторы клиента (шаблон, помощник, свободный)
  engine/             ход диалога и прогоны
  evaluation/         судья, проверки, калибровка, аналитик
  metrics/            качество и задержка
  voice/              распознавание и разбор аудиозвонков
  tuning/             автоподбор параметров (Optuna)
  notify/             уведомления в Telegram
  storage/            база SQLite и шифрование секретов
  auth.py             пользователи и токены входа
scripts/users.py      управление пользователями из консоли
cli.py                запуск из терминала
tests/                тесты самого тестера
data/                 база и файлы прогонов (не в git)
```