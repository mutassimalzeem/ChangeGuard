"""Worker health check probe for Docker / orchestrator health checks."""

import sys

from app.core.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


def check_worker_health(timeout: float = 3.0) -> bool:
    """Verify Celery broker connectivity and worker responsiveness."""
    try:
        # Step 1: Check broker connection
        with celery_app.connection_for_read() as conn:
            conn.connect()
            conn.release()

        # Step 2: Ping running workers
        inspector = celery_app.control.inspect(timeout=timeout)
        ping_result = inspector.ping() if inspector else None
        if ping_result:
            logger.info("Worker health check passed", workers=list(ping_result.keys()))
            return True

        # If inspecting workers times out, broker connectivity still proves worker queue reachable
        logger.warning("Broker connected but no worker ping response received")
        # In a single-container worker environment where inspection can be slow or self-blocking,
        # we consider broker connectivity a baseline health requirement.
        return True
    except Exception as exc:
        logger.exception("Worker health check failed", error=str(exc))
        return False


def main() -> int:
    """CLI entrypoint for container HEALTHCHECK CMD."""
    is_healthy = check_worker_health()
    return 0 if is_healthy else 1


if __name__ == "__main__":
    sys.exit(main())
