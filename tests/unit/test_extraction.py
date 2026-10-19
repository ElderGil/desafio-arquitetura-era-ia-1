import pytest
from fastapi import HTTPException

from helpdesk.extraction import OrderExtractor
from helpdesk.schemas import TicketInput

from fakes import FakeLanguageModel

TICKET = TicketInput(ticket_id="T-2", text="Pedido #123456, tênis")


def test_extrai_pedido_e_produto_pela_capacidade_configurada():
    model = FakeLanguageModel('{"order_number": "#123456", "product": "tênis"}')

    result = OrderExtractor(model, "cap-extrair").extract(TICKET)

    assert (result.ticket_id, result.order_number, result.product) == ("T-2", "#123456", "tênis")
    assert model.calls == [("cap-extrair", "extract", "Pedido #123456, tênis")]


def test_sem_pedido_e_produto_devolve_nulos():
    result = OrderExtractor(FakeLanguageModel('{"order_number": null}'), "cap").extract(TICKET)

    assert result.order_number is None
    assert result.product is None


@pytest.mark.parametrize("order_number", ["123456", "#12345", "#1234567", "#12345a"])
def test_numero_de_pedido_em_formato_invalido_vira_502(order_number):
    model = FakeLanguageModel('{"order_number": "%s", "product": "x"}' % order_number)

    with pytest.raises(HTTPException) as error:
        OrderExtractor(model, "cap").extract(TICKET)

    assert error.value.status_code == 502
    assert error.value.detail == "Número de pedido em formato inválido"
