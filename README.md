# Projeto FastAPI

Este é um projeto básico usando FastAPI.

## Instalação

1. Crie um ambiente virtual (recomendado):
```bash
python -m venv venv
source venv/bin/activate  # No Linux/Mac
# ou
.\venv\Scripts\activate  # No Windows
```

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

## Executando o projeto

Para iniciar o servidor de desenvolvimento:
```bash
uvicorn main:app --reload
```

O servidor estará disponível em `http://127.0.0.1:8000`

## Documentação da API

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

