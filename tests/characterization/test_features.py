"""Caracterização (Feathers) das quatro features como a v1 as entrega.

Fixa o que o sistema faz hoje, não o que ele deveria fazer: status e corpo
completo de cada resposta, inclusive os erros de entrada. A suíte é a mesma nas
tags v1-coupled e v2-decoupled.
"""

import json
from pathlib import Path

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

@pytest.mark.parametrize("ticket_id", SUGGESTION_IDS)
def test_reply_suggestion(helpdesk, golden, ticket_id):
    response = helpdesk.post("/tickets/reply-suggestion", json=TICKETS[ticket_id])
    golden(f"reply-suggestion/{ticket_id}", response)


def test_reply_suggestion_rejects_missing_ticket_id(helpdesk, golden):
    response = helpdesk.post("/tickets/reply-suggestion", json={"text": "Meu pedido não chegou"})
    golden("reply-suggestion/error-missing-ticket-id", response)


# F3 Relatório de temas
# O mês inteiro leva cerca de 6 min e a borda corta em 30 s. Dois dias (274 tickets,
# 2 lotes) cabem e ainda exercitam a soma de temas entre lotes.

def test_topics_two_days(helpdesk, golden):
    response = helpdesk.post("/reports/topics", json={"start": "2026-08-01", "end": "2026-08-02"})
    golden("topics/2026-08-01_2026-08-02", response)


def test_topics_period_without_tickets(helpdesk, golden):
    response = helpdesk.post("/reports/topics", json={"start": "2026-09-01", "end": "2026-09-30"})
    golden("topics/period-without-tickets", response)


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
