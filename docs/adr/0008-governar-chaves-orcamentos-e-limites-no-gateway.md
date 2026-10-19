# 0008. Governar chaves, orçamentos e limites no gateway

- Status: aceita
- Data: 2026-10-19
- Nível: solução

## Contexto

O requisito 5 pede pelo menos uma chave com orçamento e uma com limite de requisições, e que a requisição fora do limite seja recusada antes de chegar ao provider.

Na v1 não existe nenhum controle de gasto. Um relatório do mês custa cerca de US$ 0,85 (222 mil tokens de entrada e 12 mil de saída no `claude-fake-large`), e a dor 1 mostrou esse gasto acontecendo sem ninguém receber o resultado. Os valores em US$ deste ADR são custo calculado com os preços do provider simulado: nenhum provider real é chamado.

O teto de gasto do helpdesk é decisão corporativa ([0009](0009-limitar-o-gasto-mensal-com-ia-do-helpdesk.md)). Aqui decidimos como ele vira regra executável.

## Opções consideradas

1. Políticas nas virtual keys do gateway, com preços declarados por modelo.
2. Contar tokens e custo na aplicação.
3. Só a chave da aplicação, com orçamento e limite apertados.

## Decisão

Opção 1, com as chaves versionadas em `gateway/keys.yaml` e criadas pelo `gateway-init` ([0004](0004-criar-as-virtual-keys-na-subida-sem-passo-manual.md)):

| chave | acesso | orçamento | limite | papel |
|---|---|---|---|---|
| `helpdesk-app` | as 4 capacidades | US$ 100 por 30 dias | 600 req/min | a política real da aplicação |
| `roteiro-orcamento` | `ticket-classifier` | US$ 0,0001 | — | demonstra a recusa por orçamento |
| `roteiro-rpm` | `ticket-classifier` | — | 2 req/min | demonstra a recusa por limite |

Os preços de cada modelo estão declarados em `gateway/config.yaml`. Sem eles, o LiteLLM calcula custo zero e nenhum orçamento estoura.

O limite de 600 req/min da aplicação não aperta o uso normal: o pico previsto é a F3 com 8 chamadas simultâneas. Ele serve para conter um laço descontrolado. A opção 3 foi descartada pelo mesmo motivo: um limite apertado na chave da aplicação derrubaria o próprio helpdesk (e a suíte do avaliador) com `429`. Por isso as chaves de roteiro aplicam a mesma política em escala mínima.

A opção 2 obrigaria cada serviço a reimplementar contagem de tokens e preço por modelo, que é exatamente o que o gateway centraliza.

## Consequências

- Recusa por orçamento e por limite é `429`, devolvida pelo gateway sem chamar o provider.
- O gasto é acumulado no banco do gateway ([0003](0003-usar-postgres-dedicado-para-o-estado-do-gateway.md)) e sobrevive a reinícios. A chave `roteiro-orcamento` continua estourada até `docker compose down -v`, e no roteiro do README a primeira chamada pode já ser recusada.
- Quando a aplicação estourar o teto mensal, todas as features recebem `503` (o gateway recusa e a aplicação não tem destino) até a janela de 30 dias renovar. É o comportamento pedido pela decisão corporativa: parar é preferível a gastar sem teto.

## Evidência

- `uv run pytest tests/acceptance -k recusa -v`: as duas recusas são `429` e o número de chamadas no `/admin/calls` não aumenta.
- O roteiro de governança do README repete isso com `curl` direto no gateway (`localhost:4000`).
- `curl -s "localhost:4000/key/info?key=$HELPDESK_GATEWAY_KEY" -H "Authorization: Bearer $LITELLM_MASTER_KEY"` mostra `max_budget`, `budget_duration`, `rpm_limit` e o `spend` acumulado.
