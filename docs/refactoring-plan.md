# Plano de refatoração: da v1-coupled à v2-decoupled

Este documento é vivo. A seção 1 a 5 é o plano original, escrito antes do piloto; a seção 6 registra o piloto com a medição antes e depois; a seção 7 registra o que mudou no plano e por quê; a seção 8 registra o handoff para o agente que escalou a refatoração.

## 1. Ponto de partida (v1-coupled)

Medição com `metrics/coupling.py` sobre a tag `v1-coupled` (`metrics/results/v1-coupled.csv`):

| componente | Ca | Ce | I | A | D | leitura |
|---|---|---|---|---|---|---|
| `config` | 6 | 0 | 0,00 | 0,00 | 1,00 | **zona de dor**: chaves, URLs e nomes de modelo físicos, importado por seis componentes |
| `schemas` | 5 | 0 | 0,00 | 0,00 | 1,00 | **zona de dor**: tipos de valor pydantic |
| `llm` | 4 | 1 | 0,20 | 0,00 | 0,80 | **zona de dor**: dois clientes de SDK concretos, chamados direto pelas quatro features |
| `tickets` | 1 | 1 | 0,50 | 0,00 | 0,50 | no limite; lê o arquivo do caminho fixo em `config` |
| `classification`, `extraction`, `suggestion` | 1 | 3 | 0,75 | 0,00 | 0,25 | conhecem `config`, `llm` e o modelo físico |
| `report` | 1 | 4 | 0,80 | 0,00 | 0,20 | idem, mais `tickets` |
| `main` | 0 | 5 | 1,00 | 0,00 | 0,00 | rotas |

O grafo (`metrics/results/v1-coupled-dependencies.md`) não tem ciclos. O problema é de direção: tudo aponta para dois concretos instáveis por natureza (`config` e `llm`), e é exatamente por eles que passam provider, modelo, credencial e formato de API. É o acoplamento que as quatro dores do diagnóstico expõem.

## 2. Componentes-alvo e estratégia

| alvo | estratégia | resultado esperado |
|---|---|---|
| `llm` | **inverter a dependência.** Nasce `ports.LanguageModel` (Protocol) com a operação que as features precisam (pedir uma capacidade lógica para uma tarefa). A implementação concreta vai para `adapters.gateway`, único componente que conhece o SDK e o endereço do gateway. Ele declara explicitamente que implementa o port (`class GatewayLanguageModel(LanguageModel)`), para que o contrato seja verificável. O módulo `llm` deixa de existir. | `ports` estável e abstrato (A = 1, D ≈ 0); `adapters.gateway` concreto, com Ca = 1 (só o `main`) e fora da zona de dor |
| `config` | **reduzir Ca.** Só o ponto de composição (`main`) lê a configuração. As features recebem por construtor o port e o nome da capacidade que usam. | `config` com Ca = 1, sem nomes físicos de modelo nem chaves de provider |
| features (`classification`, `extraction`, `suggestion`, `report`) | **compor em vez de importar.** Cada feature vira uma classe que recebe o `LanguageModel` e a capacidade; depende só de `ports` e `schemas`. | nenhuma feature importa `adapters.*` nem `config` |
| `tickets` | **inverter a dependência da F3.** `ports.TicketSource` (Protocol); a leitura do arquivo vira `adapters.tickets_file`, que recebe o caminho por construtor. O relatório depende do port. | `report` testável sem arquivo; a leitura concreta fora da zona de dor |
| `schemas` | **manter.** São tipos de valor do contrato HTTP, sem comportamento. Declarado como estável por natureza no ADR da métrica. | permanece em (I = 0, A = 0), justificado |
| `main` | **virar o ponto de composição.** Monta adapters e features a partir de `config` e expõe as rotas. | instável e concreto por natureza (I = 1), sobre a Main Sequence |

Fora do escopo desta etapa: mudar modos de resposta (streaming, assíncrono), governança e resiliência do gateway. Entram depois da tag, na `main`.

## 3. Gateway nesta etapa

O mínimo do requisito 4, com o LiteLLM Proxy no serviço `gateway` do compose:

- capacidades lógicas, uma por feature: `ticket-classifier`, `reply-writer`, `topic-analyst` e `order-extractor`;
- nesta tag, cada capacidade aponta para o mesmo modelo `large` que a feature usava na v1 (os dois `large` são equivalentes, mas mantê-los evita qualquer dúvida na suíte);
- a app usa uma chave do próprio gateway (virtual key) e não recebe `FAKE_OPENAI_KEY` nem `FAKE_ANTHROPIC_KEY`;
- a app fala com o gateway pelo SDK da OpenAI com `max_retries=0`: retry é responsabilidade do gateway, e retries em camadas se multiplicam.

## 4. Critério de pronto (v2-decoupled)

Todos mecânicos, nenhum depende de julgamento do agente:

1. `uv run pytest tests/characterization` passa sem nenhuma alteração em `tests/characterization/` (golden master da v1).
2. `metrics/coupling.py` sobre o código novo: nenhum componente na zona de dor, exceto `schemas`.
3. Contratos do import-linter: nenhuma feature importa `adapters` nem `config`; só `main` importa `adapters`.
4. `grep -rE "gpt-fake|claude-fake|FAKE_OPENAI_KEY|FAKE_ANTHROPIC_KEY" app/` não encontra nada.
5. `/admin/calls` mostra cada feature chegando ao mesmo modelo `large` da v1, via gateway.

## 5. Sequência

1. Subir o gateway com as quatro capacidades e a virtual key da app, sem mexer em `app/`.
2. **Piloto em um componente: `llm`.** É o componente que chama o gateway, o único que o critério de aceite proíbe declarar como exceção, e o que concentra a dor de troca de modelo e de provider.
3. Medir, comparar com a previsão e revisar o plano.
4. Escalar para `config`, features e `tickets` com um agente, usando o contrato da seção 4 como aceite.
5. Medir a v2, rodar a suíte e marcar `v2-decoupled`.

## 6. Piloto: `llm`

O que mudou:

- nasceu `ports.LanguageModel` (Protocol, uma operação: `complete(capability, task, content)`);
- nasceu `adapters.gateway.GatewayLanguageModel`, que implementa o port falando com o gateway pelo SDK da OpenAI (`max_retries=0`). É o único arquivo da app que importa um SDK;
- `llm.py` saiu; as quatro features passaram a receber o `LanguageModel` como parâmetro, e o `main` monta o adapter;
- `config.py` trocou chaves de provider, URLs e nomes de modelo físicos por endereço e chave do gateway e nomes de capacidade;
- o serviço `app` no compose deixou de receber o `.env`: recebe só `GATEWAY_URL` e a virtual key.

Resultado: `uv run pytest tests/characterization` passou sem alteração (39 testes). O `/admin/calls` mostrou cada feature chegando ao mesmo modelo `large` da v1, agora pelo gateway, uma chamada por requisição.

Medição antes (v1-coupled) e depois (piloto):

| componente | antes: Ca / Ce / I / A / D | depois: Ca / Ce / I / A / D |
|---|---|---|
| `llm` | 4 / 1 / 0,20 / 0,00 / **0,80 dor** | removido |
| `ports` | — | 5 / 0 / 0,00 / 1,00 / 0,00 |
| `adapters.gateway` | — | 1 / 1 / 0,50 / 0,00 / 0,50 |
| `config` | 6 / 0 / 0,00 / 0,00 / **1,00 dor** | 6 / 0 / 0,00 / 0,00 / **1,00 dor** |
| `schemas` | 5 / 0 / 0,00 / 0,00 / **1,00 dor** | 5 / 0 / 0,00 / 0,00 / **1,00 dor** |
| `tickets` | 1 / 1 / 0,50 / 0,00 / 0,50 | 1 / 1 / 0,50 / 0,00 / 0,50 |
| `main` | 0 / 5 / 1,00 / 0,00 / 0,00 | 0 / 7 / 1,00 / 0,00 / 0,00 |
| features | Ce 3 ou 4, I de 0,75 a 0,80 | iguais (trocaram `llm` por `ports`) |

Contratos do import-linter no piloto: "ports e schemas não dependem de nada concreto" e "só o main importa adapters" mantidos; "features não conhecem config" quebrado nas quatro features e no caminho `report → tickets → config`, que é exatamente o trabalho da escala.

## 7. Revisões do plano

**Revisão 1, depois do piloto: a margem do adapter é zero, então a regra vira contrato.** O plano previa `adapters.gateway` "fora da zona de dor". A medição mostrou que ele está na fronteira: I = 0,50 e D = 0,50. Ele só fica fora porque o critério exige I < 0,5 estrito. Um segundo componente que o importe (Ca = 2) leva o I a 0,33 e o coloca na zona de dor. Mudanças:

- "só o `main` importa adapters" deixa de ser uma intenção do plano e vira contrato verificado (`.importlinter`, contrato `adapters-so-no-main`), parte do critério de pronto;
- a leitura no ADR da métrica registra a margem: o adapter é concreto por definição e fica saudável enquanto só o ponto de composição depender dele.

**Revisão 2, depois do piloto: a dependência transitiva `report → tickets → config` sobe de prioridade.** O import-linter mostrou que, mesmo removendo o `import config` do relatório, a F3 continuaria presa ao `config` pelo `tickets`. O `tickets` também está na fronteira (I = 0,50, D = 0,50) e cairia na zona de dor (Ca = 1, Ce = 0) assim que deixasse de ler o `config`. Por isso a inversão de `tickets` (`ports.TicketSource` + `adapters.tickets_file`) deixa de ser opcional e entra na mesma fatia que tira o `config` das features.

**Revisão 3, depois do piloto: o critério de pronto ganha o comando do import-linter.** O item 3 da seção 4 passa a ser literalmente `PYTHONPATH=app uv run lint-imports` com os três contratos mantidos, e não uma leitura do agente.

**Revisão 4, depois da escala: o `config` com Ca = 1 continua na zona de dor, e vira exceção guardada.** O plano previa "config com Ca = 1" como resultado bom. A régua mostrou outra coisa: com só o `main` dependendo dele e nenhuma dependência de saída, o `config` fica em I = 0 e A = 0, ou seja, D = 1, na zona de dor. O agente parou nesse ponto, como o handoff mandava, em vez de contornar.

Avaliamos duas saídas:

1. dissolver o `config` dentro do `main`, que faria o ponto sumir do gráfico, mas é desenhar o código em função da fórmula;
2. declarar o `config` como exceção, como o `schemas`.

Ficamos com a segunda, porque a dor que a zona aponta (muitos dependentes de um concreto difícil de mudar) não existe mais: o Ca caiu de 6 para 1. Para que continue assim, entrou um quarto contrato no `.importlinter`, `config-so-no-main`. A exceção deixa de ser só um parágrafo no ADR e passa a ser verificada a cada execução. Detalhes em [0005](adr/0005-ler-a-metrica-com-excecoes-declaradas-e-guardadas.md).

## 8. Handoff para o agente

**Quem.** A escala foi entregue a um subagente do Claude Code com outro modelo (Sonnet 5.5; o plano e o piloto foram feitos com o Opus 5.5), num worktree git isolado, sem acesso a push nem a tag.

**O que foi entregue.** Um prompt de handoff com:

- o contexto, apontando este plano e o commit do piloto (`3f97ab4`);
- cinco tarefas fechadas: features como classes que recebem `LanguageModel` e capacidade por construtor; `ports.TicketSource` mais `adapters.tickets_file` no lugar de `tickets.py`; `main` como único ponto de composição; comportamento externo idêntico; testes de unidade com fakes do port, em TDD por fatias verticais;
- a lista do que estava fora de escopo (testes de caracterização, golden master, provider, borda, dados, gateway, métrica, contratos, compose, docs);
- os comandos para rodar tudo e os cinco critérios de aceite mecânicos da seção 4;
- a regra de parar e relatar, em vez de contornar mudando teste, contrato ou régua, ou criando um import só para mover um ponto no gráfico.

**O que voltou.** Três commits (`8eecd98`, `29960ee`, `ac3f16d`), um por fatia, com 16 testes de unidade novos. Quatro dos cinco critérios passaram. O critério da métrica falhou por causa do `config` (revisão 4), e o agente parou e devolveu a decisão, que era o comportamento pedido. Ele também registrou duas decisões fora do plano:

- adicionou `fastapi` ao grupo de dev da raiz, para os testes de unidade importarem as features (a app não ganhou dependência);
- criou `tests/unit/conftest.py` para os testes rodarem sem `PYTHONPATH`.

**Como aceitamos.** Nada foi aceito pelo relato do agente. Depois do fast-forward para a `main`, rodamos de novo os cinco critérios com a pilha reconstruída:

| critério | resultado |
|---|---|
| `uv run pytest tests/characterization -q` | 39 passed, `tests/characterization/` intocado |
| `PYTHONPATH=app uv run lint-imports` | 4 contratos mantidos (3 do plano e o `config-so-no-main` da revisão 4) |
| `metrics/coupling.py` | só `schemas` e `config` na zona de dor, os dois declarados e guardados |
| grep de nomes físicos e chaves em `app/` | vazio |
| `uv run pytest tests/unit -q` | 16 passed |

O `/admin/calls` mostrou as mesmas chamadas da v1: `classify` e `extract` em `gpt-fake-large`, `suggest` e `topics` em `claude-fake-large`, todas pelo gateway e uma por requisição. O diff do agente tocou só `app/helpdesk/`, `tests/unit/` e o grupo de dev do `pyproject.toml`. Antes da tag, a refatoração passa ainda por uma revisão em par com outro agente, o Antigravity CLI (Gemini), como auditor, e o registro fica no ai-memory.

## 9. Resultado (v2-decoupled)

`metrics/results/comparison.md` e `comparison.png` comparam as versões. De 3 componentes na zona de dor na v1 para 2 na v2, e os dois que ficam mudaram de natureza:

- o `config` passou de 6 dependentes para 1;
- o `schemas` é tipo de valor, sem comportamento.

O `llm` saiu, e a abstração que nasceu no lugar (`ports`) está sobre a Main Sequence (A = 1, I = 0, D = 0), com 6 dependentes. Os dois adapters estão na fronteira (I = 0,50, D = 0,50), protegidos pelo contrato `adapters-so-no-main`.
