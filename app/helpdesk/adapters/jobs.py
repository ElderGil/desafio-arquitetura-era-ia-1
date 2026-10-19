import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..ports import ModelUnavailable

Progress = Callable[[int, int], None]


@dataclass
class Job:
    id: str
    state: str = "pending"          # pending -> running -> done | failed
    done: int = 0
    total: int | None = None
    result: dict | None = None
    reason: str | None = None
    touched_at: float = field(default_factory=time.monotonic)


class JobAbandoned(Exception):
    """A tarefa já foi dada como falha; o trabalho em andamento deve parar."""


class InMemoryJobs:
    """Tarefas em segundo plano dentro do processo da aplicação (Asynchronous Request-Reply).

    No máximo `max_running` tarefas rodam ao mesmo tempo; as outras esperam como
    `pending`. Uma tarefa em `running` sem progresso por `stall_seconds` é dada como
    `failed`, para nunca ficar presa. Reiniciar a aplicação perde as tarefas: o
    enunciado não cobra sobreviver a reinício (docs/adr).
    """

    def __init__(self, max_running: int, stall_seconds: float):
        self._pool = ThreadPoolExecutor(max_workers=max_running, thread_name_prefix="job")
        self._stall_seconds = stall_seconds
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, work: Callable[[Progress], object]) -> str:
        job = Job(id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.id] = job
        self._pool.submit(self._run, job, work)
        return job.id

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.state == "running" and time.monotonic() - job.touched_at > self._stall_seconds:
                self._finish(job, "failed", reason=f"sem progresso há mais de {self._stall_seconds:.0f} s")
            return job

    def _run(self, job: Job, work: Callable[[Progress], object]) -> None:
        def progress(done: int, total: int) -> None:
            with self._lock:
                if job.state != "running":
                    raise JobAbandoned(job.id)   # o vigia já desistiu: para de gastar chamadas
                job.done, job.total, job.touched_at = done, total, time.monotonic()

        with self._lock:
            job.state, job.touched_at = "running", time.monotonic()
        try:
            result = work(progress)
        except ModelUnavailable as error:
            with self._lock:
                self._finish(job, "failed", reason=f"modelo indisponível para {error.capability}")
            return
        except Exception as error:  # a tarefa nunca fica em running por erro inesperado
            with self._lock:
                self._finish(job, "failed", reason=f"erro interno: {type(error).__name__}")
            return
        with self._lock:
            self._finish(job, "done", result=result.model_dump(mode="json"))

    @staticmethod
    def _finish(job: Job, state: str, result: dict | None = None, reason: str | None = None) -> None:
        if job.state in ("done", "failed"):
            return  # quem chegou primeiro (resultado ou vigia de travamento) decide
        job.state, job.result, job.reason = state, result, reason
