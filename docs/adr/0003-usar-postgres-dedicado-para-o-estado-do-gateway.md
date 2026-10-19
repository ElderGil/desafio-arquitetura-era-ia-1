# 0003. Usar um Postgres dedicado para o estado do gateway

- Status: aceita
- Data: 2026-10-19
- Nível: solução

## Contexto

O requisito 5 pede pelo menos uma chave com orçamento e uma com limite de requisições, com a requisição fora do limite recusada antes de chegar ao provider. No LiteLLM, virtual keys, orçamento e gasto acumulado por chave só existem com um banco Postgres (`DATABASE_URL`). Sem banco, o proxy aceita apenas a master key e não guarda gasto. O enunciado exige um ADR para cada serviço novo no compose além de `app` e `gateway`.

## Opções consideradas

1. Postgres dedicado ao gateway (`gateway-db`), só na rede interna do compose.
2. Sem banco: só a master key, e orçamento e limite implementados na aplicação.
3. Postgres compartilhado com a aplicação.

## Decisão

Opção 1, com a imagem `postgres:16-alpine` e healthcheck por `pg_isready`. O gateway só sobe depois do banco saudável.

A opção 2 obrigaria a aplicação a contar tokens e custo, exatamente a responsabilidade que o gateway veio centralizar. A opção 3 não existe na prática, porque a aplicação não tem banco, e mesmo que tivesse misturaria o estado de governança com o estado do negócio.

## Consequências

- Mais um serviço para subir. Ele não expõe porta para o host.
- O gasto por chave fica no volume do container: `docker compose down` sem `-v` preserva o gasto entre subidas, e `down -v` zera tudo. Isso importa para o roteiro de governança do README.
- A senha do banco vem de `GATEWAY_DB_PASSWORD` no `.env` e não é segredo real fora deste compose.

## Evidência

- `docker compose ps gateway-db` mostra o serviço `healthy`.
- `curl -s "localhost:4000/key/info?key=$HELPDESK_GATEWAY_KEY" -H "Authorization: Bearer $LITELLM_MASTER_KEY"` devolve a chave com o campo `spend`, que cresce a cada chamada.
