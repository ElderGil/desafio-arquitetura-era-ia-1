"""Caracterização (Feathers) das quatro features.

Fixa o que a v1 entregava: status e corpo completo de cada resposta, inclusive os
erros de entrada (golden master em golden/, gravado na v1-coupled). Nas tags
v1-coupled e v2-decoupled esta suíte era idêntica. Na main, F2 passou a entregar
em streaming (SSE) e F3 de forma assíncrona (202 + status + 303): os testes dessas
duas consomem o contrato novo e comparam o conteúdo final com o mesmo golden da v1.
"""

import json
import time
from pathlib import Path

import httpx
import pytest

TICKETS_FILE = Path(__file__).resolve().parents[2] / "data" / "tickets.jsonl"

# Cobrem as 5 categorias, as 3 prioridades e as bordas da extração: nota fiscal
# antes do pedido, pedido sem "#", ticket sem pedido e ticket com produto.
TICKET_IDS = [
    "TK-00002",  # product_defect/medium, nota fiscal 530720 antes do pedido #605065
    "TK-00007",  # delivery/medium, sem pedido, com produto
    "TK-00009",  # delivery/high, sem pedido
    "TK-00011",  # other/high
    "TK-00012",  # other/low, sem pedido
    "TK-00015",  # exchange_return/medium, nota fiscal e "pedido 972600" sem "#"
    "TK-00016",  # delivery/low
    "TK-00023",  # payment/high
    "TK-00024",  # payment/low
    "TK-00030",  # product_defect/low, pedido e produto
    "TK-00035",  # product_defect/high
    "TK-00039",  # exchange_return/high, sem pedido
    "TK-00065",  # exchange_return/medium, com produto
    "TK-00088",  # delivery/high, pedido, produto e nota fiscal
]

# A sugestão leva cerca de 16 s por chamada: dois tickets bastam para fixar o formato.
SUGGESTION_IDS = ["TK-00002", "TK-00023"]

README_EXAMPLE = {"ticket_id": "TK-00042", "text": "Meu pedido #481516 não chegou e já passou do prazo, urgente"}


def _load_tickets() -> dict[str, dict]:
    wanted = set(TICKET_IDS)
    found = {}
    with open(TICKETS_FILE, encoding="utf-8") as file:
        for line in file:
            ticket = json.loads(line)
            if ticket["id"] in wanted:
                found[ticket["id"]] = {"ticket_id": ticket["id"], "text": ticket["text"]}
    return found


TICKETS = _load_tickets()


# F1 Classificar ticket

@pytest.mark.parametrize("ticket_id", TICKET_IDS)
def test_classification(helpdesk, golden, ticket_id):
    response = helpdesk.post("/tickets/classification", json=TICKETS[ticket_id])
    golden(f"classification/{ticket_id}", response)


def test_classification_readme_example(helpdesk, golden):
    response = helpdesk.post("/tickets/classification", json=README_EXAMPLE)
    golden("classification/readme-example", response)


def test_classification_rejects_empty_text(helpdesk, golden):
    response = helpdesk.post("/tickets/classification", json={"ticket_id": "TK-00001", "text": ""})
    golden("classification/error-empty-text", response)


# F2 Sugerir resposta

def read_sse(helpdesk, payload: dict) -> tuple[httpx.Response, list[tuple[str, dict]]]:
    """Consome o stream da F2 e devolve a resposta e os eventos (nome, dados) na ordem."""
    events, name = [], "message"
    with helpdesk.stream("POST", "/tickets/reply-suggestion", json=payload) as response:
        for line in response.iter_lines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((name, json.loads(line.removeprefix("data: "))))
                name = "message"
    return response, events


@pytest.mark.parametrize("ticket_id", SUGGESTION_IDS)
def test_reply_suggestion(helpdesk, golden_body, ticket_id):
    response, events = read_sse(helpdesk, TICKETS[ticket_id])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert events[-1] == ("end", {"ticket_id": ticket_id})
    text = "".join(data["chunk"] for name, data in events[:-1])
    assert {"ticket_id": ticket_id, "suggestion": text} == golden_body(f"reply-suggestion/{ticket_id}")


def test_reply_suggestion_rejects_missing_ticket_id(helpdesk, golden):
    response = helpdesk.post("/tickets/reply-suggestion", json={"text": "Meu pedido não chegou"})
    golden("reply-suggestion/error-missing-ticket-id", response)


# F3 Relatório de temas
# Dois dias (274 tickets, 2 lotes) exercitam a soma de temas entre lotes; o mês
# inteiro fica na suíte de aceite (tests/acceptance).

def run_report(helpdesk, period: dict) -> dict:
    """Pede o relatório (202), acompanha o status até o 303 e devolve o resultado."""
    accepted = helpdesk.post("/reports/topics", json=period)
    assert accepted.status_code == 202
    assert int(accepted.headers["retry-after"]) > 0
    status_url = accepted.headers["location"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status = helpdesk.get(status_url, follow_redirects=False)
        if status.status_code == 303:
            result = helpdesk.get(status.headers["location"])
            assert result.status_code == 200
            return result.json()
        assert status.status_code == 200
        assert status.json()["state"] in ("pending", "running"), status.json()
        time.sleep(1)
    pytest.fail("relatório não terminou em 120 s")


def test_topics_two_days(helpdesk, golden_body):
    report = run_report(helpdesk, {"start": "2026-08-01", "end": "2026-08-02"})
    assert report == golden_body("topics/2026-08-01_2026-08-02")


def test_topics_period_without_tickets(helpdesk, golden_body):
    report = run_report(helpdesk, {"start": "2026-09-01", "end": "2026-09-30"})
    assert report == golden_body("topics/period-without-tickets")


def test_topics_rejects_inverted_period(helpdesk, golden):
    response = helpdesk.post("/reports/topics", json={"start": "2026-08-31", "end": "2026-08-01"})
    golden("topics/error-inverted-period", response)


def test_topics_rejects_invalid_date(helpdesk, golden):
    response = helpdesk.post("/reports/topics", json={"start": "2026-08-32", "end": "2026-08-31"})
    golden("topics/error-invalid-date", response)


# F4 Extrair dados do pedido

@pytest.mark.parametrize("ticket_id", TICKET_IDS)
def test_extraction(helpdesk, golden, ticket_id):
    response = helpdesk.post("/tickets/extraction", json=TICKETS[ticket_id])
    golden(f"extraction/{ticket_id}", response)


def test_extraction_readme_example(helpdesk, golden):
    response = helpdesk.post("/tickets/extraction", json=README_EXAMPLE)
    golden("extraction/readme-example", response)


def test_extraction_rejects_empty_text(helpdesk, golden):
    response = helpdesk.post("/tickets/extraction", json={"ticket_id": "TK-00001", "text": ""})
    golden("extraction/error-empty-text", response)
