FROM python:3.12-slim

WORKDIR /app

# Instala netcat para verificar a disponibilidade do postgres
RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x run_migrations.sh

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 