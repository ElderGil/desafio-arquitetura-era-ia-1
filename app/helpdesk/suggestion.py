from .ports import LanguageModel
from .schemas import ReplySuggestion, TicketInput


class ReplySuggester:
    def __init__(self, model: LanguageModel, capability: str):
        self._model = model
        self._capability = capability

    def suggest(self, ticket: TicketInput) -> ReplySuggestion:
        text = self._model.complete(self._capability, "suggest", ticket.text)
        return ReplySuggestion(ticket_id=ticket.ticket_id, suggestion=text)
