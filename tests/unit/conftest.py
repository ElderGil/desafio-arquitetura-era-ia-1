import sys
from pathlib import Path

# A aplicação vive em app/; os testes de unidade importam o pacote helpdesk direto.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
