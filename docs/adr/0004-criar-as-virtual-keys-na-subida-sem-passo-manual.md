# 0004. Criar as virtual keys na subida, sem passo manual

- Status: aceita
- Data: 2026-10-19
- Nível: software

## Contexto

A aplicação precisa de uma chave do próprio gateway (virtual key), e o roteiro de governança precisa de chaves com orçamento e com limite de requisições. No LiteLLM, essas chaves nascem por chamada à API administrativa (`/key/generate`), não pelo arquivo de configuração. O enunciado exige que `cp .env.example .env && docker compose up -d --build --wait` suba tudo sem passo manual. O enunciado também exige um ADR para cada serviço novo no compose.

## Opções consideradas

1. Um serviço `gateway-init` que roda uma vez, cria as chaves e termina; a aplicação só sobe depois dele terminar com sucesso.
2. Criar as chaves dentro da própria aplicação, na inicialização.
3. Documentar um `curl` no README para criar as chaves.

## Decisão

Opção 1. O `gateway-init` usa a mesma imagem do gateway (que já tem Python e PyYAML), lê `gateway/keys.yaml` e aplica cada chave. A chave é criada com `/key/generate` se ainda não existir, ou tem modelos e limites reaplicados com `/key/update` se já existir, preservando o gasto acumulado. O valor de cada chave vem de uma variável do `.env` (`key_env`), então a aplicação sabe de antemão qual chave usar.

A opção 2 daria à aplicação a master key do gateway, uma credencial administrativa que ela não deve ter. A opção 3 é o passo manual que o enunciado proíbe.

## Consequências

- Chaves, modelos permitidos, orçamentos e limites ficam versionados em `gateway/keys.yaml`, ao lado da configuração das capacidades.
- A subida ganha um serviço que termina (`exited (0)`). Isso é esperado. Se ele falhar, a aplicação não sobe e o motivo aparece em `docker compose logs gateway-init`.
- Rodar a subida de novo é seguro: o init é idempotente.

## Evidência

- `docker compose logs gateway-init` mostra `chave helpdesk-app criada` na primeira subida e `atualizada` nas seguintes.
- `docker compose ps -a gateway-init` mostra `Exited (0)`.
