"""Critérios de aceite da main, provocados pelo provider simulado e conferidos no /admin/calls.

Cada teste prepara um modo de falha, chama a feature pela borda (localhost:8000)
e confere a resposta e o caminho que a chamada fez. É o mesmo roteiro que o
avaliador segue; os números (tentativas, tempos) são os declarados no README e
nos ADRs.

    uv run pytest tests/acceptance -v      (com a pilha no ar; cerca de 4 minutos)
"""

import json
import os
import time

import httpx
import pytest

HELPDESK_URL = os.environ.get("HELPDESK_URL", "http://localhost:8000")
PROVIDER_URL = os.environ.get("PROVIDER_URL", "http://localhost:8090")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:4000")

TICKET = {"ticket_id": "TK-00042", "text": "Meu pedido #481516 não chegou e já passou do prazo, urgente"}
MONTH = {"start": "2026-08-01", "end": "2026-08-31"}
ONE_DAY = {"start": "2026-08-01", "end": "2026-08-01"}

LARGE = {"openai": "gpt-fake-large", "anthropic": "claude-fake-large"}
MINI = {"openai": "gpt-fake-mini", "anthropic": "claude-fake-mini"}
# Primário de cada feature em gateway/config.yaml; o equivalente é o large do outro provider.
PRIMARY = {"classify": "openai", "extract": "openai", "suggest": "anthropic", "topics": "anthropic"}
OTHER = {"openai": "anthropic", "anthropic": "openai"}


@pytest.fixture
def helpdesk():
    with httpx.Client(base_url=HELPDESK_URL, timeout=90) as client:
        yield client


@pytest.fixture(autouse=True)
def provider_normal():
    httpx.post(f"{PROVIDER_URL}/admin/reset", timeout=10).raise_for_status()
    yield
    httpx.post(f"{PROVIDER_URL}/admin/reset", timeout=10).raise_for_status()


def fail(provider: str, mode: str, model: str | None = None) -> None:
    body = {"provider": provider, "mode": mode} | ({"model": model} if model else {})
    httpx.post(f"{PROVIDER_URL}/admin/failures", json=body, timeout=10).raise_for_status()


def calls(task: str) -> list[dict]:
    """Chamadas recebidas pelo provider para uma tarefa, da mais antiga para a mais recente."""
    recent = httpx.get(f"{PROVIDER_URL}/admin/calls", params={"last": 500}, timeout=10).json()
    return [call for call in reversed(recent) if call["task"] == task]


def path(task: str) -> list[tuple[str, int | None]]:
    return [(call["model"], call["status"]) for call in calls(task)]


def read_sse(helpdesk, payload: dict) -> tuple[httpx.Response, list[tuple[float, str, dict]]]:
    """Eventos da F2 com o instante (s desde o início) em que cada um chegou."""
    events, name, start = [], "message", time.monotonic()
    with helpdesk.stream("POST", "/tickets/reply-suggestion", json=payload) as response:
        if response.status_code != 200:
            response.read()
            return response, events
        for line in response.iter_lines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((time.monotonic() - start, name, json.loads(line.removeprefix("data: "))))
                name = "message"
    return response, events


def request_report(helpdesk, period: dict) -> tuple[httpx.Response, float]:
    start = time.monotonic()
    response = helpdesk.post("/reports/topics", json=period)
    return response, time.monotonic() - start


def wait_report(helpdesk, status_url: str, limit: float) -> tuple[httpx.Response, float]:
    """Acompanha o status até 303 ou failed; devolve a última resposta e o tempo gasto."""
    start = time.monotonic()
    while time.monotonic() - start < limit:
        status = helpdesk.get(status_url, follow_redirects=False)
        assert status.status_code in (200, 303), status.text
        if status.status_code == 303 or status.json()["state"] == "failed":
            return status, time.monotonic() - start
        time.sleep(1)
    pytest.fail(f"o relatório não terminou nem falhou em {limit:.0f} s")


# Fluxos no modo normal ------------------------------------------------------------

def test_f1_responde_em_ate_3_s(helpdesk):
    start = time.monotonic()
    response = helpdesk.post("/tickets/classification", json=TICKET)
    assert response.status_code == 200
    assert time.monotonic() - start <= 3
    assert response.json() == {"ticket_id": "TK-00042", "category": "delivery", "priority": "high"}


def test_f2_primeiro_trecho_em_ate_1_5_s_e_antes_da_metade(helpdesk):
    response, events = read_sse(helpdesk, TICKET)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    first, total = events[0][0], events[-1][0]
    assert events[0][1] == "message" and events[0][2]["chunk"]
    assert first <= 1.5
    assert first < total / 2
    assert events[-1][1:] == ("end", {"ticket_id": "TK-00042"})


def test_f3_aceita_o_mes_em_ate_1_s_e_entrega_5000_tickets(helpdesk):
    accepted, elapsed = request_report(helpdesk, MONTH)
    assert accepted.status_code == 202 and elapsed <= 1
    assert accepted.headers["location"].startswith("/reports/topics/status/")
    assert int(accepted.headers["retry-after"]) > 0
    status, _ = wait_report(helpdesk, accepted.headers["location"], limit=240)
    assert status.status_code == 303, status.json()
    report = helpdesk.get(status.headers["location"])
    assert report.status_code == 200
    assert report.json()["total_tickets"] == 5000
    assert len([c for c in calls("topics") if c["status"] == 200]) == 34   # 5000 / 150 = 34 lotes


# Fallback técnico: primário em error_500 -------------------------------------------

@pytest.mark.parametrize("route,task", [("/tickets/classification", "classify"),
                                        ("/tickets/extraction", "extract")])
def test_fallback_tecnico_sincrono(helpdesk, route, task):
    primary = PRIMARY[task]
    fail(primary, "error_500")
    response = helpdesk.post(route, json=TICKET)
    assert response.status_code == 200
    assert path(task) == [(LARGE[primary], 500), (LARGE[primary], 500), (LARGE[OTHER[primary]], 200)]


def test_fallback_tecnico_streaming(helpdesk):
    fail("anthropic", "error_500")
    response, events = read_sse(helpdesk, TICKET)
    assert response.status_code == 200 and events[-1][1] == "end"
    assert path("suggest") == [(LARGE["anthropic"], 500), (LARGE["anthropic"], 500), (LARGE["openai"], 200)]


def test_fallback_tecnico_assincrono(helpdesk):
    fail("anthropic", "error_500")
    accepted, _ = request_report(helpdesk, ONE_DAY)
    status, _ = wait_report(helpdesk, accepted.headers["location"], limit=60)
    assert status.status_code == 303
    assert path("topics") == [(LARGE["anthropic"], 500), (LARGE["anthropic"], 500), (LARGE["openai"], 200)]


# Fallback com modelo fraco: os dois large em error_500 ------------------------------

def both_large_down() -> None:
    fail("openai", "error_500", LARGE["openai"])
    fail("anthropic", "error_500", LARGE["anthropic"])


def test_f1_sem_large_responde_com_mini(helpdesk):
    both_large_down()
    response = helpdesk.post("/tickets/classification", json=TICKET)
    assert response.status_code == 200
    assert path("classify")[-1] == (MINI["openai"], 200)


def test_f2_sem_large_responde_com_mini(helpdesk):
    both_large_down()
    response, events = read_sse(helpdesk, TICKET)
    assert response.status_code == 200 and events[-1][1] == "end"
    assert path("suggest")[-1] == (MINI["anthropic"], 200)


def test_f3_sem_large_responde_com_mini(helpdesk):
    both_large_down()
    accepted, _ = request_report(helpdesk, ONE_DAY)
    status, _ = wait_report(helpdesk, accepted.headers["location"], limit=60)
    assert status.status_code == 303
    assert path("topics")[-1] == (MINI["anthropic"], 200)


def test_f4_sem_large_falha_explicitamente_sem_mini(helpdesk):
    both_large_down()
    response = helpdesk.post("/tickets/extraction", json=TICKET)
    assert response.status_code == 503
    assert "order-extractor" in response.json()["detail"]
    models = {model for model, _ in path("extract")}
    assert models == {LARGE["openai"], LARGE["anthropic"]}   # nenhuma tentativa no mini
    assert len(path("extract")) == 4                          # 2 no primário + 2 no equivalente


# Provider travado e falhas sem saída ----------------------------------------------

def test_f1_com_primario_travado_responde_em_ate_15_s(helpdesk):
    fail("openai", "timeout")
    start = time.monotonic()
    response = helpdesk.post("/tickets/classification", json=TICKET)
    assert response.status_code in (200, 503)
    assert time.monotonic() - start <= 15


def test_f3_com_os_dois_providers_fora_falha_visivel_em_ate_60_s(helpdesk):
    fail("openai", "error_500")
    fail("anthropic", "error_500")
    accepted, _ = request_report(helpdesk, MONTH)
    status, elapsed = wait_report(helpdesk, accepted.headers["location"], limit=60)
    assert status.status_code == 200
    assert status.json()["state"] == "failed" and status.json()["reason"]
    assert elapsed <= 60


def test_f2_erro_no_meio_do_stream_vira_evento_error(helpdesk):
    fail("anthropic", "midstream_error", LARGE["anthropic"])
    response, events = read_sse(helpdesk, TICKET)
    assert response.status_code == 200
    assert events[0][1] == "message"   # o texto começou a chegar antes do erro
    assert events[-1][1:] == ("error", {"ticket_id": "TK-00042", "message": "A geração foi interrompida"})


# Governança no gateway --------------------------------------------------------------

def gateway_call(key: str) -> httpx.Response:
    return httpx.post(f"{GATEWAY_URL}/v1/chat/completions", timeout=30,
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": "ticket-classifier",
                            "messages": [{"role": "user", "content": "TASK: classify\nFui cobrado duas vezes"}]})


def test_recusa_por_orcamento_nao_chega_ao_provider():
    key = os.environ.get("ROTEIRO_ORCAMENTO_KEY", "sk-roteiro-orcamento-0001")
    # A primeira chamada pode passar (o gasto ainda está abaixo do teto) e estoura o orçamento.
    first = gateway_call(key)
    assert first.status_code in (200, 429)
    before = len(calls("classify"))
    refused = gateway_call(key)
    assert refused.status_code == 429 and "Budget" in refused.text
    assert len(calls("classify")) == before


def test_recusa_por_limite_de_requisicoes_nao_chega_ao_provider():
    key = os.environ.get("ROTEIRO_RPM_KEY", "sk-roteiro-rpm-0001")
    responses = [gateway_call(key) for _ in range(2)]
    before = len(calls("classify"))
    refused = gateway_call(key)
    assert refused.status_code == 429 and "Rate limit" in refused.text, [r.status_code for r in responses]
    assert len(calls("classify")) == before
