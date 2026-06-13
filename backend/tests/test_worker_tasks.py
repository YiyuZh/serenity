from __future__ import annotations

from sqlalchemy import select

from app.config import get_settings
from app.infrastructure.db import get_engine, get_session_factory, init_db, session_scope
from app.infrastructure.models import SourceAccount, SyncRun


def test_poll_accounts_creates_runs_and_enqueues_processing(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'worker.db'}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("X_ACCOUNT_HANDLE", "aleabitoreddit")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    init_db()

    from app.worker import tasks

    enqueued_run_ids: list[int] = []
    monkeypatch.setattr(tasks.process_sync_run, "delay", lambda run_id: enqueued_run_ids.append(run_id))

    run_ids = tasks.poll_accounts()

    assert run_ids
    assert enqueued_run_ids == run_ids
    with session_scope() as session:
        runs = list(session.scalars(select(SyncRun).order_by(SyncRun.id.asc())))
        assert [run.id for run in runs] == run_ids
        assert all(run.status == "pending" for run in runs)


def test_process_sync_run_enqueues_new_post_processing(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'worker-process.db'}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    init_db()

    with session_scope() as session:
        account = SourceAccount(source="x", handle="aleabitoreddit", active=True)
        session.add(account)
        session.flush()
        run = SyncRun(account_id=account.id, triggered_by="manual", status="pending")
        session.add(run)
        session.flush()
        run_id = run.id

    from app.worker import tasks

    class FakePipeline:
        last_new_post_ids = [11, 12]

        def process_run(self, session, run_id):
            return None

    enqueued_post_ids: list[int] = []
    monkeypatch.setattr(tasks, "SyncPipeline", FakePipeline)
    monkeypatch.setattr(tasks.process_post, "delay", lambda post_id: enqueued_post_ids.append(post_id))

    assert tasks.process_sync_run(run_id) == run_id
    assert enqueued_post_ids == [11, 12]
