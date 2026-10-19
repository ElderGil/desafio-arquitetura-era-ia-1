# 0010. Fazer o dado de cliente sair da empresa só pelo gateway

- Status: aceita
- Data: 2026-10-19
- Nível: corporativa

## Contexto

Os tickets carregam dado de cliente: número de pedido, nota fiscal, produto, cidade ("Moro em Campinas, caso ajude") e o relato do problema. Toda chamada a um modelo envia esse texto para um provider externo. Na v1, cada feature chamava o provider direto, com a chave na configuração da aplicação: não havia um ponto único para saber o que saiu, para onde e por qual chave, nem para cortar o acesso de uma aplicação sem trocar a chave do provider de todas.

Com a IA espalhada por mais sistemas, a pergunta "quem mandou dado de cliente para fora, e para qual provider?" precisa ter uma resposta só.

## Opções consideradas

1. Toda chamada a modelo de qualquer sistema da empresa passa pelo AI Gateway, e só o gateway tem as credenciais dos providers.
2. Cada sistema chama o provider direto, com regras de uso em documento.
3. Uma lista de providers aprovados, com chamada direta permitida.

## Decisão

Opção 1. O gateway é a única saída de dado de cliente para modelos, e nenhuma aplicação recebe credencial de provider. As opções 2 e 3 dependem de cada time seguir a regra, e a v1 é a prova de como isso termina.

## Consequências

- No helpdesk, a regra é verificável: a aplicação não tem as chaves (`docker compose exec app env`), não importa SDK de provider (contrato `features-sem-detalhes` em `.importlinter`) e só conhece o endereço do gateway.
- Trocar ou incluir um provider passa a ser decisão de quem opera o gateway, e o novo provider herda as mesmas chaves, orçamentos e limites.
- O gateway vira ponto crítico de disponibilidade e de segurança: se ele cai, a IA de toda a empresa cai junto, e as chaves de todos os providers ficam num lugar só, que precisa de mais proteção.
- Auditar o conteúdo enviado (logs de prompt, mascaramento de dado pessoal) é o passo seguinte que essa decisão habilita. Segurança e guardrails estão fora do escopo deste trabalho.

## Evidência

- `docker compose config`: o serviço `app` recebe só `GATEWAY_URL` e `GATEWAY_API_KEY`; `FAKE_OPENAI_KEY` e `FAKE_ANTHROPIC_KEY` aparecem só no serviço `gateway`.
- `grep -rE "FAKE_OPENAI_KEY|FAKE_ANTHROPIC_KEY|sk-fake-openai|sk-ant-fake" app/` não retorna nada.
- `PYTHONPATH=app uv run lint-imports`: o contrato `features-sem-detalhes` proíbe `openai` e `anthropic` nas features. O único arquivo que importa um SDK é o adapter do gateway, que fala com o gateway, não com o provider.
