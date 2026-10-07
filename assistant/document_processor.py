import os
import hashlib
import re
import numpy as np
from pathlib import Path
from openai import OpenAI
from markitdown import MarkItDown

CURRENT_DIR = Path(__file__).resolve().parent
ITALIA_DIR = CURRENT_DIR.parent / "data" / "italia"

def calculate_file_hash(file_path: Path) -> str:
    """Calcola l'hash SHA-256 del contenuto del file per tracciarne le modifiche."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

class DocumentProcessor:
    def __init__(self, db):
        self.collection = db.get_collection()
        self.md_converter = MarkItDown()
        # Inizializziamo il client OpenAI per generare gli embeddings semantici
        self.openai_client = OpenAI()

    @staticmethod
    def get_document_metadata(file_path: str, file_hash: str) -> dict:
        """Estrae i metadati di base per il singolo documento."""
        return {
            "source": os.path.basename(file_path),
            "file_hash": file_hash
        }

    def semantic_chunk_text(self, text: str, threshold_percentile=85, max_chunk_size=1200) -> list[str]:
        """Divide il testo in chunk basandosi sulla distanza semantica tra le frasi."""
        # 1. Pulizia e suddivisione in frasi
        clean_text = text.replace("\n", " ")
        sentences = re.split(r'(?<=[.!?])\s+', clean_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return [text] if text.strip() else []
            
        if len(sentences) == 1:
            return sentences

        try:
            # 2. Generazione degli embeddings per ogni frase tramite OpenAI
            response = self.openai_client.embeddings.create(
                input=sentences,
                model="text-embedding-3-small"
            )
            embeddings = [item.embedding for item in response.data]
            
            # 3. Calcolo della distanza di coseno tra frasi adiacenti
            def cosine_similarity(a, b):
                return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
                
            distances = []
            for i in range(len(embeddings) - 1):
                sim = cosine_similarity(embeddings[i], embeddings[i+1])
                distances.append(1.0 - sim) # Distanza = 1 - similarità
                
            if not distances:
                return [text]
                
            # 4. Soglia dinamica basata sul percentile delle distanze
            threshold = np.percentile(distances, threshold_percentile)
            
            chunks = []
            current_chunk = [sentences[0]]
            current_length = len(sentences[0])
            
            for i, dist in enumerate(distances):
                next_sentence = sentences[i+1]
                # Spezziamo se la distanza supera la soglia o se superiamo la dimensione massima del chunk
                if dist > threshold or (current_length + len(next_sentence) > max_chunk_size):
                    chunks.append(" ".join(current_chunk))
                    current_chunk = [next_sentence]
                    current_length = len(next_sentence)
                else:
                    current_chunk.append(next_sentence)
                    current_length += len(next_sentence) + 1
                    
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                
            return chunks
            
        except Exception as e:
            print(f"[WARNING] Errore nel chunking semantico ({e}), fallback al chunking a dimensione fissa.")
            chunk_size = 1000
            return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

    def sync_documents(self):
        """Sincronizza la cartella data/italia/ con ChromaDB usando il chunking semantico."""
        print(f"\n[DEBUG] Controllo cartella italia in corso...")
        print(f"[DEBUG] Percorso assoluto cercato: {ITALIA_DIR.resolve()}")
        
        if not ITALIA_DIR.exists():
            print(f"[DEBUG] La cartella non esiste. La creo adesso...")
            ITALIA_DIR.mkdir(parents=True, exist_ok=True)
            return

        supported_extensions = {".txt", ".pdf", ".docx", ".pptx", ".xlsx", ""}
        
        local_files = {
            f.name: f for f in ITALIA_DIR.iterdir() 
            if f.is_file() and f.suffix.lower() in supported_extensions
        }
        print(f"[DEBUG] File compatibili trovati nella cartella: {list(local_files.keys())}")
        
        local_file_names = set(local_files.keys())

        existing_data = self.collection.get(include=["metadatas"])
        existing_metadatas = existing_data.get("metadatas", [])
        existing_ids = existing_data.get("ids", [])

        db_files_info = {}
        file_to_chunk_ids = {}

        for chunk_id, meta in zip(existing_ids, existing_metadatas):
            if meta and "source" in meta:
                source = meta["source"]
                file_hash = meta.get("file_hash", "")
                db_files_info[source] = file_hash
                file_to_chunk_ids.setdefault(source, []).append(chunk_id)

        db_file_names = set(db_files_info.keys())

        added_files = local_file_names - db_file_names
        removed_files = db_file_names - local_file_names
        
        common_files = local_file_names.intersection(db_file_names)
        updated_files = set()
        for filename in common_files:
            file_path = local_files[filename]
            current_hash = calculate_file_hash(file_path)
            if current_hash != db_files_info.get(filename):
                updated_files.add(filename)

        files_to_remove = removed_files.union(updated_files)
        for filename in files_to_remove:
            ids_to_delete = file_to_chunk_ids.get(filename, [])
            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)

        files_to_add = added_files.union(updated_files)
        for filename in files_to_add:
            file_path = local_files[filename]
            current_hash = calculate_file_hash(file_path)
            
            if file_path.suffix.lower() == ".txt" or file_path.suffix == "":
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                result = self.md_converter.convert(str(file_path))
                content = result.text_content

            # Applicazione del chunking semantico intelligente
            print(f"[DEBUG] Analisi semantica e chunking per il file '{filename}'...")
            chunks = self.semantic_chunk_text(content)
            print(f"[DEBUG] File '{filename}' suddiviso in {len(chunks)} chunk semantici.")

            documents = []
            ids = []
            metadatas = []

            for idx, chunk in enumerate(chunks):
                if chunk and not chunk.isspace():
                    chunk_id = f"{filename}_chunk_{idx}"
                    documents.append(chunk)
                    ids.append(chunk_id)
                    metadatas.append(self.get_document_metadata(str(file_path), current_hash))

            if documents:
                self.collection.add(
                    documents=documents,
                    ids=ids,
                    metadatas=metadatas
                )
                print(f"[DEBUG] Salvati con successo {len(documents)} chunk semantici per il file '{filename}'.\n")