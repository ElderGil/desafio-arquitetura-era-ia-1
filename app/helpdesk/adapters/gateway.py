from openai import OpenAI

from ..ports import LanguageModel


class GatewayLanguageModel(LanguageModel):
    """Único ponto da aplicação que fala com o AI Gateway.

    Usa o formato Chat Completions do gateway para qualquer capacidade, seja qual
    for o provider por trás. Não repete chamadas (max_retries=0): retry é política
    do gateway, e retries em camadas se multiplicam.
    """

    def __init__(self, base_url: str, api_key: str, timeout: float, max_output_tokens: int):
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)
        self._max_output_tokens = max_output_tokens

    def complete(self, capability: str, task: str, content: str) -> str:
        response = self._client.chat.completions.create(
            model=capability,
            max_tokens=self._max_output_tokens,
            messages=[{"role": "user", "content": f"TASK: {task}\n{content}"}],
        )
        return response.choices[0].message.content
