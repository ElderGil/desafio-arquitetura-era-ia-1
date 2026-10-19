import json
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from fastapi import HTTPException

from .ports import LanguageModel, TicketSource
from .schemas import PeriodInput, Topic, TopicsReport


class TopicsReporter:
    """Relatório de temas de um período, em lotes que cabem na janela de contexto.

    Cada relatório roda até `parallel_batches` lotes ao mesmo tempo: o mês inteiro
    fica mais rápido sem disparar dezenas de chamadas simultâneas contra a cota do
    gateway. A soma segue a ordem dos lotes, então o resultado é o mesmo da execução
    em série.
    """

    def __init__(self, model: LanguageModel, capability: str, tickets: TicketSource, batch_size: int,
                 parallel_batches: int):
        self._model = model
        self._capability = capability
        self._tickets = tickets
        self._batch_size = batch_size
        self._parallel_batches = parallel_batches

    def validate(self, period: PeriodInput) -> None:
        if period.start > period.end:
            raise HTTPException(status_code=422, detail="A data inicial é posterior à data final")

    def topics(self, period: PeriodInput, on_progress: Callable[[int, int], None] = lambda done, total: None
               ) -> TopicsReport:
        self.validate(period)
        selected = self._tickets.in_period(period.start, period.end)
        batches = [selected[first:first + self._batch_size] for first in range(0, len(selected), self._batch_size)]
        on_progress(0, len(selected))

        def analyze(batch: list[dict]) -> list[dict]:
            content = "\n".join(f"[{t['id']}] {t['text']}" for t in batch)
            return json.loads(self._model.complete(self._capability, "topics", content))["topics"]

        with ThreadPoolExecutor(max_workers=self._parallel_batches, thread_name_prefix="topics-batch") as pool:
            futures = {pool.submit(analyze, batch): len(batch) for batch in batches}
            done_tickets, pending = 0, set(futures)
            try:
                while pending:
                    finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in finished:
                        future.result()   # propaga a falha do lote
                        done_tickets += futures[future]
                    on_progress(done_tickets, len(selected))
            except BaseException:
                # Desistir também é cancelar: lote que ainda não começou não chama o gateway.
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            results = [future.result() for future in futures]   # na ordem dos lotes

        totals: dict[str, dict] = {}
        for answer in results:
            for item in answer:
                current = totals.setdefault(item["topic"], {"count": 0, "examples": []})
                current["count"] += item["count"]
                current["examples"] = (current["examples"] + item["examples"])[:3]

        items = [Topic(topic=name, **data) for name, data in totals.items()]
        items.sort(key=lambda t: (-t.count, t.topic))
        return TopicsReport(start=period.start, end=period.end, total_tickets=len(selected), topics=items)
