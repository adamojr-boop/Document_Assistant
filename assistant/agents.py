import os
from openai import OpenAI

class TravelAgent:
    def __init__(self, db):
        self.db = db
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def query(self, user_query: str, n_results: int = 12):
        """Esegue la ricerca semantica su ChromaDB e genera la risposta con l'LLM."""
        collection = self.db.get_collection()
        
        # Recupero dei chunk
        results = collection.query(
            query_texts=[user_query],
            n_results=n_results
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

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2
        )

        answer = response.choices[0].message.content
        return answer, context