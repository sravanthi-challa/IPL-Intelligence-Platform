from typing import List, Dict, Any, Optional

class ContextBuilder:
    """
    Assembles, deduplicates, and formats retrieved document chunks
    and SQL analytics results into structured evidence blocks for the LLM.
    """

    @staticmethod
    def build_context(
        chunks: List[Dict[str, Any]],
        sql_data: Optional[Any] = None,
        max_context_chars: int = 4000
    ) -> Dict[str, Any]:
        """
        Deduplicates chunks and formats evidence text with explicit provenance markers.
        Returns:
            {
                "context_text": str,
                "sources": List[Dict[str, str]]
            }
        """
        seen_doc_ids = set()
        unique_chunks = []
        sources = []

        for c in chunks:
            doc_id = c.get("doc_id", c.get("chunk_id", "unknown"))
            if doc_id not in seen_doc_ids:
                seen_doc_ids.add(doc_id)
                unique_chunks.append(c)
                sources.append({
                    "doc_id": doc_id,
                    "title": c.get("title", "Untitled Document"),
                    "doc_type": c.get("doc_type", "general"),
                })

        context_parts = []

        # 1. Include SQL evidence if available
        if sql_data:
            context_parts.append("=== VERIFIED DATABASE SQL RESULTS ===")
            if isinstance(sql_data, list):
                for idx, row in enumerate(sql_data, 1):
                    row_str = ", ".join([f"{k}: {v}" for k, v in row.items()])
                    context_parts.append(f"Row {idx}: {row_str}")
            elif isinstance(sql_data, dict):
                for k, v in sql_data.items():
                    context_parts.append(f"{k}: {v}")
            else:
                context_parts.append(str(sql_data))
            context_parts.append("=====================================\n")

        # 2. Include Document chunks
        if unique_chunks:
            context_parts.append("=== RETRIEVED CRICKET EVIDENCE ===")
            current_chars = sum(len(p) for p in context_parts)
            for idx, c in enumerate(unique_chunks, 1):
                block = (
                    f"[Evidence Block {idx}]\n"
                    f"Document ID: {c.get('doc_id')}\n"
                    f"Title: {c.get('title')}\n"
                    f"Content:\n{c.get('content')}\n"
                )
                if current_chars + len(block) > max_context_chars:
                    break
                context_parts.append(block)
                current_chars += len(block)
            context_parts.append("===================================\n")

        context_text = "\n".join(context_parts)
        return {
            "context_text": context_text,
            "sources": sources,
            "chunks_used": len(unique_chunks)
        }
