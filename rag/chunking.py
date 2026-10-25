from typing import List, Dict, Any
from abc import ABC, abstractmethod

class BaseChunker(ABC):
    @abstractmethod
    def chunk_document(self, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        pass

class SemanticDocumentChunker(BaseChunker):
    """
    Chunks documents along natural paragraph/section boundaries while
    preserving critical entity headers (Title, Match ID, Teams, Player Name)
    in every child chunk to prevent loss of semantic context.
    """
    def __init__(self, max_chunk_words: int = 350):
        self.max_chunk_words = max_chunk_words

    def chunk_document(self, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        doc_id = doc["doc_id"]
        doc_type = doc.get("doc_type", "general")
        title = doc.get("title", "")
        content = doc.get("content", "")
        metadata = doc.get("metadata", {})

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        total_words = len(content.split())

        # If document is concise enough, preserve it as a single high-coherence chunk
        if total_words <= self.max_chunk_words or len(paragraphs) <= 1:
            return [{
                "chunk_id": f"{doc_id}_c0",
                "doc_id": doc_id,
                "doc_type": doc_type,
                "chunk_index": 0,
                "title": title,
                "content": content,
                "metadata": metadata,
                "word_count": total_words
            }]

        chunks = []
        current_paras = []
        current_word_count = 0
        chunk_idx = 0

        header_prefix = f"[{title}]\n"

        for p in paragraphs:
            p_words = len(p.split())
            if current_word_count + p_words > self.max_chunk_words and current_paras:
                chunk_body = header_prefix + "\n\n".join(current_paras)
                chunks.append({
                    "chunk_id": f"{doc_id}_c{chunk_idx}",
                    "doc_id": doc_id,
                    "doc_type": doc_type,
                    "chunk_index": chunk_idx,
                    "title": title,
                    "content": chunk_body,
                    "metadata": metadata,
                    "word_count": len(chunk_body.split())
                })
                chunk_idx += 1
                current_paras = [p]
                current_word_count = p_words
            else:
                current_paras.append(p)
                current_word_count += p_words

        if current_paras:
            chunk_body = header_prefix + "\n\n".join(current_paras)
            chunks.append({
                "chunk_id": f"{doc_id}_c{chunk_idx}",
                "doc_id": doc_id,
                "doc_type": doc_type,
                "chunk_index": chunk_idx,
                "title": title,
                "content": chunk_body,
                "metadata": metadata,
                "word_count": len(chunk_body.split())
            })

        return chunks

class SlidingWindowChunker(BaseChunker):
    """
    Fixed-window chunking with token/word overlap for arbitrary length prose.
    """
    def __init__(self, window_size: int = 150, overlap: int = 30):
        self.window_size = window_size
        self.overlap = overlap

    def chunk_document(self, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        doc_id = doc["doc_id"]
        doc_type = doc.get("doc_type", "general")
        title = doc.get("title", "")
        content = doc.get("content", "")
        metadata = doc.get("metadata", {})

        words = content.split()
        if len(words) <= self.window_size:
            return [{
                "chunk_id": f"{doc_id}_w0",
                "doc_id": doc_id,
                "doc_type": doc_type,
                "chunk_index": 0,
                "title": title,
                "content": content,
                "metadata": metadata,
                "word_count": len(words)
            }]

        chunks = []
        chunk_idx = 0
        start = 0
        step = self.window_size - self.overlap

        while start < len(words):
            end = min(start + self.window_size, len(words))
            chunk_words = words[start:end]
            chunk_text = f"[{title}] " + " ".join(chunk_words)

            chunks.append({
                "chunk_id": f"{doc_id}_w{chunk_idx}",
                "doc_id": doc_id,
                "doc_type": doc_type,
                "chunk_index": chunk_idx,
                "title": title,
                "content": chunk_text,
                "metadata": metadata,
                "word_count": len(chunk_words)
            })
            chunk_idx += 1
            if end == len(words):
                break
            start += step

        return chunks
