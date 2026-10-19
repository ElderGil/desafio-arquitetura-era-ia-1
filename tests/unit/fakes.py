import threading
from collections.abc import Callable, Iterator


class FakeLanguageModel:
    """Implementa o port LanguageModel sem rede.

    Recebe respostas pré-definidas (devolvidas em ordem) ou uma função que responde
    a partir do conteúdo, para chamadas concorrentes. Registra cada chamada.
    """

    def __init__(self, *answers: str, respond: Callable[[str], str] | None = None, chunk_size: int = 4):
        self._answers = list(answers)
        self._respond = respond
        self._chunk_size = chunk_size
        self._lock = threading.Lock()
        self.calls: list[tuple[str, str, str]] = []

    def complete(self, capability: str, task: str, content: str) -> str:
        with self._lock:
            self.calls.append((capability, task, content))
            if self._respond:
                return self._respond(content)
            return self._answers.pop(0)

    def stream(self, capability: str, task: str, content: str) -> Iterator[str]:
        text = self.complete(capability, task, content)
        for start in range(0, len(text), self._chunk_size):
            yield text[start:start + self._chunk_size]


class FakeTicketSource:
    """Implementa o port TicketSource com uma lista em memória."""

    def __init__(self, tickets: list[dict]):
        self._tickets = tickets
        self.calls: list[tuple] = []

    def in_period(self, start, end) -> list[dict]:
        self.calls.append((start, end))
        return self._tickets
