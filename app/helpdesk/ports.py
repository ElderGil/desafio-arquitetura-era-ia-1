from datetime import date
from typing import Protocol


class LanguageModel(Protocol):
    """Uma capacidade de linguagem pedida pelo nome lógico; o modelo físico é decisão do gateway."""

    def complete(self, capability: str, task: str, content: str) -> str: ...


class TicketSource(Protocol):
    """De onde vêm os tickets de um período; a leitura concreta é decisão do adapter."""

    def in_period(self, start: date, end: date) -> list[dict]: ...
