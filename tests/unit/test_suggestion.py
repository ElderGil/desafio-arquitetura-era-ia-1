from helpdesk.schemas import TicketInput
from helpdesk.suggestion import ReplySuggester

from fakes import FakeLanguageModel


def test_devolve_o_texto_do_modelo_como_sugestao():
    model = FakeLanguageModel("Olá, vamos resolver.")

    result = ReplySuggester(model, "cap-responder").suggest(TicketInput(ticket_id="T-3", text="Ajuda"))

    assert (result.ticket_id, result.suggestion) == ("T-3", "Olá, vamos resolver.")
    assert model.calls == [("cap-responder", "suggest", "Ajuda")]
