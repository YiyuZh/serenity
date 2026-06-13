from __future__ import annotations

import argparse

from sqlalchemy import or_, select, text

from app.application.account_service import ensure_default_account
from app.application.normalizer import normalize_x_payload
from app.application.processing_service import process_post_lifecycle
from app.application.sync_pipeline import SyncPipeline
from app.application.sync_service import create_manual_sync_run
from app.config import get_settings
from app.infrastructure.db import init_db, session_scope
from app.infrastructure.external_clients import DeepSeekClient, FeishuWebhookClient, XApiClient
from app.infrastructure.models import Post


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="serenity-backend")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db")
    resolve_parser = subparsers.add_parser("resolve-user")
    resolve_parser.add_argument("handle", nargs="?")
    subparsers.add_parser("sync-once")
    retry_parser = subparsers.add_parser("retry-failed")
    retry_parser.add_argument("--limit", type=int, default=50)
    check_parser = subparsers.add_parser("check-integrations")
    check_parser.add_argument("--handle")
    check_parser.add_argument("--send-feishu-test", action="store_true")
    subparsers.add_parser("healthcheck")
    args = parser.parse_args(argv)

    if args.command == "init-db":
        get_settings().validate_runtime_security()
        init_db()
        with session_scope() as session:
            ensure_default_account(session)
        print("Database initialized")
        return 0
    if args.command == "resolve-user":
        settings = get_settings()
        handle = (args.handle or settings.x_account_handle).lstrip("@")
        user_id = XApiClient(settings=settings).resolve_user(handle)
        print(user_id)
        return 0
    if args.command == "sync-once":
        settings = get_settings()
        settings.validate_runtime_security()
        init_db()
        with session_scope() as session:
            account = ensure_default_account(session)
            run = create_manual_sync_run(session, account)
            pipeline = SyncPipeline()
            pipeline.process_run(session, run.id)
            for post_id in pipeline.last_new_post_ids:
                process_post_lifecycle(session, post_id)
            print(f"Sync run {run.id}: fetched={run.fetched_count} new={run.new_count} processed={len(pipeline.last_new_post_ids)}")
        return 0
    if args.command == "retry-failed":
        init_db()
        failed = {"failed", "retrying"}
        with session_scope() as session:
            post_ids = list(
                session.scalars(
                    select(Post.id)
                    .where(
                        or_(
                            Post.media_status.in_(failed),
                            Post.translation_status.in_(failed),
                            Post.push_status.in_(failed),
                        )
                    )
                    .order_by(Post.updated_at.asc())
                    .limit(max(1, args.limit))
                )
            )
            for post_id in post_ids:
                process_post_lifecycle(session, post_id)
            print(f"Retried {len(post_ids)} posts")
        return 0
    if args.command == "check-integrations":
        settings = get_settings()
        handle = (args.handle or settings.x_account_handle).lstrip("@")
        x_client = XApiClient(settings=settings)
        user_id = x_client.resolve_user(handle)
        payload = x_client.fetch_posts(user_id, since_id=None, max_results=min(settings.x_max_results, 10), max_pages=1)
        posts = normalize_x_payload(payload, handle)
        print(f"X API ok: handle=@{handle} user_id={user_id} fetched={len(posts)}")

        translated, usage = DeepSeekClient(settings=settings).translate("Serenity integration check. Preserve number 123.")
        print(f"DeepSeek ok: translated={translated[:120]!r} total_tokens={usage.get('total_tokens')}")

        if args.send_feishu_test:
            FeishuWebhookClient(settings=settings).send(
                {
                    "msg_type": "text",
                    "content": {"text": f"Serenity integration check ok for @{handle}. X posts fetched: {len(posts)}."},
                }
            )
            print("Feishu ok: test message sent")
        else:
            print("Feishu skipped: rerun with --send-feishu-test to send a group message")
        return 0
    if args.command == "healthcheck":
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        print("ok")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
