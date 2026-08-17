# Deployment (Phase 11)

Stateless service -- no database, no persistent volumes. `docker-compose.yml`
runs it standalone with `uvicorn --reload` for local dev.

## Production (standalone image, no compose)

The Dockerfile's `CMD` runs gunicorn with `uvicorn_worker.UvicornWorker`
workers instead of bare uvicorn. Worker count is deliberately low (2): each
request holds an LLM call open for up to `REQUEST_TIMEOUT_SECONDS`, so this
is sized to avoid piling up concurrent outbound calls, not to maximize
request throughput.

## Auth

`SERVICE_AUTH_TOKEN` must be set to a real shared secret in any real
deployment -- it's what stops this service (and the LLM credits behind it)
from being reachable by anything other than workroom-backend's
`celery_worker_heavy`. Empty disables the check, which is fine for local dev
only.

## Error tracking

Not pre-wired, same as workroom-backend -- see that repo's DEPLOYMENT.md.
