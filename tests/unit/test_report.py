import json
from datetime import date

import pytest
from fastapi import HTTPException

from helpdesk.report import TopicsReporter
from helpdesk.schemas import PeriodInput

from fakes import FakeLanguageModel, FakeTicketSource

PERIOD = PeriodInput(start=date(2026, 3, 1), end=date(2026, 3, 31))


def tickets(n: int) -> list[dict]:
    return [{"id": f"T-{i}", "text": f"texto {i}", "created_at": "2026-03-10T10:00:00"} for i in range(n)]


def answer(*topics: tuple[str, int, list[str]]) -> str:
    return json.dumps({"topics": [{"topic": t, "count": c, "examples": e} for t, c, e in topics]})


def test_caminho_feliz_ordena_por_contagem_e_depois_por_nome():
    model = FakeLanguageModel(answer(("b", 2, ["x"]), ("a", 2, ["y"]), ("c", 5, ["z"])))
    source = FakeTicketSource(tickets(3))

    report = TopicsReporter(model, "cap-temas", source, batch_size=150).topics(PERIOD)

    assert [(t.topic, t.count) for t in report.topics] == [("c", 5), ("a", 2), ("b", 2)]
    assert (report.start, report.end, report.total_tickets) == (PERIOD.start, PERIOD.end, 3)
    assert source.calls == [(PERIOD.start, PERIOD.end)]
    capability, task, content = model.calls[0]
    assert (capability, task) == ("cap-temas", "topics")
    assert content == "[T-0] texto 0\n[T-1] texto 1\n[T-2] texto 2"


def test_periodo_invertido_vira_422_sem_ler_tickets_nem_chamar_o_modelo():
    model = FakeLanguageModel()
    source = FakeTicketSource(tickets(3))
    inverted = PeriodInput(start=date(2026, 3, 31), end=date(2026, 3, 1))

    with pytest.raises(HTTPException) as error:
        TopicsReporter(model, "cap", source, batch_size=150).topics(inverted)

    assert error.value.status_code == 422
    assert error.value.detail == "A data inicial é posterior à data final"
    assert model.calls == []
    assert source.calls == []


def test_processa_em_lotes_em_serie_e_soma_temas_entre_lotes():
    model = FakeLanguageModel(
        answer(("entrega", 2, ["a", "b"])),
        answer(("entrega", 3, ["c"]), ("pagamento", 1, ["d"])),
        answer(("entrega", 1, ["e"])),
    )

    report = TopicsReporter(model, "cap", FakeTicketSource(tickets(5)), batch_size=2).topics(PERIOD)

    assert [len(call[2].split("\n")) for call in model.calls] == [2, 2, 1]
    assert [(t.topic, t.count) for t in report.topics] == [("entrega", 6), ("pagamento", 1)]
    assert report.total_tickets == 5


def test_exemplos_sao_cortados_em_tres():
    model = FakeLanguageModel(
        answer(("entrega", 2, ["a", "b"])),
        answer(("entrega", 2, ["c", "d"])),
    )

    report = TopicsReporter(model, "cap", FakeTicketSource(tickets(4)), batch_size=2).topics(PERIOD)

    assert report.topics[0].examples == ["a", "b", "c"]


def test_sem_tickets_nao_chama_o_modelo():
    model = FakeLanguageModel()

    report = TopicsReporter(model, "cap", FakeTicketSource([]), batch_size=2).topics(PERIOD)

    assert (report.total_tickets, report.topics) == (0, [])
    assert model.calls == []
