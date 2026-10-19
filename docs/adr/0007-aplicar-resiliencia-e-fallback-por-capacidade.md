# 0007. Aplicar resiliência e fallback por capacidade, com o modelo fraco decidido feature a feature

- Status: aceita
- Data: 2026-10-19
- Nível: solução

## Contexto

Na v1 não há timeout nem retry explícitos: valem os padrões dos SDKs (600 s de leitura, 2 retries). Com a OpenAI travada, uma requisição à F1 prendeu a aplicação por cerca de 15 minutos. Com a Anthropic fora, F2 e F3 pararam, embora o `large` equivalente da OpenAI estivesse no ar.

Retry e fallback resolvem a disponibilidade, mas não a qualidade. Medimos as quatro tarefas nos dois tamanhos, direto no provider simulado, com os 300 primeiros tickets:

| tarefa | `mini` x `large` | leitura |
|---|---|---|
| `classify` | 0 de 300 divergem | o `mini` serve |
| `topics` | lote de 150 idêntico | o `mini` serve |
| `suggest` | cerca de 1.000 caracteres contra 2.400, mesma abertura e mesmos passos, sem as repetições | resposta mais curta, ainda útil |
| `extract` | 90 de 300 divergem: 45 números de pedido errados (o `mini` pega o primeiro número de 6 dígitos, que pode ser a nota fiscal) e o produto sempre `null` | o `mini` não serve |

Exemplo do erro do `mini` em `TK-00002`: "Tenho aqui a nota fiscal 530720 (...) pedido #605065". O `large` devolve `#605065`; o `mini` devolve `#530720`.

## Opções consideradas

1. Resiliência e fallback no gateway, com o modelo fraco liberado por capacidade.
2. Retry e fallback na aplicação, com o gateway só repassando.
3. Fallback com modelo fraco igual para todas as features.

## Decisão

Opção 1. Os mecanismos moram no gateway (`gateway/config.yaml`). A aplicação não repete chamadas (`max_retries=0`) e só tem um timeout de segurança acima do pior caso do gateway (`app/helpdesk/config.py`).

### Resiliência (igual para todas as capacidades)

- **Timeout por tentativa**, conforme o orçamento de latência de cada feature: F1 e F4 com 4 s; F2 com 2 s até o primeiro trecho (`stream_timeout`); F3 com 20 s por lote.
- **Retry limitado, só para falha transitória**: `500` e `429` têm 1 retry com backoff; timeout não tem retry (`TimeoutErrorRetries: 0`), porque repetir um travamento só dobra a espera.
- **Fallback técnico** para o `large` do outro provider (destino `-equivalente`), para toda capacidade.
- **Cooldown desligado** (`disable_cooldowns: true`): o primário é tentado em toda requisição. Circuit breaker está fora do escopo, e o cooldown esconderia do `/admin/calls` as tentativas no primário.

Número máximo de tentativas por destino: 2 no primário, 2 no equivalente e 1 no fraco.

### F1 Classificar ticket: fraco permitido

Uma classificação idêntica a mais barata é melhor que nenhuma, e o cliente que abriu o ticket recebe a confirmação. Sem `large`, responde `200` pelo `gpt-fake-mini`.

### F2 Sugerir resposta: fraco permitido

O atendente está na tela e edita o texto antes de enviar. Uma sugestão mais curta, mas correta, é melhor que a tela vazia. Sem `large`, o stream sai pelo `claude-fake-mini`.

### F3 Relatório de temas: fraco permitido

O resultado do `mini` foi idêntico, e o relatório é interno e agregado. Sem `large`, os lotes saem pelo `claude-fake-mini`.

### F4 Extrair dados do pedido: fraco proibido

A F4 alimenta uma troca automática sem revisão humana. No `mini`, cerca de 15% dos pedidos viriam errados, e cada erro vira uma troca errada (frete, estoque e cliente). Uma resposta pior aqui é pior que nenhuma. Sem `large`, o gateway não tem para onde ir (`order-extractor` só tem o equivalente como fallback), e a aplicação responde `503` com `"Nenhum modelo disponível para order-extractor no momento"`. A automação reprocessa depois.

## Consequências

- Pior caso da F1 e da F4 com o primário travado: 4 s e o fallback, cerca de 5 s. Com tudo travado: até 12 s no gateway, cortados pela aplicação em 13 s. Fica dentro dos 15 s.
- O fallback técnico entre providers equivalentes devolve a mesma saída, porque os dois `large` são equivalentes no provider simulado. Com providers reais, isso precisaria ser medido.
- O fallback para o fraco degrada a F2 de forma visível (texto mais curto). O atendente percebe, e é aceitável. Na F4, a mesma degradação seria invisível e cara, e por isso é proibida.
- Retry fica num lugar só. Somar retries do SDK, do gateway e da aplicação multiplicaria as tentativas.

## Evidência

- `uv run pytest tests/acceptance -v`:
  - `test_fallback_tecnico_*`: com o primário em `error_500`, o `/admin/calls` mostra 2 tentativas no primário e o sucesso no equivalente, em F1, F4, F2 (stream) e F3 (lote);
  - `test_f*_sem_large_*`: com os dois `large` em `error_500`, F1, F2 e F3 terminam no `mini` correspondente; a F4 responde `503` com 4 tentativas, nenhuma no `mini`;
  - `test_f1_com_primario_travado_responde_em_ate_15_s`.
- A comparação `large` x `mini` pode ser refeita direto no provider: `POST /openai/v1/chat/completions` com `TASK: extract` em `TK-00002`, nos dois modelos.
