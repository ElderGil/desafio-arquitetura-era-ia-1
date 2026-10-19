# 0005. Ler a métrica com exceções declaradas e guardadas por contrato

- Status: aceita
- Data: 2026-10-19
- Nível: software

## Contexto

A régua do requisito 3 (Ca, Ce, I, A, D por módulo de `app/helpdesk/`) é fixa e é o juiz da refatoração. Ela é aplicada por `metrics/coupling.py`, conferido em `tests/metrics/test_coupling.py` contra um pacote com valores calculados à mão.

Na v1, `config`, `schemas` e `llm` estavam na zona de dor (A < 0,5, I < 0,5 e D ≥ 0,5). Na v2 e na `main`, o `llm` saiu e ficaram dois componentes:

- `schemas`: Ca = 5, Ce = 0, I = 0, A = 0, D = 1. São os tipos pydantic do contrato HTTP (`TicketInput`, `Classification`, `OrderData`, `PeriodInput`, `Topic`, `TopicsReport`), sem comportamento;
- `config`: Ca = 1, Ce = 0, I = 0, A = 0, D = 1. São o endereço do gateway, a virtual key, os nomes das capacidades e parâmetros, lidos só pelo `main`.

Os adapters (`adapters.gateway`, `adapters.tickets_file` e, na `main`, `adapters.jobs`) ficaram fora da zona de dor, mas na fronteira: I = 0,50 e D = 0,50. Eles só estão fora porque o critério exige I < 0,5 estrito, e um segundo componente que os importe os coloca dentro.

O enunciado permite declarar componentes concretos que quase nunca mudam como estáveis por natureza, com justificativa. O componente que chama o gateway e os das features não podem ser exceção.

## Opções consideradas

1. Declarar `schemas` e `config` como exceções e guardar cada uma (e a margem dos adapters) com um contrato do import-linter.
2. Declarar as exceções só por escrito.
3. Mexer na estrutura até os pontos saírem da zona: tornar `schemas` "abstrato", dissolver o `config` no `main`, criar imports para empurrar os adapters.

## Decisão

Opção 1.

- **`schemas` é estável por natureza.** Tipo de valor do contrato HTTP só muda quando o contrato muda, e aí todos os dependentes mudariam de qualquer jeito. Inverter dependência sobre um tipo de valor não protege ninguém. O contrato `nucleo-estavel` garante que ele não passe a depender de nada concreto do helpdesk.
- **`config` é estável por natureza.** Depois da refatoração, sobraram nele só os nomes lógicos das capacidades, o endereço do gateway, a virtual key e parâmetros de composição. Os elementos voláteis da v1 (modelos físicos, URLs e chaves dos providers) migraram para `gateway/config.yaml`. Ele é dado de composição, lido só pelo `main`. A dor que a zona aponta (muitos dependentes de um concreto difícil de mudar) acabou: o Ca caiu de 6 para 1. O contrato `config-so-no-main` impede que volte a crescer.
- **A margem dos adapters vira regra.** O contrato `adapters-so-no-main` garante que só o ponto de composição dependa deles, que é o que os mantém fora da zona.

A opção 2 vale até o próximo import descuidado. A opção 3 é desenhar o código em função da fórmula, que o próprio enunciado desaconselha.

## Consequências

- As exceções não dependem de alguém lembrar delas: `PYTHONPATH=app uv run lint-imports` quebra se qualquer feature, port ou adapter importar `config`, ou se qualquer coisa além do `main` importar um adapter.
- Uma nova necessidade de configuração dentro de uma feature tem que chegar por construtor, montada no `main`. É mais cerimônia, e é de propósito.
- Se o `schemas` ganhar comportamento (regra de negócio, chamada externa), deixa de ser tipo de valor, e a exceção precisa ser revista.

## Evidência

- `uv run python metrics/coupling.py app/helpdesk --name main`: na zona de dor só `config` e `schemas`. Na `main`, `ports` tem A = 0,67 (dois Protocols e a exceção `ModelUnavailable`, que faz parte do contrato do port) e D = 0,33, com 8 dependentes.
- `PYTHONPATH=app uv run lint-imports`: os 4 contratos mantidos.
- `metrics/results/comparison.md`: o Ca do `config` cai de 6 (v1-coupled) para 1 (v2-decoupled).
