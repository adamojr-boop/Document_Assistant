import os
import shutil
import json
from datetime import datetime
from pathlib import Path
import chainlit as cl
from chainlit.action import Action

# Importiamo i moduli puliti dal pacchetto assistant
from assistant import Database, DocumentProcessor, TravelAgent

db = Database()
processor = DocumentProcessor(db)
travel_agent = TravelAgent(db)

# Percorso per il salvataggio dei log di feedback (diagnostica RAG)
FEEDBACK_LOG_FILE = Path("feedback_logs.json")

def log_feedback_to_disk(user_query: str, context: str, answer: str, rating: str):
    """Salva la telemetria del feedback su file JSON."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "rating": rating,
        "query": user_query,
        "context_retrieved": context,
        "assistant_answer": answer
    }
    logs = []
    if FEEDBACK_LOG_FILE.exists():
        try:
            with open(FEEDBACK_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    logs.append(log_entry)
    with open(FEEDBACK_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=4)


@cl.on_chat_start
async def start():
    """Inizializza la chat e sincronizza automaticamente i documenti all'avvio."""
    try:
        processor.sync_documents()
    except Exception as e:
        print(f"Errore di sincronizzazione iniziale: {e}")

    actions = [
        Action(name="db_stats", icon="bar-chart", label="Statistiche Database", value="db_stats", payload={}),
        Action(name="db_reindex", icon="refresh-cw", label="Reindex Database", value="db_reindex", payload={}),
        Action(name="db_clear", icon="trash-2", label="Svuota Database", value="db_clear", payload={}),
    ]
    
    await cl.Message(
        content="Benvenuto nel tuo **Travel Assistant** ✈️! Gestisci i documenti turistici regionali o chiedimi informazioni sulle mete. Puoi anche caricare nuovi file direttamente qui in chat!", 
        actions=actions,
        author="system_assistant"
    ).send()


@cl.action_callback("db_stats")
async def on_db_stats(action: Action):
    collection = db.get_collection()
    count = collection.count() if collection else 0
    await cl.Message(
        content=f"📊 **Statistiche Database:** Il database contiene attualmente `{count}` chunk indicizzati.",
        author="system_assistant"
    ).send()


@cl.action_callback("db_reindex")
async def on_db_reindex(action: Action):
    processor.sync_documents()
    await cl.Message(
        content="🔄 **Reindex completato:** Le cartelle regionali sono state sincronizzate con successo.",
        author="system_assistant"
    ).send()


@cl.action_callback("db_clear")
async def on_db_clear(action: Action):
    db.delete_collection()
    await cl.Message(
        content="🗑️ **Database svuotato:** L'intera collezione è stata eliminata.",
        author="system_assistant"
    ).send()


@cl.on_message
async def main(message: cl.Message):
    # 1. AGENTE DI SISTEMA: Gestione dei file allegati
    if message.elements:
        uploaded_files_count = 0
        for element in message.elements:
            if element.mime and element.path:
                dest_path = processor.ITALIA_DIR / element.name if hasattr(processor, "ITALIA_DIR") else Path("data/italia") / element.name
                shutil.copy(element.path, dest_path)
                uploaded_files_count += 1
        
        if uploaded_files_count > 0:
            processor.sync_documents()
            await cl.Message(
                content=f"📁 Ho ricevuto e caricato con successo `{uploaded_files_count}` nuovo/i file! Il database è stato aggiornato e indicizzato.",
                author="system_assistant"
            ).send()
            return

    # 2. TRAVEL ASSISTANT: Richiesta delegata all'agente dedicato
    msg = cl.Message(
        content="Sto cercando nei documenti di viaggio...",
        author="travel_assistant"
    )
    await msg.send()

    user_query = message.content
    
    # Eseguiamo la query tramite l'agente modulare
    answer, context = travel_agent.query(user_query)

    msg.content = answer
    msg.author = "travel_assistant"
    msg.metadata = {
        "user_query": user_query,
        "context": context,
        "answer": answer
    }

    # Pulsanti di feedback
    feedback_actions = [
        Action(name="feedback_up", icon="thumbs-up", label="Utile", value="up", payload={}),
        Action(name="feedback_down", icon="thumbs-down", label="Non utile", value="down", payload={})
    ]
    msg.actions = feedback_actions
    await msg.update()


@cl.action_callback("feedback_up")
async def on_feedback_up(action: Action):
    msg = action.for_message
    if msg and hasattr(msg, "metadata") and msg.metadata:
        log_feedback_to_disk(
            user_query=msg.metadata.get("user_query"),
            context=msg.metadata.get("context"),
            answer=msg.metadata.get("answer"),
            rating="up"
        )
    await cl.Message(content="👍 Grazie per il tuo feedback positivo! Traccia salvata.", author="system_assistant").send()


@cl.action_callback("feedback_down")
async def on_feedback_down(action: Action):
    msg = action.for_message
    if msg and hasattr(msg, "metadata") and msg.metadata:
        log_feedback_to_disk(
            user_query=msg.metadata.get("user_query"),
            context=msg.metadata.get("context"),
            answer=msg.metadata.get("answer"),
            rating="down"
        )
    await cl.Message(content="👎 Grazie per il feedback. Traccia registrata nei log.", author="system_assistant").send()