import threading
import time

from helpdesk.adapters.jobs import InMemoryJobs
from helpdesk.ports import ModelUnavailable
from helpdesk.schemas import ReportStatus


def wait_state(jobs: InMemoryJobs, job_id: str, states: set[str], timeout: float = 2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if job.state in states:
            return job
        time.sleep(0.01)
    raise AssertionError(f"tarefa ficou em {jobs.get(job_id).state}")


def test_tarefa_concluida_guarda_o_resultado():
    jobs = InMemoryJobs(max_running=1, stall_seconds=5)

    def work(progress):
        progress(3, 3)
        return ReportStatus(state="pronto")

    job = wait_state(jobs, jobs.submit(work), {"done"})

    assert (job.result, job.done, job.total) == ({"state": "pronto", "progress": None, "reason": None}, 3, 3)


def test_modelo_indisponivel_vira_failed_com_o_motivo():
    jobs = InMemoryJobs(max_running=1, stall_seconds=5)

    def work(progress):
        raise ModelUnavailable("topic-analyst", "InternalServerError")

    job = wait_state(jobs, jobs.submit(work), {"failed"})

    assert job.reason == "modelo indisponível para topic-analyst"


def test_tarefa_sem_progresso_vira_failed_e_o_trabalho_para_no_proximo_progresso():
    jobs = InMemoryJobs(max_running=1, stall_seconds=0.05)
    release, stopped = threading.Event(), threading.Event()

    def work(progress):
        release.wait(1)
        try:
            progress(1, 2)
        except Exception:
            stopped.set()
            raise

    job_id = jobs.submit(work)
    time.sleep(0.1)
    job = wait_state(jobs, job_id, {"failed"})
    release.set()

    assert job.reason.startswith("sem progresso")
    assert stopped.wait(1)


def test_tarefas_alem_do_limite_esperam_como_pending():
    jobs = InMemoryJobs(max_running=1, stall_seconds=5)
    release = threading.Event()
    first = jobs.submit(lambda progress: release.wait(1) and ReportStatus(state="ok"))
    second = jobs.submit(lambda progress: ReportStatus(state="ok"))

    assert jobs.get(second).state == "pending"
    release.set()
    wait_state(jobs, first, {"done"})
    wait_state(jobs, second, {"done"})
