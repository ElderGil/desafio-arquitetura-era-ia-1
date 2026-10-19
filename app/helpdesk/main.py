from fastapi import FastAPI

from . import classification, config, extraction, report, suggestion
from .adapters.gateway import GatewayLanguageModel
from .schemas import (Classification, OrderData, PeriodInput, ReplySuggestion, TicketInput,
                      TopicsReport)

app = FastAPI(title="Helpdesk")

# Ponto de composição: o único lugar que conhece a implementação concreta do modelo.
model = GatewayLanguageModel(
    base_url=config.GATEWAY_URL,
    api_key=config.GATEWAY_API_KEY,
    timeout=config.GATEWAY_TIMEOUT_SECONDS,
    max_output_tokens=config.MAX_OUTPUT_TOKENS,
)
classifier = classification.Classifier(model, config.CLASSIFICATION_CAPABILITY)
suggester = suggestion.ReplySuggester(model, config.SUGGESTION_CAPABILITY)
extractor = extraction.OrderExtractor(model, config.EXTRACTION_CAPABILITY)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tickets/classification")
def classify_ticket(ticket: TicketInput) -> Classification:
    return classifier.classify(ticket)


@app.post("/tickets/reply-suggestion")
def suggest_reply(ticket: TicketInput) -> ReplySuggestion:
    return suggester.suggest(ticket)


@app.post("/tickets/extraction")
def extract_order_data(ticket: TicketInput) -> OrderData:
    return extractor.extract(ticket)


@app.post("/reports/topics")
def topics_report(period: PeriodInput) -> TopicsReport:
    return report.topics(period, model)
