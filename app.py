import os
import shutil
from pathlib import Path
import chainlit as cl
from chainlit.action import Action
from openai import OpenAI
from assistant.database import Database
from assistant.document_processor import DocumentProcessor, ITALIA_DIR

db = Database()
processor = DocumentProcessor(db)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@cl.on_chat_start
async def start():
    """Inizializza la chat e sincronizza automaticamente i documenti all'avvio."""
    try:
        processor.sync_documents()
    except Exception as e:
        print(f"Errore di sincronizzazione iniziale: {e}")

    actions = [
        Action(
            name="db_stats",
            icon="bar-chart",
            label="Statistiche Database",
            value="db_stats",
            payload={}
        ),
        Action(
            name="db_reindex",
            icon="refresh-cw",
            label="Reindex Database",
            value="db_reindex",
            payload={}
        ),
        Action(
            name="db_clear",
            icon="trash-2",
            label="Svuota Database",
            value="db_clear",
            payload={}
        ),
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
    # 1. Gestione dei file allegati direttamente dall'interfaccia di Chainlit
    if message.elements:
        uploaded_files_count = 0
        for element in message.elements:
            if element.mime and element.path:
                dest_path = ITALIA_DIR / element.name
                shutil.copy(element.path, dest_path)
                uploaded_files_count += 1
        
        if uploaded_files_count > 0:
            processor.sync_documents()
            await cl.Message(
                content=f"📁 Ho ricevuto e caricato con successo `{uploaded_files_count}` nuovo/i file! Il database è stato aggiornato e indicizzato.",
                author="system_assistant"
            ).send()
            return

    # 2. Gestione della normale richiesta RAG
    msg = cl.Message(
        content="Sto cercando nei documenti di viaggio...",
        author="travel_assistant"
    )
    await msg.send()

    user_query = message.content
    collection = db.get_collection()

    # Eseguiamo la ricerca semantica su ChromaDB con i 12 chunk
    results = collection.query(
        query_texts=[user_query],
        n_results=12
    )
    retrieved_chunks = results.get("documents", [[]])[0]
    context = "\n\n".join(retrieved_chunks) if retrieved_chunks else "Nessun documento rilevante trovato."

    system_instruction = """Sei il mio Travel Assistant, un assistente turistico esperto, cordiale e preciso.
Il tuo compito è rispondere alle mie domande basandoti ESCLUSIVAMENTE sulle informazioni presenti nel Contesto fornito, estratto dai documenti nel database o caricati in app.

REGOLE TASSATIVE:
1. Usa solo ed esclusivamente le informazioni contenute nel Contesto sottostante per formulare la risposta.
2. Non inventare o aggiungere informazioni esterne o dettagli non menzionati nel contesto.
3. Se la risposta non è presente nel contesto fornito, di' onestamente che la guida non riporta questa informazione, senza attingere alla tua conoscenza generale.
"""

    user_prompt = f"""Contesto dai documenti turistici:
{context}

Domanda dell'utente: {user_query}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )

    answer = response.choices[0].message.content
    msg.content = answer
    msg.author = "travel_assistant"

    # 3. Aggiungiamo i pulsanti di feedback (👍 / 👎) sotto la risposta
    feedback_actions = [
        Action(name="feedback_up", icon="thumbs-up", label="Utile", value="up", payload={}),
        Action(name="feedback_down", icon="thumbs-down", label="Non utile", value="down", payload={})
    ]
    msg.actions = feedback_actions
    await msg.update()

@cl.action_callback("feedback_up")
async def on_feedback_up(action: Action):
    await cl.Message(content="👍 Grazie per il tuo feedback positivo!", author="system_assistant").send()

@cl.action_callback("feedback_down")
async def on_feedback_down(action: Action):
    await cl.Message(content="👎 Grazie per il feedback. Faremo tesoro della segnalazione per migliorare le risposte.", author="system_assistant").send()