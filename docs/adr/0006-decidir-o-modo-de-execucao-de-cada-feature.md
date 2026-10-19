# 0006. Decidir o modo de execução de cada feature

- Status: aceita
- Data: 2026-10-19
- Nível: solução

## Contexto

Na v1, as quatro features respondem de forma síncrona, com o resultado no corpo. A borda (`edge/nginx.conf`) encerra com `504` qualquer requisição que passe 30 s sem enviar um byte. O diagnóstico mostrou duas dores que nascem daí:

- o relatório do mês dá `504` em 29,8 s, e a aplicação continua trabalhando por mais 5 min 20 s, sem ninguém para receber;
- a sugestão de resposta leva 15,8 s até o primeiro byte, igual ao tempo total, com o atendente olhando uma tela parada.

A pergunta não é qual modo adotar. É qual modo para cada caso de uso, a partir do contrato de cada feature. Usamos três perguntas da árvore de decisão:

1. Alguém está esperando agora?
2. Cabe no orçamento de latência?
3. O resultado é consumível aos poucos?

## Opções consideradas

Para cada feature: síncrono, streaming (SSE) ou Asynchronous Request-Reply (202 + status + 303).

## Decisão

### F1 Classificar ticket: síncrono

- Alguém está esperando? Sim: o cliente espera a confirmação na tela, na abertura do ticket.
- Cabe no orçamento? Sim: saída curta (cerca de 11 tokens), cerca de 1,1 s no modelo `large`. O requisito pede o resultado completo em até 3 s.
- Consumível aos poucos? Não: `category` e `priority` são valores fixos, e um JSON pela metade não serve para nada.

Síncrono, com timeout explícito: 4 s por tentativa no gateway e 13 s na aplicação, acima do pior caso do gateway (3 destinos de 4 s) e abaixo dos 15 s exigidos.

### F2 Sugerir resposta: streaming (SSE)

- Alguém está esperando? Sim: o atendente está olhando a tela.
- Cabe no orçamento? Não inteira: cerca de 600 tokens a 40 tokens/s dão cerca de 16 s.
- Consumível aos poucos? Sim: o atendente começa a ler e editar assim que o texto aparece.

Streaming muda a espera percebida: o primeiro trecho chega em cerca de 0,8 s, e o resto continua chegando. A conexão continua aberta, mas nunca passa 30 s sem bytes. Detalhes do contrato:

- `Content-Type: text/event-stream`, com eventos `data: {"chunk": ...}` e, no fim, `event: end`;
- o primeiro trecho é lido antes de responder, e se nenhum modelo atender, ainda dá para devolver `503` em vez de um `200` vazio;
- um erro depois do primeiro trecho (o status `200` já foi enviado) chega como `event: error` dentro do próprio stream, no formato do enunciado;
- o header `X-Accel-Buffering: no` impede a borda (nginx) de acumular a resposta. Esse header é a forma de desligar o buffer sem alterar `edge/`, que é proibido.

### F3 Relatório de temas: assíncrono (Asynchronous Request-Reply)

- Alguém está esperando? Não: quem pede é um painel interno, e ninguém fica olhando para ele.
- Cabe no orçamento? Não: 5.000 tickets em 34 lotes passam de 5 minutos em série. Nenhum timeout de proxy aceita isso.
- Consumível aos poucos? Não: o relatório só faz sentido somado.

Streaming resolveria a borda "por acidente" (os bytes mantêm a conexão viva), mas prenderia uma conexão por minutos sem ninguém lendo. O painel também não expõe callback. Por isso:

- `POST /reports/topics` valida o período (`422` na hora, se for inválido) e responde `202 Accepted` com `Location: /reports/topics/status/{id}` e `Retry-After: 5`, em cerca de 13 ms;
- a URL de status responde `200` com `state` (`pending`, `running` ou `failed`, este com `reason`) e `progress` (por exemplo `1800/5000`); quando a tarefa chega a `done`, responde `303 See Other` para `/reports/topics/{id}`.

Onde a tarefa roda:

- dentro da própria aplicação, num pool limitado: no máximo 2 relatórios simultâneos, e os demais esperam como `pending`;
- cada relatório roda até 4 lotes em paralelo. O mês cai de cerca de 5 min 30 s para cerca de 90 s, com o mesmo custo e a mesma ordem de soma. O teto é de 8 chamadas simultâneas, bem dentro do limite de 600 rpm da chave da aplicação.

Não subimos fila nem worker: o requisito não cobra sobreviver a reinício, e cada serviço novo exigiria um ADR próprio sem requisito por trás. Uma tarefa nunca fica presa em `running`:

- a falha de um lote marca a tarefa como `failed` com o motivo e cancela os lotes que ainda não começaram;
- uma tarefa sem progresso por 50 s também vira `failed`, e o trabalho em andamento para no próximo ponto de progresso.

### F4 Extrair dados do pedido: síncrono

- Alguém está esperando? Sim: é uma automação de troca e devolução que consome o resultado na hora.
- Cabe no orçamento? Sim: saída curta, cerca de 1,1 s.
- Consumível aos poucos? Não: `order_number` e `product` só valem completos e validados.

Síncrono, com os mesmos timeouts da F1. A diferença está no fallback ([0007](0007-aplicar-resiliencia-e-fallback-por-capacidade.md)): sem modelo `large`, a F4 falha com `503` em vez de responder com o modelo fraco.

## Consequências

- A F2 mudou o contrato: quem consumia JSON passa a consumir SSE. A F3 também mudou: quem esperava o relatório no corpo passa a acompanhar uma URL de status. As duas mudanças são deliberadas e entram só depois da tag `v2-decoupled`. Os testes de caracterização da `main` consomem os contratos novos e comparam o conteúdo final com o mesmo golden master da v1.
- As tarefas da F3 vivem na memória da aplicação: reiniciá-la perde os relatórios em andamento, e o painel precisa pedir de novo.
- O gateway continua gerando o relatório até o fim mesmo se ninguém buscar o resultado. Desistir do lado da aplicação (falha ou travamento) cancela os lotes que ainda não começaram.

## Evidência

- `uv run pytest tests/acceptance -v` cobre os quatro modos:
  - F1 completa em até 3 s;
  - na F2, o primeiro trecho chega em até 1,5 s e antes da metade do tempo total, e o `midstream_error` vira `event: error`;
  - a F3 aceita o mês em até 1 s, entrega `total_tickets = 5000` com 34 chamadas `topics`, e com os dois providers fora chega a `failed` com motivo em até 60 s;
  - nenhum dos cenários produz `504`.
- Os `curl` de cada fluxo estão na seção "Fluxos" do README.
