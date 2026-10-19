class FakeLanguageModel:
    """Implementa o port LanguageModel sem rede: devolve respostas pré-definidas, em ordem."""

    def __init__(self, *answers: str):
        self._answers = list(answers)
        self.calls: list[tuple[str, str, str]] = []

    def complete(self, capability: str, task: str, content: str) -> str:
        self.calls.append((capability, task, content))
        return self._answers.pop(0)


class FakeTicketSource:
    """Implementa o port TicketSource com uma lista em memória."""

    def __init__(self, tickets: list[dict]):
        self._tickets = tickets
        self.calls: list[tuple] = []

    def in_period(self, start, end) -> list[dict]:
        self.calls.append((start, end))
        return self._tickets
