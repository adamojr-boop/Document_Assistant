import os
import chromadb
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DB_DIR = CURRENT_DIR / "chroma_db"

class Database:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(DB_DIR))
        self.collection_name = "travel_documents"
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def get_collection(self):
        return self.collection

    def delete_collection(self):
        try:
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.get_or_create_collection(name=self.collection_name)
        except Exception:
            pass