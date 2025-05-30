from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis
import json
from typing import List, Optional
from datetime import datetime
import os
from dateutil.parser import parse
from dateutil import tz
import asyncio

# Inicialização do cliente Redis usando variáveis de ambiente
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    decode_responses=True
)

app = FastAPI(
    title="Minha API",
    description="Uma API de exemplo usando FastAPI",
    version="1.0.0"
)

class ImageContent(BaseModel):
    image_id: str
    content_url: str

class Message(BaseModel):
    message_id: str
    chat_id: str
    content_type: str
    content: str | ImageContent
    timestamp: str
    event: str
    user_name: str

def parse_timestamp(timestamp_str: str) -> datetime:
    """Converte string de timestamp para objeto datetime."""
    return parse(timestamp_str).astimezone(tz.UTC)

async def check_message_flow(chat_id: str, current_message: Message) -> str:
    """
    Verifica o fluxo da mensagem baseado nas condições especificadas.
    Implementa lógica de agrupamento de mensagens em sequência.
    """
    try:
        # Obtém todas as mensagens do buffer
        buffer_messages = redis_client.lrange(f"chat:{chat_id}", 0, -1)
        
        if not buffer_messages:
            return "prosseguir"
        
        # Converte as mensagens do buffer
        messages = [Message(**json.loads(msg)) for msg in buffer_messages]
        
        # Primeira mensagem do buffer (mais antiga)
        first_message = messages[-1]
        # Última mensagem do buffer (mais recente)
        last_message = messages[0]
        
        # Se o ID da primeira mensagem é diferente da atual
        if first_message.message_id != current_message.message_id:
            return "nada a fazer"
        
        # Verifica o tempo desde a última mensagem
        current_ts = datetime.now(tz.UTC)
        last_message_ts = parse_timestamp(last_message.timestamp)
        time_diff = (current_ts - last_message_ts).total_seconds()
        
        # Se passou mais de 3 segundos desde a última mensagem
        if time_diff > 3:
            return "prosseguir"
        
        # Se chegou aqui, significa que ainda estamos dentro da janela de 3 segundos
        return "esperar"
            
    except Exception as e:
        print(f"Erro ao verificar fluxo: {str(e)}")
        return "prosseguir"  # Em caso de erro, permite prosseguir

@app.get("/")
async def root():
    return {"mensagem": "Bem-vindo à minha API FastAPI!"}

@app.post("/message/{chat_id}")
async def send_message(chat_id: str, message: Message):
    try:
        # 1. Insere mensagem no buffer
        redis_client.lpush(f"chat:{chat_id}", json.dumps(message.dict()))
        
        # 2 e 3. Verifica o fluxo da mensagem
        flow_status = await check_message_flow(chat_id, message)
        print(f"Status do fluxo: {flow_status}")
        
        # Se precisar esperar, aguarda 3 segundos antes de retornar
        if flow_status == "esperar":
            await asyncio.sleep(3)
            # Verifica novamente após a espera
            flow_status = await check_message_flow(chat_id, message)
            print(f"Status do fluxo após espera: {flow_status}")
        
        return {
            "status": "success",
            "data": message.dict(),
            "flow_status": flow_status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem: {str(e)}")

@app.get("/messages/{chat_id}", response_model=List[Message])
async def get_messages(chat_id: str, limit: int = 10):
    try:
        messages = redis_client.lrange(f"chat:{chat_id}", 0, limit - 1)
        return [Message(**json.loads(msg)) for msg in messages]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao recuperar mensagens: {str(e)}")

@app.delete("/messages/cleanup")
async def cleanup_messages():
    try:
        chat_keys = redis_client.keys("chat:*")
        if chat_keys:
            redis_client.delete(*chat_keys)
        return {"status": "success", "message": "Todas as mensagens foram removidas"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao limpar mensagens: {str(e)}")

@app.get("/health")
async def health_check():
    try:
        redis_client.ping()
        return {"status": "healthy", "redis": "connected"}
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Redis não está disponível")
