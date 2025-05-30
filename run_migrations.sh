#!/bin/bash

# Espera o PostgreSQL estar pronto
echo "Aguardando PostgreSQL..."
while ! nc -z postgres 5432; do
  sleep 1
done
echo "PostgreSQL está pronto!"

# Executa as migrações
export DATABASE_URL="postgresql://user:password@postgres:5432/dbname"
alembic upgrade head 