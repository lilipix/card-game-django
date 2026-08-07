FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /home/app app

COPY pyproject.toml README.md ./
COPY . /app

# 🔹 /app/staticfiles a été ajouté ici à la commande mkdir -p
RUN pip install --upgrade pip && \
    pip install -e . && \
    mkdir -p /home/app /app/staticfiles && \
    chown -R app:app /home/app /app

USER app

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000"]