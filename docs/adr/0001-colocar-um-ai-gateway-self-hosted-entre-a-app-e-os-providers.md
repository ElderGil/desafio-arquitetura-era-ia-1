# 0001. Colocar um AI Gateway self-hosted entre a aplicação e os providers

- Status: aceita
- Data: 2026-10-19
- Nível: solução

## Contexto

Na v1, cada feature chama o SDK do provider de dentro do código (`app/helpdesk/llm.py`). A aplicação conhece dois SDKs, dois formatos de API, duas chaves e quatro nomes de modelo físico (`app/helpdesk/config.py`). O diagnóstico do README mostrou o preço disso:

- com a Anthropic em `error_500`, F2 e F3 respondem `500` depois de 3 tentativas cada, enquanto o `gpt-fake-large`, equivalente, estava no ar;
- com a OpenAI em `timeout`, uma única requisição à F1 prendeu a aplicação por cerca de 15 minutos (3 tentativas de 300 s), e o cliente já tinha recebido `504` da borda em 29,6 s;
- trocar o modelo da F1 exigiu editar `config.py` e reconstruir a imagem: `restart` não bastou.

Credencial, retry, timeout, fallback, custo e limite estão espalhados ou simplesmente não existem. O enunciado exige que tudo isso saia da aplicação, que a troca de modelo seja configuração e que o gateway rode localmente (gateway SaaS está fora).

## Opções consideradas

1. LiteLLM Proxy como serviço `gateway` no compose.
2. Um gateway mais novo e open source (Bifrost, Portkey OSS).
3. Um gateway próprio em FastAPI, escrito por nós.
4. LiteLLM como biblioteca dentro da aplicação, sem proxy.

## Decisão

Opção 1, na imagem `ghcr.io/berriai/litellm:v1.102.1`, a versão com que o `provider-fake` foi testado.

A opção 4 resolve compatibilidade de formato, mas mantém a credencial dos providers e a política de resiliência dentro do processo da aplicação. Ou seja, não resolve o problema de credencial nem de governança. A opção 3 dá controle total, mas vira código nosso para escrever, testar e operar só para chegar onde o LiteLLM já está, e o enunciado pede foco em arquitetura, não em ferramenta. A opção 2 traria repertório novo, mas sem compatibilidade testada com o provider simulado, com risco de travar em fricção de ferramenta.

O gateway fica entre a aplicação e os providers e é a única porta de saída para eles. A aplicação fala com ele pelo formato Chat Completions (SDK da OpenAI com `base_url` no gateway), seja qual for o provider por trás.

## Consequências

- A aplicação passa a ter um único cliente, um único formato e uma única credencial (a virtual key do gateway). O componente que chama o gateway é `app/helpdesk/adapters/gateway.py`, e só o ponto de composição (`main.py`) depende dele.
- Retry fica só no gateway: o cliente da aplicação usa `max_retries=0`, para que as tentativas não se multipliquem em camadas.
- Passa a existir mais um serviço para subir e vigiar, e ele vira caminho crítico: se o gateway cai, todas as features caem juntas. O gateway precisa de healthcheck e a aplicação só sobe depois dele.
- Virtual keys e orçamento exigem um banco ([0003](0003-usar-postgres-dedicado-para-o-estado-do-gateway.md)).

## Evidência

- `docker compose config` mostra o serviço `app` só com `GATEWAY_URL` e `GATEWAY_API_KEY`, sem `env_file`.
- `grep -rE "gpt-fake|claude-fake|FAKE_OPENAI_KEY|FAKE_ANTHROPIC_KEY|sk-fake-openai|sk-ant-fake" app/` não retorna nada.
- Depois de uma chamada a qualquer feature, `curl -s "localhost:8090/admin/calls?last=1"` mostra a chamada chegando ao provider pelo gateway, no modelo configurado em `gateway/config.yaml`.
