import json
from collections.abc import Iterator

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from . import classification, config, extraction, report, suggestion
from .adapters.gateway import GatewayLanguageModel
from .adapters.jobs import InMemoryJobs
from .adapters.tickets_file import TicketFile
from .ports import ModelUnavailable
from .schemas import Classification, OrderData, PeriodInput, ReportStatus, TicketInput, TopicsReport

app = FastAPI(title="Helpdesk")

# Ponto de composição: o único lugar que conhece as implementações concretas e a configuração.
model = GatewayLanguageModel(
    base_url=config.GATEWAY_URL,
    api_key=config.GATEWAY_API_KEY,
    timeouts=config.GATEWAY_TIMEOUTS,
    max_output_tokens=config.MAX_OUTPUT_TOKENS,
)
tickets = TicketFile(config.TICKETS_FILE)
jobs = InMemoryJobs(max_running=config.REPORT_MAX_RUNNING, stall_seconds=config.REPORT_STALL_SECONDS)

classifier = classification.Classifier(model, config.CLASSIFICATION_CAPABILITY)
extractor = extraction.OrderExtractor(model, config.EXTRACTION_CAPABILITY)
suggester = suggestion.ReplySuggester(model, config.SUGGESTION_CAPABILITY)
reporter = report.TopicsReporter(model, config.REPORT_CAPABILITY, tickets, config.TICKETS_PER_CALL,
                                 config.REPORT_PARALLEL_BATCHES)


@app.exception_handler(ModelUnavailable)
def model_unavailable(request: Request, error: ModelUnavailable) -> JSONResponse:
    # O gateway já esgotou retry e fallback permitidos para a capacidade (docs/adr).
    return JSONResponse(status_code=503, content={
        "detail": f"Nenhum modelo disponível para {error.capability} no momento"})


@app.get("/health")
def health():
    return {"status": "ok"}


# F1: síncrona. Saída curta e de valores fixos, com o cliente esperando a confirmação.
@app.post("/tickets/classification")
def classify_ticket(ticket: TicketInput) -> Classification:
    return classifier.classify(ticket)


# F2: streaming (SSE). O atendente começa a ler assim que o primeiro trecho chega.
@app.post("/tickets/reply-suggestion")
def suggest_reply(ticket: TicketInput):
    chunks = suggester.stream(ticket)
    # Lê o primeiro trecho antes de responder: se nenhum modelo atender, ainda dá
    # para devolver 503 em vez de um 200 vazio.
    first = next(chunks, None)

    def events() -> Iterator[str]:
        try:
            if first is not None:
                yield _sse({"chunk": first})
            for chunk in chunks:
                yield _sse({"chunk": chunk})
        except ModelUnavailable:
            yield _sse({"ticket_id": ticket.ticket_id, "message": "A geração foi interrompida"}, event="error")
            return
        yield _sse({"ticket_id": ticket.ticket_id}, event="end")

    # X-Accel-Buffering: a borda (nginx) não acumula a resposta antes de repassar.
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(data: dict, event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data, ensure_ascii=False)}\n\n"


# F4: síncrona. Alimenta uma automação sem revisão humana; sem modelo large, falha
# explicitamente (503) em vez de responder com o modelo fraco (docs/adr).
@app.post("/tickets/extraction")
def extract_order_data(ticket: TicketInput) -> OrderData:
    return extractor.extract(ticket)


# F3: assíncrona (Asynchronous Request-Reply). Ninguém espera olhando; o mês inteiro
# não cabe no orçamento de latência da borda.
@app.post("/reports/topics", status_code=202)
def request_topics_report(period: PeriodInput, response: Response) -> ReportStatus:
    reporter.validate(period)
    job_id = jobs.submit(lambda progress: reporter.topics(period, progress))
    response.headers["Location"] = f"/reports/topics/status/{job_id}"
    response.headers["Retry-After"] = str(config.REPORT_RETRY_AFTER_SECONDS)
    return ReportStatus(state="pending")


@app.get("/reports/topics/status/{job_id}", response_model=None)
def topics_report_status(job_id: str, response: Response) -> ReportStatus | RedirectResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    if job.state == "done":
        return RedirectResponse(f"/reports/topics/{job_id}", status_code=303)
    if job.state != "failed":
        response.headers["Retry-After"] = str(config.REPORT_RETRY_AFTER_SECONDS)
    progress = f"{job.done}/{job.total}" if job.total is not None else None
    return ReportStatus(state=job.state, progress=progress, reason=job.reason)


@app.get("/reports/topics/{job_id}")
def topics_report_result(job_id: str) -> TopicsReport:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    if job.state != "done":
        raise HTTPException(status_code=409, detail=f"Relatório ainda não está pronto (estado: {job.state})")
    return TopicsReport.model_validate(job.result)
