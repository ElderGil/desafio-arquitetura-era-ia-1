from typing import Protocol


class LanguageModel(Protocol):
    """Uma capacidade de linguagem pedida pelo nome lógico; o modelo físico é decisão do gateway."""

    def complete(self, capability: str, task: str, content: str) -> str: ...
