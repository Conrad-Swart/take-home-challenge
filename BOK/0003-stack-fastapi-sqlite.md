# 0003. FastAPI + SQLModel + SQLite for the backend

## Context
Need a small backend that handles auth, an upload endpoint, and history
queries. Alternatives considered:
- Django (batteries but heavy for a 4-6 hour rebuild)
- Flask (fine but no built-in typing / OpenAPI)
- Node/Express (adds a second language — reviewer would have to context-switch)

## Decision
- FastAPI for the API
- SQLModel for models (thin wrapper over SQLAlchemy + Pydantic)
- SQLite for storage
- passlib[bcrypt] for password hashing
- itsdangerous for signed session cookies

## Why
- FastAPI is the smallest Python framework that gives dependency injection,
  form handling, static file mounting, and generated OpenAPI in one place.
- SQLModel keeps the model definitions in the same shape they'd have in a
  team-scale app, so section 3 of WRITEUP can honestly say "swap SQLite for
  Postgres with a URL change" without hand-waving.
- SQLite lets docker compose up work with zero external services. A reviewer
  clones the repo and it runs.

## Cost accepted
SQLite is not fine for a real multi-user deployment (write concurrency).
Called out in WRITEUP section 3 as priority 3 for the next two weeks.
