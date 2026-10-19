from collections.abc import Iterator

from openai import APIError, OpenAI

from ..ports import LanguageModel, ModelUnavailable


class GatewayLanguageModel(LanguageModel):
    """Único ponto da aplicação que fala com o AI Gateway.

    Usa o formato Chat Completions do gateway para qualquer capacidade, seja qual
    for o provider por trás. Não repete chamadas (max_retries=0): retry e fallback
    são política do gateway, e retries em camadas se multiplicam. O timeout por
    capacidade é a rede de segurança acima do pior caso do gateway (docs/adr).
    """

    def __init__(self, base_url: str, api_key: str, timeouts: dict[str, float], max_output_tokens: int):
        self._client = OpenAI(base_url=base_url, api_key=api_key, max_retries=0)
        self._timeouts = timeouts
        self._max_output_tokens = max_output_tokens

    def _request(self, capability: str, task: str, content: str, stream: bool):
        return self._client.chat.completions.create(
            model=capability,
            max_tokens=self._max_output_tokens,
            messages=[{"role": "user", "content": f"TASK: {task}\n{content}"}],
            stream=stream,
            timeout=self._timeouts[capability],
        )

    def complete(self, capability: str, task: str, content: str) -> str:
        try:
            response = self._request(capability, task, content, stream=False)
        except APIError as error:
            raise ModelUnavailable(capability, type(error).__name__) from error
        return response.choices[0].message.content

    def stream(self, capability: str, task: str, content: str) -> Iterator[str]:
        try:
            for chunk in self._request(capability, task, content, stream=True):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except APIError as error:
            raise ModelUnavailable(capability, type(error).__name__) from error
