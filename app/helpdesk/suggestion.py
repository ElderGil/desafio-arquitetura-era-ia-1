from . import config
from .ports import LanguageModel
from .schemas import ReplySuggestion, TicketInput


def suggest(ticket: TicketInput, model: LanguageModel) -> ReplySuggestion:
    text = model.complete(config.SUGGESTION_CAPABILITY, "suggest", ticket.text)
    return ReplySuggestion(ticket_id=ticket.ticket_id, suggestion=text)
