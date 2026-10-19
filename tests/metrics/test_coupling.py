"""Confere a régua do script de métrica num pacote com valores calculados à mão.

Pacote `shop` usado nos testes:

    shop/__init__.py           (fora da medição)
    shop/types.py              2 classes, nenhuma abstrata
    shop/ports.py              Store(Protocol), Clock(ABC), Repo(Protocol[T]), Helper -> 3 de 4 abstratas
    shop/service.py            from . import types; from .ports import Store; import json
    shop/main.py               from shop import service; import shop.adapters.db
    shop/adapters/__init__.py  (fora da medição)
    shop/adapters/db.py        from ..ports import Store; from ..types import Item; import httpx

Arestas: service->types, service->ports, main->service, main->adapters.db,
adapters.db->ports, adapters.db->types.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "metrics" / "coupling.py"
spec = importlib.util.spec_from_file_location("coupling", SCRIPT)
coupling = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coupling)

FILES = {
    "__init__.py": "",
    "types.py": "class Item:\n    pass\n\n\nclass Money:\n    pass\n",
    "ports.py": (
        "import abc\nfrom typing import Protocol, TypeVar\n\nT = TypeVar('T')\n\n\n"
        "class Store(Protocol):\n    def save(self): ...\n\n\n"
        "class Clock(abc.ABC):\n    pass\n\n\n"
        "class Repo(Protocol[T]):\n    pass\n\n\n"
        "class Helper:\n    pass\n"
    ),
    "service.py": "import json\n\nfrom . import types\nfrom .ports import Store\n",
    "main.py": "import shop.adapters.db\nfrom shop import service\n",
    "adapters/__init__.py": "",
    "adapters/db.py": "import httpx\n\nfrom ..ports import Store\nfrom ..types import Item\n",
}

# component: (ca, ce, i, a, d)
EXPECTED = {
    "adapters.db": (1, 2, 0.67, 0.0, 0.33),   # I = 2/3
    "main": (0, 2, 1.0, 0.0, 0.0),
    "ports": (2, 0, 0.0, 0.75, 0.25),
    "service": (1, 2, 0.67, 0.0, 0.33),
    "types": (2, 0, 0.0, 0.0, 1.0),
}


@pytest.fixture
def shop(tmp_path):
    root = tmp_path / "shop"
    for relative, content in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def test_components_exclude_init_and_use_dotted_names(shop):
    assert set(coupling.analyze(shop)) == set(EXPECTED)


def test_dependencies_resolve_relative_and_absolute_imports(shop):
    components = coupling.analyze(shop)
    assert components["service"].depends_on == {"types", "ports"}
    assert components["main"].depends_on == {"service", "adapters.db"}
    assert components["adapters.db"].depends_on == {"ports", "types"}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_metrics_match_hand_calculation(shop, name):
    rows = {row["component"]: row for row in coupling.metrics(coupling.analyze(shop))}
    row = rows[name]
    assert (row["ca"], row["ce"], row["i"], row["a"], row["d"]) == EXPECTED[name]


def test_isolated_module_has_zero_instability(tmp_path):
    root = tmp_path / "solo"
    root.mkdir()
    (root / "alone.py").write_text("import os\n", encoding="utf-8")
    [row] = coupling.metrics(coupling.analyze(root))
    assert (row["ca"], row["ce"], row["i"], row["a"], row["d"]) == (0, 0, 0.0, 0.0, 1.0)


def test_csv_header_is_exact(shop, tmp_path):
    out = tmp_path / "result.csv"
    coupling.write_csv(coupling.metrics(coupling.analyze(shop)), out)
    assert out.read_text(encoding="utf-8").splitlines()[0] == "component,ca,ce,i,a,d"


def test_no_cycles_in_acyclic_package(shop):
    assert coupling.cycles(coupling.analyze(shop)) == []


def test_detects_cycle(tmp_path):
    root = tmp_path / "loop"
    root.mkdir()
    (root / "a.py").write_text("from . import b\n", encoding="utf-8")
    (root / "b.py").write_text("from . import c\n", encoding="utf-8")
    (root / "c.py").write_text("from . import a\n", encoding="utf-8")
    (root / "d.py").write_text("from . import a\n", encoding="utf-8")
    assert coupling.cycles(coupling.analyze(root)) == [["a", "b", "c"]]


def test_pain_zone_rule():
    assert coupling.in_pain_zone({"a": 0.0, "i": 0.0, "d": 1.0})
    assert not coupling.in_pain_zone({"a": 0.0, "i": 0.5, "d": 0.5})   # I = 0,5 não é < 0,5
    assert not coupling.in_pain_zone({"a": 0.75, "i": 0.0, "d": 0.25})
