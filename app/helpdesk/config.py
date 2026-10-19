import os

# A aplicação só conhece o gateway e a própria chave dele (virtual key).
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:4000")
GATEWAY_API_KEY = os.environ["GATEWAY_API_KEY"]

# Capacidades lógicas. Qual modelo atende cada uma está em gateway/config.yaml.
CLASSIFICATION_CAPABILITY = "ticket-classifier"
EXTRACTION_CAPABILITY = "order-extractor"
SUGGESTION_CAPABILITY = "reply-writer"
REPORT_CAPABILITY = "topic-analyst"

# Timeout da aplicação por chamada ao gateway: rede de segurança acima do pior caso
# do próprio gateway (timeout por tentativa x destinos, em gateway/config.yaml).
#   F1 e F4: 4 s x até 3 destinos = 12 s  -> 13 s, abaixo dos 15 s exigidos
#   F2: 2 s até o 1º trecho x 3 destinos = 6 s; o valor vale entre trechos -> 15 s
#   F3: por lote; corta antes do 3º destino para a tarefa falhar bem antes de 60 s
GATEWAY_TIMEOUTS = {
    CLASSIFICATION_CAPABILITY: 13,
    EXTRACTION_CAPABILITY: 13,
    SUGGESTION_CAPABILITY: 15,
    REPORT_CAPABILITY: 45,
}

MAX_OUTPUT_TOKENS = 2000

TICKETS_FILE = "/data/tickets.jsonl"
TICKETS_PER_CALL = 150

# Relatório assíncrono (F3).
REPORT_PARALLEL_BATCHES = 4    # lotes simultâneos por relatório
REPORT_MAX_RUNNING = 2         # relatórios simultâneos (teto: 2 x 4 = 8 chamadas); os demais esperam como pending
REPORT_STALL_SECONDS = 50      # running sem progresso vira failed
REPORT_RETRY_AFTER_SECONDS = 5
