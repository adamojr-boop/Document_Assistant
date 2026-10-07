import os
import shutil
import chainlit as cl
from chainlit.action import Action
from openai import OpenAI
from assistant.database import Database
from assistant.document_processor import DocumentProcessor

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
        content="Benvenuto nel tuo **Travel Assistant** ✈️! Gestisci i documenti turistici regionali o chiedimi informazioni sulle mete.", 
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
    await msg.update()