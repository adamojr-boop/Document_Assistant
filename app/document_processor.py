import os
import hashlib
from pathlib import Path
from markitdown import MarkItDown

# Percorso fisso e pulito: punta direttamente a app/data/italia
CURRENT_DIR = Path(__file__).resolve().parent
ITALIA_DIR = CURRENT_DIR / "data" / "italia"

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

    @staticmethod
    def get_document_metadata(file_path: str, file_hash: str) -> dict:
        """Estrae i metadati di base per il singolo documento."""
        return {
            "source": os.path.basename(file_path),
            "file_hash": file_hash
        }

    def sync_documents(self):
        """Sincronizza la cartella app/data/italia/ con ChromaDB."""
        print(f"\n[DEBUG] Controllo cartella italia in corso...")
        print(f"[DEBUG] Percorso assoluto cercato: {ITALIA_DIR.resolve()}")
        
        if not ITALIA_DIR.exists():
            print(f"[DEBUG] La cartella non esiste. La creo adesso...")
            ITALIA_DIR.mkdir(parents=True, exist_ok=True)
            print(f"[DEBUG] Cartella creata. Inserisci i file .txt al suo interno.")
            return

        supported_extensions = {".txt", ".pdf", ".docx", ".pptx", ".xlsx"}
        
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
            
            if file_path.suffix.lower() == ".txt":
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                result = self.md_converter.convert(str(file_path))
                content = result.text_content

            # Chunking semplice ed efficiente
            chunk_size = 1000
            chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
            print(f"[DEBUG] File '{filename}' suddiviso in {len(chunks)} chunk.")

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
                print(f"[DEBUG] Salvati con successo {len(documents)} chunk per il file '{filename}'.\n")