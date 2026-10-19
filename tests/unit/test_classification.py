import pytest
from fastapi import HTTPException

from helpdesk.classification import Classifier
from helpdesk.schemas import TicketInput

from fakes import FakeLanguageModel

TICKET = TicketInput(ticket_id="T-1", text="Meu pedido não chegou")


def test_classifica_pedindo_a_capacidade_configurada():
    model = FakeLanguageModel('{"category": "delivery", "priority": "high"}')

    result = Classifier(model, "cap-classificar").classify(TICKET)

    assert (result.ticket_id, result.category, result.priority) == ("T-1", "delivery", "high")
    assert model.calls == [("cap-classificar", "classify", "Meu pedido não chegou")]


@pytest.mark.parametrize("answer", [
    '{"category": "spam", "priority": "high"}',
    '{"category": "delivery", "priority": "urgent"}',
    '{}',
])
def test_valor_fora_do_permitido_vira_502(answer):
    with pytest.raises(HTTPException) as error:
        Classifier(FakeLanguageModel(answer), "cap").classify(TICKET)

    assert error.value.status_code == 502
    assert error.value.detail == "Classificação fora dos valores permitidos"
