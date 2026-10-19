"""Fixtures da suíte de caracterização.

A suíte fala com o helpdesk pela borda (a mesma porta que o avaliador usa) e
compara cada resposta com o comportamento gravado da v1 em `golden/`.

    CHAR_RECORD=1 uv run pytest tests/characterization   # grava o golden master
    uv run pytest tests/characterization                 # compara com o gravado
"""

import json
import os
from pathlib import Path

import httpx
import pytest

HELPDESK_URL = os.environ.get("HELPDESK_URL", "http://localhost:8000")
PROVIDER_URL = os.environ.get("PROVIDER_URL", "http://localhost:8090")
GOLDEN_DIR = Path(__file__).parent / "golden"
RECORD = os.environ.get("CHAR_RECORD") == "1"


@pytest.fixture(scope="session")
def helpdesk():
    # 60 s cobre a sugestão (cerca de 16 s) e o relatório de 2 dias (cerca de 20 s);
    # a borda corta antes, em 30 s.
    with httpx.Client(base_url=HELPDESK_URL, timeout=60) as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def provider_normal():
    """Garante o provider simulado no modo normal antes da suíte."""
    httpx.post(f"{PROVIDER_URL}/admin/reset", timeout=10).raise_for_status()


@pytest.fixture
def golden():
    """Compara (status, corpo) com o arquivo gravado, ou grava quando CHAR_RECORD=1."""

    def check(name: str, response: httpx.Response) -> None:
        observed = {"status": response.status_code, "body": response.json()}
        path = GOLDEN_DIR / f"{name}.json"
        if RECORD:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(observed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return
        assert path.exists(), f"golden master ausente: {path} (grave com CHAR_RECORD=1)"
        expected = json.loads(path.read_text(encoding="utf-8"))
        assert observed == expected

    return check
