import json

from fastapi import HTTPException

from .ports import LanguageModel
from .schemas import Classification, TicketInput

CATEGORIES = {"delivery", "payment", "exchange_return", "product_defect", "other"}
PRIORITIES = {"low", "medium", "high"}


class Classifier:
    def __init__(self, model: LanguageModel, capability: str):
        self._model = model
        self._capability = capability

    def classify(self, ticket: TicketInput) -> Classification:
        text = self._model.complete(self._capability, "classify", ticket.text)
        data = json.loads(text)
        if data.get("category") not in CATEGORIES or data.get("priority") not in PRIORITIES:
            raise HTTPException(status_code=502, detail="Classificação fora dos valores permitidos")
        return Classification(ticket_id=ticket.ticket_id, **data)
