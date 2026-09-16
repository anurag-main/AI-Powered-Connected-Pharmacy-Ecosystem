"""Send refill reminders for everyone currently due. Run by a scheduler.

    python -m scripts.refill_sweep
    python -m scripts.refill_sweep --as-of 2026-09-20 --limit 20 --dry-run

WHY A SCRIPT AND NOT CELERY
---------------------------
The requirement is "run this once a day". That is a cron problem, not a queueing
problem. Celery buys retries, concurrency and a broker; this job needs a few
sends a day, retries are already handled by the attempt counter on each
notification row, and adding Redis plus a worker process to a single-server
pharmacy deployment is infrastructure nobody is going to operate.

APScheduler was the other candidate. It would run in-process, which means the
sweep only happens while the API is up and runs once per worker if the API is
ever scaled out. An external scheduler is one process, observable with the same
tools as any other command, and cannot fire twice because it is scaled.

    Windows:  Task Scheduler -> daily -> python -m scripts.refill_sweep
    Linux:    0 10 * * *  cd /app && python -m scripts.refill_sweep

WHY IT DOES NOT CALL THE API
----------------------------
It imports NotificationService directly. Making an HTTP request to the same
application would add a network hop, a second set of failure modes and an
authentication problem, all to reach code already importable in-process.

SAFE BY DEFAULT
---------------
With WHATSAPP_ENABLED unset or false, the provider factory returns the fake and
this command sends nothing. Turning it on is deliberate.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from app.core.database import SessionLocal
from app.core.logging_config import configure_logging
from app.integrations.messaging.factory import get_messaging_provider
from app.integrations.messaging.fake import FakeMessagingProvider
from app.integrations.messaging.whatsapp import whatsapp_is_enabled
from app.services.notification_service import NotificationService

logger = logging.getLogger("app.refill_sweep")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send due refill reminders.")
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="Reference date (YYYY-MM-DD). Defaults to today in the pharmacy timezone.",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force the fake provider even if WHATSAPP_ENABLED is true.",
    )
    args = parser.parse_args(argv)

    configure_logging()

    provider = FakeMessagingProvider() if args.dry_run else get_messaging_provider()

    logger.info(
        "refill_sweep_starting",
        extra={
            "provider": provider.name,
            "whatsapp_enabled": whatsapp_is_enabled(),
            "dry_run": args.dry_run,
            "as_of": str(args.as_of) if args.as_of else None,
        },
    )

    with SessionLocal() as db:
        service = NotificationService(db, provider=provider)
        counts = service.run_sweep(as_of=args.as_of, limit=args.limit)

    # Printed as well as logged so a cron mail or Task Scheduler history shows
    # the outcome without anyone opening the log file.
    print(
        f"considered={counts['considered']} sent={counts['sent']} "
        f"skipped={counts['skipped']} failed={counts['failed']} "
        f"provider={provider.name}"
    )

    # Non-zero when something failed, so a scheduler can surface it.
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
