# Helpdesk com IA: da integração frágil à arquitetura resiliente

Desafio de arquitetura do MBA em Engenharia de Software com IA da Full Cycle. Este repositório é um fork de [devfullcycle/desafio-arquitetura-era-ia-1](https://github.com/devfullcycle/desafio-arquitetura-era-ia-1), onde está o enunciado original.

## Visão geral

Recebi um helpdesk com quatro features de IA do jeito que elas costumam nascer: cada feature chamando o SDK do provider direto, chave na configuração da aplicação, nome do modelo no código e tudo síncrono. Funciona no dia a dia. O problema aparece quando a conta chega, quando o provider cai e quando alguém pede para trocar de modelo.

A virada teve três passos, cada um medido. Primeiro, travei o comportamento da v1 com testes de caracterização e medi o acoplamento. Depois, refatorei até a aplicação pedir capacidades lógicas a um AI Gateway (LiteLLM), sem conhecer provider, modelo nem chave. Por fim, decidi o modo de execução de cada feature: F1 e F4 síncronas, F2 em streaming e F3 assíncrona.

Quando um provider cai, o gateway tenta de novo uma vez e cai para o modelo equivalente do outro provider. Quando os dois modelos bons caem, cada feature faz o que o ADR dela diz: F1, F2 e F3 respondem com o modelo mais barato, porque a evidência mostrou que a resposta continua útil, e a F4 falha com `503`, porque um número de pedido errado vira uma troca errada.

Os marcos estão nas tags: [`v1-coupled`](https://github.com/ElderGil/desafio-arquitetura-era-ia-1/tree/v1-coupled) (a aplicação recebida mais a suíte de caracterização), [`v2-decoupled`](https://github.com/ElderGil/desafio-arquitetura-era-ia-1/tree/v2-decoupled) (refatorada, atrás do gateway, mesmo comportamento) e a `main` (versão final).

## Diagnóstico da v1

Reproduzi as quatro dores pela borda (`localhost:8000`), com o provider simulado registrando tudo em `/admin/calls`. As causas apontam para o código da tag `v1-coupled`.

### 1. O relatório do mês não chega

```bash
curl -s -w '%{http_code} %{time_total}s\n' -X POST localhost:8000/reports/topics \
  -H "Content-Type: application/json" -d '{"start": "2026-08-01", "end": "2026-08-31"}'
```

- **Observado.** `504` em 29,8 s. Mas a aplicação não parou: o `/admin/calls` continuou recebendo chamadas `topics` por mais 5 min 20 s, até completar as 34, cerca de 10 s cada. Foram 222.114 tokens de entrada e 12.162 de saída no `claude-fake-large`, cerca de US$ 0,85 por um relatório que ninguém recebeu.
- **Causa.** `app/helpdesk/report.py:15-22` processa os 34 lotes em série, dentro da requisição. A rota é síncrona (`main.py:30-32`), a borda corta em 30 s sem nenhum byte (`edge/nginx.conf:21`) e nada cancela o trabalho quando o cliente desiste.

### 2. A sugestão deixa o atendente olhando para uma tela parada

```bash
curl -sN -o /dev/null -w 'primeiro byte %{time_starttransfer}s, total %{time_total}s\n' \
  -X POST localhost:8000/tickets/reply-suggestion -H "Content-Type: application/json" \
  -d '{"ticket_id": "TK-00042", "text": "Meu pedido #481516 não chegou e já passou do prazo, urgente"}'
```

- **Observado.** `200`, com o primeiro byte em 15,82 s, igual ao total. O `/admin/calls` mostra `stream: false`, com 606 tokens de saída em 15.957 ms.
- **Causa.** `app/helpdesk/llm.py:20-26` chama `messages.create` sem streaming, e `suggestion.py:6` e `main.py:20-22` só devolvem o JSON quando o texto inteiro chega.

### 3. Com um provider fora ou travado, parte do helpdesk para

```bash
curl -s -X POST localhost:8090/admin/failures -H "Content-Type: application/json" -d '{"provider": "anthropic", "mode": "error_500"}'
# depois, as quatro features pela borda
```

- **Anthropic em `error_500`.** F1 e F4 seguem com `200`; F2 e F3 respondem `500 Internal Server Error` em cerca de 1,3 s, cada uma com 3 chamadas no `/admin/calls` (o retry padrão do SDK). O `gpt-fake-large`, equivalente, estava no ar e nunca foi tentado.
- **OpenAI em `timeout`.** A F1 levou `504` da borda em 29,6 s. Pelo log da borda, foi uma única requisição, mas o `/admin/calls` registrou 3 chamadas `classify` (11:48:28, 11:53:24 e 11:58:21), cada uma presa por cerca de 300 s. A aplicação ficou ocupada por cerca de 15 minutos com uma resposta que o cliente já tinha perdido.
- **Causa.** `app/helpdesk/llm.py:8-9` cria os clientes sem timeout nem `max_retries` explícitos. Valem os padrões dos SDKs (`openai 3.19.0` e `anthropic 1.8.0`): 600 s de leitura e 2 retries. `config.py:9-13` amarra um provider por feature, e não existe fallback nem tratamento de erro: a exceção do SDK vira `500`.

### 4. Trocar o modelo exige mudar código e reconstruir

Troquei temporariamente `CLASSIFICATION_MODEL` para `gpt-fake-mini` em `app/helpdesk/config.py:10` e chamei a F1 depois de cada passo:

| passo | modelo no `/admin/calls` |
|---|---|
| só editar o arquivo | `gpt-fake-large` |
| `docker compose restart app` | `gpt-fake-large` |
| `docker compose up -d --build app` | `gpt-fake-mini` |

- **Causa.** O nome do modelo é uma constante no código (`config.py:10-13`), e `app/Dockerfile:6` copia o código para a imagem. Trocar de modelo é mudar código, reconstruir e reiniciar. A alteração foi desfeita antes da tag: `app/` na `v1-coupled` é idêntico ao do repositório base.

## Como rodar

Pré-requisitos: Docker com Compose v2 e [uv](https://docs.astral.sh/uv/) (para testes e métrica).

```bash
cp .env.example .env
docker compose up -d --build --wait
curl -s localhost:8000/health
```

A pilha sobe seis serviços: `provider-fake`, `edge`, `app`, `gateway` (LiteLLM), `gateway-db` (Postgres do gateway) e `gateway-init` (cria as chaves do gateway e termina com `Exited (0)`).

Testes e métrica:

```bash
uv sync

# caracterização: as quatro features pela borda, contra o golden master gravado na v1 (cerca de 90 s)
uv run pytest tests/characterization -q

# aceite: cada critério provocado pelo /admin/failures e conferido no /admin/calls (cerca de 4 min)
uv run pytest tests/acceptance -v

# unidade (features com fakes dos ports) e régua da métrica; não precisam da pilha
uv run pytest tests/unit tests/metrics -q

# contratos de dependência
PYTHONPATH=app uv run lint-imports

# métrica de qualquer checkout: CSV, gráfico A x I e grafo de dependências em metrics/results/
uv run python metrics/coupling.py app/helpdesk --name main
git worktree add ../v1 v1-coupled && uv run python metrics/coupling.py ../v1/app/helpdesk --name v1-coupled

# comparativo entre versões (metrics/results/comparison.md e comparison.png)
uv run python metrics/compare.py v1-coupled v2-decoupled main
```

Nas tags `v1-coupled` e `v2-decoupled`, a suíte de caracterização é idêntica e roda com o mesmo comando. Na `main`, os testes da F2 consomem o stream e os da F3 acompanham o status, e os dois comparam o conteúdo final com o mesmo golden master da v1.

## Métrica

Componente é cada módulo `.py` de `app/helpdesk/`, pela régua do requisito 3, aplicada por `metrics/coupling.py` e conferida em `tests/metrics/` contra um pacote com valores calculados à mão. Resultados em `metrics/results/`: `v1-coupled`, `v2-decoupled` e `main`, cada um com CSV, gráfico A × I e grafo de dependências. A comparação está em `comparison.md`.

| componente | v1-coupled (Ca / Ce / I / A / D) | v2-decoupled | main |
|---|---|---|---|
| `llm` | 4 / 1 / 0,20 / 0,00 / 0,80 **dor** | — | — |
| `config` | 6 / 0 / 0,00 / 0,00 / 1,00 **dor** | 1 / 0 / 0,00 / 0,00 / 1,00 exceção | 1 / 0 / 0,00 / 0,00 / 1,00 exceção |
| `schemas` | 5 / 0 / 0,00 / 0,00 / 1,00 **dor** | 5 / 0 / 0,00 / 0,00 / 1,00 exceção | 5 / 0 / 0,00 / 0,00 / 1,00 exceção |
| `ports` | — | 6 / 0 / 0,00 / 1,00 / 0,00 | 8 / 0 / 0,00 / 0,67 / 0,33 |
| `adapters.gateway` | — | 1 / 1 / 0,50 / 0,00 / 0,50 | 1 / 1 / 0,50 / 0,00 / 0,50 |
| `adapters.tickets_file` | — | 1 / 1 / 0,50 / 0,00 / 0,50 | 1 / 1 / 0,50 / 0,00 / 0,50 |
| `adapters.jobs` | — | — | 1 / 1 / 0,50 / 0,00 / 0,50 |
| features (`classification`, `extraction`, `suggestion`, `report`) | Ca 1, Ce 3 ou 4, I de 0,75 a 0,80 | Ca 1, Ce 2, I 0,67 | Ca 1, Ce 2, I 0,67 |
| `main` | 0 / 5 / 1,00 / 0,00 / 0,00 | 0 / 8 / 1,00 / 0,00 / 0,00 | 0 / 10 / 1,00 / 0,00 / 0,00 |

Leitura dos três gráficos:

- **v1.** Tudo aponta para dois concretos: `config` (6 dependentes, com chave, URL e modelo físico) e `llm` (4 dependentes, com os dois SDKs). É exatamente por eles que passam as dores 3 e 4. O `schemas` também está na zona, mas por outro motivo: é tipo de valor.
- **v2.** O `llm` saiu. No lugar dele nasceu uma abstração, `ports.LanguageModel`, sobre a Main Sequence (A = 1, I = 0), e um adapter concreto que só o `main` conhece. As features passaram a receber tudo por construtor. O `config` caiu de 6 dependentes para 1, mas continua na zona, porque um concreto com um único dependente e nenhuma dependência de saída dá I = 0 pela fórmula. O plano previu "Ca = 1" e não previu isso; está na revisão 4 de [`docs/refactoring-plan.md`](docs/refactoring-plan.md).
- **main.** A estrutura não mudou. Entrou `adapters.jobs` (tarefas da F3), e `ports` ganhou a exceção `ModelUnavailable`, que faz parte do contrato do port. Por isso o A do `ports` foi para 0,67.

Exceções declaradas como estáveis por natureza no [ADR 0005](docs/adr/0005-ler-a-metrica-com-excecoes-declaradas-e-guardadas.md): `schemas` (tipos de valor do contrato HTTP) e `config` (sobraram só nomes lógicos e dados de composição, lidos só pelo `main`). As duas exceções e a margem dos adapters, que estão na fronteira com I = 0,50, são guardadas por contratos do import-linter (`.importlinter`). Um import descuidado quebra o `lint-imports` antes de quebrar a métrica.

**O componente que chama o gateway é `app/helpdesk/adapters/gateway.py`.** É o único arquivo da aplicação que importa um SDK, e só o ponto de composição (`app/helpdesk/main.py`) depende dele. Nenhuma feature o importa (contrato `adapters-so-no-main`).

## Tabela de capacidades

A aplicação conhece só as quatro capacidades (`app/helpdesk/config.py`). Destinos e políticas estão em [`gateway/config.yaml`](gateway/config.yaml).

| capacidade | feature | primário | fallback técnico | modelo fraco | tentativas por destino (primário / equivalente / fraco) | timeout por tentativa |
|---|---|---|---|---|---|---|
| `ticket-classifier` | F1 | `openai/gpt-fake-large` | `anthropic/claude-fake-large` | `openai/gpt-fake-mini` | 2 / 2 / 1 | 4 s |
| `reply-writer` | F2 | `anthropic/claude-fake-large` | `openai/gpt-fake-large` | `anthropic/claude-fake-mini` | 2 / 2 / 1 | 2 s até o 1º trecho |
| `topic-analyst` | F3 | `anthropic/claude-fake-large` | `openai/gpt-fake-large` | `anthropic/claude-fake-mini` | 2 / 2 / 1 (por lote) | 20 s por lote |
| `order-extractor` | F4 | `openai/gpt-fake-large` | `anthropic/claude-fake-large` | não usa | 2 / 2 / — | 4 s |

As duas tentativas por destino valem para erro transitório (`500` e `429`: 1 retry com backoff). Timeout não tem retry: uma tentativa travada passa direto para o próximo destino. A aplicação não repete chamadas (`max_retries=0`). Os detalhes estão no [ADR 0007](docs/adr/0007-aplicar-resiliencia-e-fallback-por-capacidade.md).

## Tabela de fallback

O que acontece quando nenhum modelo `large` está disponível (por exemplo, `gpt-fake-large` e `claude-fake-large` em `error_500`):

| feature | resposta | status | por quê |
|---|---|---|---|
| F1 Classificar | classificação pelo `gpt-fake-mini` | `200` | o mini acertou 300 de 300 |
| F2 Sugerir | stream pelo `claude-fake-mini`, com texto mais curto | `200` (`text/event-stream`) | o atendente revisa; um texto mais curto ainda ajuda |
| F3 Relatório | relatório pelo `claude-fake-mini` | `202`, depois `303` e `200` | resultado idêntico no lote testado |
| F4 Extrair | `{"detail": "Nenhum modelo disponível para order-extractor no momento"}` | `503` | o mini errou 45 de 300 pedidos, e a F4 dispara troca sem revisão humana |

Se nem o fraco responde, F1 e F2 respondem `503` (a F2 ainda antes de abrir o stream), e a tarefa da F3 vai para `failed`, com o motivo, em segundos.

## Fluxos

### F1 Classificar ticket: síncrono

```bash
curl -s -X POST localhost:8000/tickets/classification -H "Content-Type: application/json" \
  -d '{"ticket_id": "TK-00042", "text": "Meu pedido #481516 não chegou e já passou do prazo, urgente"}'
# 200 {"ticket_id":"TK-00042","category":"delivery","priority":"high"}  (cerca de 1,1 s)
```

### F2 Sugerir resposta: streaming (SSE)

```bash
curl -sN -X POST localhost:8000/tickets/reply-suggestion -H "Content-Type: application/json" \
  -d '{"ticket_id": "TK-00042", "text": "Meu pedido #481516 não chegou e já passou do prazo, urgente"}'
# 200, Content-Type: text/event-stream
# data: {"chunk": "Olá!"}            <- cerca de 0,8 s
# data: {"chunk": " Sin"}
# ...
# event: end
# data: {"ticket_id": "TK-00042"}
```

Erro no meio do stream (o `200` já foi enviado): `event: error` e `data: {"ticket_id": "TK-00042", "message": "A geração foi interrompida"}`, e o stream termina. Se nenhum modelo atende antes do primeiro trecho, a resposta é `503` em JSON.

### F3 Relatório de temas: assíncrono (Asynchronous Request-Reply)

```bash
curl -si -X POST localhost:8000/reports/topics -H "Content-Type: application/json" \
  -d '{"start": "2026-08-01", "end": "2026-08-31"}'
# 202 Accepted (cerca de 13 ms)
# Location: /reports/topics/status/<id>
# Retry-After: 5

curl -si localhost:8000/reports/topics/status/<id>
# 200 {"state":"running","progress":"1800/5000","reason":null}   (pending, running ou failed, com o motivo)
# 303 See Other, Location: /reports/topics/<id>                  (quando termina)

curl -s localhost:8000/reports/topics/<id>
# 200 {"start":"2026-08-01","end":"2026-08-31","total_tickets":5000,"topics":[...]}
```

O mês fica pronto em cerca de 90 s. Cada relatório roda até 4 lotes em paralelo, e até 2 relatórios ao mesmo tempo; os demais esperam como `pending`. Período invertido ou data inválida respondem `422` na hora, sem criar tarefa.

### F4 Extrair dados do pedido: síncrono

```bash
curl -s -X POST localhost:8000/tickets/extraction -H "Content-Type: application/json" \
  -d '{"ticket_id": "TK-00002", "text": "Tenho aqui a nota fiscal 530720. O produto veio quebrado na caixa, pedido #605065."}'
# 200 {"ticket_id":"TK-00002","order_number":"#605065","product":null}
```

## Troca de modelo

Arquivo: [`gateway/config.yaml`](gateway/config.yaml). O que muda: o `<<:` do destino da capacidade, que aponta para um dos quatro modelos declarados no topo do arquivo (`*openai-large`, `*openai-mini`, `*anthropic-large`, `*anthropic-mini`). Exemplo para a F1 passar a usar o `gpt-fake-mini`:

```yaml
  - model_name: ticket-classifier
    litellm_params: {<<: *openai-mini, timeout: 4}     # antes: *openai-large
```

Comando, reiniciando só o gateway:

```bash
docker compose restart gateway && docker compose up -d --wait gateway
curl -s -X POST localhost:8000/tickets/classification -H "Content-Type: application/json" \
  -d '{"ticket_id": "TK-00042", "text": "Meu pedido #481516 não chegou"}'
curl -s "localhost:8090/admin/calls?last=1"     # "model": "gpt-fake-mini"
```

A aplicação não é reconstruída nem reiniciada: `docker inspect -f '{{.State.StartedAt}}' $(docker compose ps -q app)` mostra o mesmo horário antes e depois.

## Roteiro de governança

As chaves estão em [`gateway/keys.yaml`](gateway/keys.yaml) e são criadas pelo `gateway-init` na subida. A da aplicação tem a política real: US$ 100 por 30 dias e 600 req/min. Duas chaves de roteiro aplicam a mesma política em escala mínima, para mostrar a recusa sem mexer na aplicação. Os valores em US$ são custo calculado com os preços do provider simulado ([ADR 0008](docs/adr/0008-governar-chaves-orcamentos-e-limites-no-gateway.md)).

```bash
set -a; . ./.env; set +a
chamar() { curl -s -w '  [%{http_code}]\n' localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $1" -H "Content-Type: application/json" \
  -d '{"model": "ticket-classifier", "messages": [{"role": "user", "content": "TASK: classify\nFui cobrado duas vezes"}]}'; }
contar() { curl -s "localhost:8090/admin/calls?last=500" | python3 -c "import json,sys; print('chamadas no provider:', len(json.load(sys.stdin)))"; }

curl -s -o /dev/null -X POST localhost:8090/admin/reset

# Orçamento: a 1ª chamada da chave custa cerca de US$ 0,00012 e estoura o teto de US$ 0,0001
chamar "$ROTEIRO_ORCAMENTO_KEY"; contar   # 200 e o contador sobe 1 (ou 429, se a chave já estourou antes)
chamar "$ROTEIRO_ORCAMENTO_KEY"; contar   # 429 "Budget has been exceeded!" e o contador não muda

# Limite de requisições: 2 por minuto
chamar "$ROTEIRO_RPM_KEY"; chamar "$ROTEIRO_RPM_KEY"; contar    # 200, 200 e o contador sobe 2
chamar "$ROTEIRO_RPM_KEY"; contar                                # 429 "Rate limit exceeded" e o contador não muda
```

O gasto fica no banco do gateway (volume `gateway-db-data`). Depois da primeira execução, a chave de orçamento continua estourada, e a primeira chamada do roteiro já volta `429`. Para zerar: `docker compose down -v`. Para o limite de requisições, espere um minuto entre execuções.

## Mapa de decisões

| ADR | nível | resumo |
|---|---|---|
| [0001](docs/adr/0001-colocar-um-ai-gateway-self-hosted-entre-a-app-e-os-providers.md) | solução | LiteLLM Proxy self-hosted como única saída para os providers |
| [0002](docs/adr/0002-expor-uma-capacidade-logica-por-feature.md) | software | uma capacidade lógica por feature; o modelo físico mora no gateway |
| [0003](docs/adr/0003-usar-postgres-dedicado-para-o-estado-do-gateway.md) | solução | Postgres dedicado para virtual keys, orçamento e gasto |
| [0004](docs/adr/0004-criar-as-virtual-keys-na-subida-sem-passo-manual.md) | software | `gateway-init` cria as chaves de forma idempotente, sem passo manual |
| [0005](docs/adr/0005-ler-a-metrica-com-excecoes-declaradas-e-guardadas.md) | software | `schemas` e `config` estáveis por natureza, guardados por contrato |
| [0006](docs/adr/0006-decidir-o-modo-de-execucao-de-cada-feature.md) | solução | F1 e F4 síncronas, F2 em streaming, F3 assíncrona, uma seção por feature |
| [0007](docs/adr/0007-aplicar-resiliencia-e-fallback-por-capacidade.md) | solução | timeout, retry e fallback no gateway; modelo fraco em F1, F2 e F3, nunca na F4 |
| [0008](docs/adr/0008-governar-chaves-orcamentos-e-limites-no-gateway.md) | solução | orçamento e limite por virtual key, com chaves de roteiro |
| [0009](docs/adr/0009-limitar-o-gasto-mensal-com-ia-do-helpdesk.md) | corporativa | teto de US$ 100 por mês com IA no helpdesk |
| [0010](docs/adr/0010-fazer-o-dado-de-cliente-sair-so-pelo-gateway.md) | corporativa | dado de cliente sai da empresa só pelo gateway |

O plano de refatoração, com o piloto, as quatro revisões e o handoff para o agente de IA, está em [`docs/refactoring-plan.md`](docs/refactoring-plan.md).

## Observação final: revisão em par

Cada marco deste desafio passou por uma revisão em par antes de virar tag. Um agente constrói, outro agente, de outro modelo, audita com evidência, e eu decido no portão. Quem constrói não dá veredito sobre o próprio trabalho. Para isso usei o meu projeto [agent-revisor](https://github.com/ElderGil/agent-revisor), que dá turno, papel e registro de cada rodada. As decisões ficam numa memória compartilhada entre os agentes.
