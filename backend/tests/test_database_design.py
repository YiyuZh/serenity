from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_database_design_doc_contains_required_sections():
    content = (ROOT / "docs" / "database-design.md").read_text(encoding="utf-8")
    required = [
        "ER 图",
        "字段",
        "约束",
        "索引",
        "状态流转",
        "生命周期",
        "自检优化清单",
        "source_accounts",
        "task_attempts",
    ]
    for item in required:
        assert item in content


def test_migration_has_foreign_key_indexes_and_check_constraints():
    migration = (ROOT / "backend" / "migrations" / "001_initial.sql").read_text(encoding="utf-8")
    required = [
        "CONSTRAINT ck_posts_fetch_status",
        "CONSTRAINT ck_media_assets_status",
        "CONSTRAINT ck_translation_jobs_status",
        "CONSTRAINT ck_push_logs_status",
        "CONSTRAINT ck_sync_runs_status",
        "CONSTRAINT ck_task_attempts_status",
        "idx_media_assets_post_id",
        "idx_translation_jobs_post_id",
        "idx_push_logs_post_id",
        "idx_push_logs_target_id",
        "idx_sync_runs_account_started",
        "idx_task_attempts_post_id",
        "idx_posts_failed_partial",
    ]
    for item in required:
        assert item in migration
