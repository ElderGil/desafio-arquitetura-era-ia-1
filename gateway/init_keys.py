"""Cria ou atualiza as virtual keys de gateway/keys.yaml no LiteLLM.

Roda no serviço gateway-init depois que o gateway fica saudável. É idempotente:
chave inexistente é criada com /key/generate; chave existente tem modelos e
limites reaplicados com /key/update, preservando o gasto acumulado.
"""

import json
import os
import sys
import urllib.error
import urllib.request

import yaml

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:4000")
MASTER_KEY = os.environ["LITELLM_MASTER_KEY"]
KEYS_FILE = os.environ.get("KEYS_FILE", "/app/keys.yaml")
LIMIT_FIELDS = ("models", "max_budget", "budget_duration", "rpm_limit", "tpm_limit")


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{GATEWAY_URL}{path}", data=data, method=method, headers={
        "Authorization": f"Bearer {MASTER_KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def main() -> int:
    with open(KEYS_FILE, encoding="utf-8") as file:
        specs = yaml.safe_load(file)["keys"]
    for spec in specs:
        key = os.environ[spec["key_env"]]
        limits = {field: spec[field] for field in LIMIT_FIELDS if field in spec}
        status, _ = call("GET", f"/key/info?key={key}")
        if status == 200:
            status, body = call("POST", "/key/update", {"key": key, "key_alias": spec["alias"], **limits})
            action = "atualizada"
        else:
            status, body = call("POST", "/key/generate", {"key": key, "key_alias": spec["alias"], **limits})
            action = "criada"
        if status != 200:
            print(f"falha na chave {spec['alias']}: {status} {body}", file=sys.stderr)
            return 1
        print(f"chave {spec['alias']} {action}: {limits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
