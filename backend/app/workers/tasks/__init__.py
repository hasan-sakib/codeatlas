from app.workers.tasks import indexing_tasks  # noqa: F401

# `celery_app.autodiscover_tasks(["app.workers"])` imports exactly
# `app.workers.tasks` (this file) — it does not descend into submodules
# on its own. Every task module must be imported here or autodiscovery
# silently registers nothing, which is exactly what happened before this
# import existed: the worker started, connected to Redis, and reported
# an empty `[tasks]` list.
__all__ = ["indexing_tasks"]
