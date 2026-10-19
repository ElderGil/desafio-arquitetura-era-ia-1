# 0009. Limitar o gasto mensal com IA do helpdesk

- Status: aceita
- Data: 2026-10-19
- Nível: corporativa

## Contexto

A conta de IA "chegou" três meses depois da adoção, e o relatório mensal sozinho gastava sem entregar (dor 1). Gasto com IA varia com volume, tamanho do texto e modelo, e um defeito (um laço, um relatório disparado em repetição) pode multiplicá-lo sem que ninguém perceba até a fatura. Decidir quanto a empresa aceita gastar com IA no atendimento é uma decisão de negócio, não de código: ela define até onde a operação continua sozinha e quando alguém precisa aprovar mais.

Estimativa de um mês normal, com os preços do provider simulado e o volume de agosto (5.000 tickets):

| item | conta | por mês |
|---|---|---|
| F1 em todos os tickets | 5.000 x US$ 0,00023 | US$ 1,15 |
| F4 em todos os tickets | 5.000 x US$ 0,00023 | US$ 1,15 |
| F2 em todos os tickets | 5.000 x US$ 0,0092 | US$ 46,00 |
| F3, cerca de 10 relatórios do mês | 10 x US$ 0,85 | US$ 8,50 |
| total | | cerca de US$ 57 |

## Opções consideradas

1. Teto mensal de US$ 100 para o helpdesk, renovado a cada 30 dias.
2. Teto justo, de US$ 60.
3. Sem teto, só acompanhamento da fatura.

## Decisão

Opção 1. Os US$ 100 cobrem um mês de pico (cerca de 75% acima do normal) e barram o gasto descontrolado. A opção 2 pararia o atendimento num mês só um pouco acima do normal. A opção 3 é a situação de hoje, a que trouxe a conta.

Ao atingir o teto, a operação de IA do helpdesk para até a renovação, e aumentar o teto passa por aprovação de quem responde pelo orçamento.

## Consequências

- O teto vira o orçamento da chave da aplicação no gateway ([0008](0008-governar-chaves-orcamentos-e-limites-no-gateway.md)).
- Atingir o teto derruba as quatro features ao mesmo tempo. Monitorar o gasto antes disso fica como próximo passo: observabilidade além de logs está fora do escopo deste trabalho.
- A estimativa precisa ser refeita quando o volume de tickets ou os preços mudarem.

## Evidência

- `gateway/keys.yaml`: `helpdesk-app` com `max_budget: 100` e `budget_duration: 30d`.
- `curl -s "localhost:4000/key/info?key=$HELPDESK_GATEWAY_KEY" -H "Authorization: Bearer $LITELLM_MASTER_KEY"` mostra o teto e o gasto acumulado.
