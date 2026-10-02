from abc import ABC, abstractmethod

class RetrievalAdapter(ABC):
    @abstractmethod
    def retrieve(self, query: str, jurisdiction: str) -> str:
        """Retrieve evidence based on query and jurisdiction."""
        pass
