from helpdesk.schemas import TicketInput
from helpdesk.suggestion import ReplySuggester

from fakes import FakeLanguageModel


def test_entrega_a_sugestao_em_trechos_que_somam_o_texto_do_modelo():
    model = FakeLanguageModel("Olá, vamos resolver.", chunk_size=5)

    chunks = list(ReplySuggester(model, "cap-responder").stream(TicketInput(ticket_id="T-3", text="Ajuda")))

    assert chunks == ["Olá, ", "vamos", " reso", "lver."]
    assert model.calls == [("cap-responder", "suggest", "Ajuda")]
