import os

# A aplicação só conhece o gateway e a própria chave dele (virtual key).
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:4000")
GATEWAY_API_KEY = os.environ["GATEWAY_API_KEY"]
GATEWAY_TIMEOUT_SECONDS = 600

# Capacidades lógicas. Qual modelo atende cada uma está em gateway/config.yaml.
CLASSIFICATION_CAPABILITY = "ticket-classifier"
EXTRACTION_CAPABILITY = "order-extractor"
SUGGESTION_CAPABILITY = "reply-writer"
REPORT_CAPABILITY = "topic-analyst"

MAX_OUTPUT_TOKENS = 2000

TICKETS_FILE = "/data/tickets.jsonl"
TICKETS_PER_CALL = 150
