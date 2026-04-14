FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.deploy.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.deploy.txt

COPY . .

ENV PORT=8080

CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py migrate && gunicorn codegaze.wsgi:application --bind 0.0.0.0:${PORT}"]