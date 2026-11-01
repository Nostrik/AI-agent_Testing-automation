FROM python:3.12-slim

# Зеркала PyPI: сервер без VPN, pypi.org из России работает с перебоями.
# Основное — Яндекс, запасное — Цинхуа (pip ищет пакет в обоих). Поменять можно в docker-compose.yml → args.
ARG PIP_INDEX_URL=https://mirror.yandex.ru/pypi/web/simple/
ARG PIP_EXTRA_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_RETRIES=10 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}

WORKDIR /app

# Зависимости отдельным слоем: пересобираются только при изменении pyproject/poetry.lock.
# Poetry в образе не нужен: версии берутся из poetry.lock и ставятся обычным pip через зеркало.
COPY pyproject.toml poetry.lock ./
COPY docker/lock_to_pip.py docker/
RUN python docker/lock_to_pip.py . \
 && pip install -r requirements.txt -c constraints.txt

COPY . .

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"

CMD ["python", "-m", "streamlit", "run", "app/Home.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
