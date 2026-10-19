from collections.abc import Iterator
from datetime import date
from typing import Protocol


class ModelUnavailable(Exception):
    """Nenhum destino da capacidade respondeu (o gateway já esgotou retry e fallback)."""

    def __init__(self, capability: str, reason: str):
        super().__init__(f"{capability}: {reason}")
        self.capability = capability
        self.reason = reason


class LanguageModel(Protocol):
    """Uma capacidade de linguagem pedida pelo nome lógico; o modelo físico é decisão do gateway.

    As duas operações levantam ModelUnavailable quando a capacidade não responde.
    """

    def complete(self, capability: str, task: str, content: str) -> str: ...

    def stream(self, capability: str, task: str, content: str) -> Iterator[str]: ...


class TicketSource(Protocol):
    """De onde vêm os tickets de um período; a leitura concreta é decisão do adapter."""

    def in_period(self, start: date, end: date) -> list[dict]: ...
