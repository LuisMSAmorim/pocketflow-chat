from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
import os
from dateutil.parser import parse
from dateutil import tz
import asyncio

# Inicialização do cliente Redis
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

# Modelos atualizados para o webhook
class DeviceListMetadata(BaseModel):
    senderKeyHash: str
    senderTimestamp: str
    recipientKeyHash: str
    recipientTimestamp: str

class MessageContextInfo(BaseModel):
    deviceListMetadata: DeviceListMetadata
    deviceListMetadataVersion: int
    messageSecret: str

class WhatsAppMessage(BaseModel):
    conversation: Optional[str] = None
    messageContextInfo: Optional[MessageContextInfo] = None

class MessageKey(BaseModel):
    remoteJid: str
    fromMe: bool
    id: str

class WebhookData(BaseModel):
    key: MessageKey
    pushName: str
    message: WhatsAppMessage
    messageType: str
    messageTimestamp: int
    instanceId: str
    source: str

class WebhookPayload(BaseModel):
    event: str
    instance: str
    data: WebhookData
    destination: str
    date_time: str
    sender: str
    server_url: str
    apikey: str

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

def map_webhook_to_message(webhook: WebhookPayload) -> Message:
    """
    Mapeia o payload do webhook para nosso modelo Message.
    """
    return Message(
        message_id=webhook.data.key.id,
        chat_id=webhook.data.key.remoteJid,
        content_type=webhook.data.messageType,
        content=webhook.data.message.conversation or "",
        timestamp=webhook.date_time,
        event=webhook.event,
        user_name=webhook.data.pushName
    )

def parse_timestamp(timestamp_str: str) -> datetime:
    """Converte string de timestamp para objeto datetime."""
    return parse(timestamp_str).astimezone(tz.UTC)

async def process_buffer_messages(chat_id: str) -> Message:
    """
    Processa as mensagens do buffer após o status 'prosseguir'.
    Retorna a última mensagem ordenada.
    """
    try:
        # 1. Obtém e remove todas as mensagens do buffer
        buffer_messages = redis_client.lrange(f"chat:{chat_id}", 0, -1)
        redis_client.delete(f"chat:{chat_id}")
        
        if not buffer_messages:
            raise ValueError("Buffer vazio")
            
        # 2. Converte e ordena as mensagens por timestamp
        messages = [Message(**json.loads(msg)) for msg in buffer_messages]
        messages.sort(key=lambda x: parse_timestamp(x.timestamp))
        
        # 3. Prepara o conteúdo para salvar no banco
        content_parts = []
        for msg in messages:
            if isinstance(msg.content, str):
                content_parts.append(msg.content)
            else:
                content_parts.append(f"[Image: {msg.content.image_id}]")
        
        formatted_content = "\n".join(content_parts)
        db_entry = {
            "type": "human",
            "content": formatted_content.replace('"', '`'),
            "additional_kwargs": {},
            "response_metadata": {}
        }
        
        # Simula salvamento no banco imprimindo a entrada
        print("\nMensagem a ser salva no banco:")
        print(json.dumps(db_entry, indent=2))
        
        # 4. Retorna a última mensagem ordenada
        return messages[-1]
        
    except Exception as e:
        print(f"Erro ao processar buffer: {str(e)}")
        raise

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
        
        # Última mensagem do buffer (mais recente)
        last_message = messages[0]
        
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

@app.post("/message")
async def send_message(webhook: WebhookPayload):
    try:
        # Converte o webhook para nosso modelo de mensagem
        message = map_webhook_to_message(webhook)
        chat_id = message.chat_id

        # 1. Insere mensagem no buffer
        redis_client.lpush(f"chat:{chat_id}", json.dumps(message.dict()))
        
        # 2. Verifica o fluxo da mensagem
        flow_status = await check_message_flow(chat_id, message)
        print(f"Status do fluxo: {flow_status}")
        
        response_data = {"status": "success", "data": message.dict(), "flow_status": flow_status}

        # Se precisar esperar, aguarda 3 segundos antes de retornar
        if flow_status == "esperar":
            await asyncio.sleep(3)
            # Verifica novamente após a espera
            flow_status = await check_message_flow(chat_id, message)
            print(f"Status do fluxo após espera: {flow_status}")
            response_data["flow_status"] = flow_status
        
        # Se status é 'prosseguir', processa as mensagens do buffer
        if flow_status == "prosseguir":
            last_message = await process_buffer_messages(chat_id)
            response_data["last_message"] = last_message.dict()
        
        return response_data
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
