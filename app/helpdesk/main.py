from fastapi import FastAPI

from . import classification, config, extraction, report, suggestion
from .adapters.gateway import GatewayLanguageModel
from .adapters.tickets_file import TicketFile
from .schemas import (Classification, OrderData, PeriodInput, ReplySuggestion, TicketInput,
                      TopicsReport)

app = FastAPI(title="Helpdesk")

# Ponto de composição: o único lugar que conhece as implementações concretas e a configuração.
model = GatewayLanguageModel(
    base_url=config.GATEWAY_URL,
    api_key=config.GATEWAY_API_KEY,
    timeout=config.GATEWAY_TIMEOUT_SECONDS,
    max_output_tokens=config.MAX_OUTPUT_TOKENS,
)
tickets = TicketFile(config.TICKETS_FILE)

classifier = classification.Classifier(model, config.CLASSIFICATION_CAPABILITY)
extractor = extraction.OrderExtractor(model, config.EXTRACTION_CAPABILITY)
suggester = suggestion.ReplySuggester(model, config.SUGGESTION_CAPABILITY)
reporter = report.TopicsReporter(model, config.REPORT_CAPABILITY, tickets, config.TICKETS_PER_CALL)


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
    return reporter.topics(period)
