from .base_adapter import RetrievalAdapter

class FssaiRetrievalAdapter(RetrievalAdapter):
    def retrieve(self, query: str, jurisdiction: str) -> str:
        # Placeholder for Legacy PDF Fetcher logic
        return f"[FSSAI] Normalized evidence for '{query}' in jurisdiction '{jurisdiction}'."
