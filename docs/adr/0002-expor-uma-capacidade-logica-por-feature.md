# 0002. Expor uma capacidade lógica por feature

- Status: aceita
- Data: 2026-10-19
- Nível: software

## Contexto

Colocar o gateway no caminho não basta se a aplicação continuar pedindo `gpt-fake-large`: muda a topologia, mas a aplicação segue presa ao modelo físico. A aplicação precisa pedir uma capacidade, e o gateway decide qual modelo a atende.

As quatro features têm exigências diferentes, medidas no provider simulado (300 tickets, `large` x `mini`):

- classificação (F1): o `mini` devolve exatamente o mesmo resultado nos 300;
- extração (F4): o `mini` diverge em 90 dos 300, com 45 números de pedido errados (pega a nota fiscal no lugar do pedido) e o produto sempre `null`;
- temas (F3): o `mini` devolve o mesmo resultado no lote testado;
- sugestão (F2): o `mini` devolve cerca de 1.000 caracteres contra 2.400 do `large`.

Ou seja, a política de fallback, o orçamento e o timeout não podem ser os mesmos para F1 e F4, embora as duas sejam "saída curta e estruturada".

## Opções consideradas

1. Uma capacidade por feature: `ticket-classifier`, `reply-writer`, `topic-analyst` e `order-extractor`.
2. Capacidades por perfil: `structured-fast` (F1 e F4) e `long-text` (F2 e F3).
3. Manter os nomes físicos atrás do gateway.

## Decisão

Opção 1. O nome diz a intenção de uso, e cada capacidade carrega a própria política. A opção 2 juntaria F1 e F4 numa política só de fallback, justamente as duas com a maior diferença de risco com o `mini`. A opção 3 não inverte nada.

O mapeamento de cada capacidade para um modelo físico mora em `gateway/config.yaml` (`model_name` é a capacidade; `litellm_params.model` é o modelo físico). A aplicação conhece só os quatro nomes, em `app/helpdesk/config.py`, e cada feature recebe a sua por construtor.

## Consequências

- Trocar o modelo de uma feature é editar uma entrada de `gateway/config.yaml` e reiniciar só o gateway, sem tocar no modelo das outras features.
- Quatro entradas no gateway em vez de duas, com alguma repetição de configuração entre capacidades que hoje usam o mesmo modelo. Aceitamos a repetição: ela é o preço de poder separar as políticas.
- Uma feature nova precisa de uma capacidade nova no gateway antes de existir na aplicação.

## Evidência

- `grep -rE "gpt-fake|claude-fake" app/` não retorna nada; `grep -n "model_name" gateway/config.yaml` lista as quatro capacidades.
- O roteiro "Troca de modelo" do README altera só `gateway/config.yaml`, reinicia só o `gateway` e mostra em `/admin/calls` a próxima chamada já no modelo novo.
