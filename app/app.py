from dotenv import load_dotenv
import chainlit as cl

load_dotenv()

@cl.on_chat_start
async def start():
    await cl.Message(content="Benvenuto nel tuo Assistente di Viaggio RAG! 🌍 Come posso aiutarti oggi con le tue destinazioni?").send()

@cl.on_message
async def main(message: cl.Message):
    # Per ora rispondiamo in modo speculare per testare l'interfaccia
    await cl.Message(content=f"Ho ricevuto il tuo messaggio: {message.content}").send()