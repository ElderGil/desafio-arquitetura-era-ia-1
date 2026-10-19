from collections.abc import Iterator

from .ports import LanguageModel
from .schemas import TicketInput


class ReplySuggester:
    def __init__(self, model: LanguageModel, capability: str):
        self._model = model
        self._capability = capability

    def stream(self, ticket: TicketInput) -> Iterator[str]:
        """Trechos da sugestão à medida que o modelo gera; o atendente lê enquanto chega."""
        return self._model.stream(self._capability, "suggest", ticket.text)
