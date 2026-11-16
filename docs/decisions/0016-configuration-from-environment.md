# 0016. Configuration comes from environment variables, read directly

**Status:** Accepted

## Context

SoundShark needs a handful of settings: which sources to load, the database URLs, and a test database URL. They differ between a laptop, CI and the server, and some are secrets. A settings library (pydantic-settings) was the original plan.

## Decision

Read each setting from an environment variable where it is used, through a small helper that fails with a clear message when a required one is missing. A `.env` file in the **directory the command runs from** is loaded first, so running from another checkout uses that checkout's settings. `.env` is never committed; `.env.example` lists every key with no values.

| Variable | Used by |
|---|---|
| `SOUNDSHARK_SOURCES` | which sources to load (`module.path:ClassName`, comma-separated; the demo by default) |
| `DATABASE_URL` | migrations, `ingest`, `identify` (a direct connection) |
| `DATABASE_URL_POOLED` | the API, later (a pooled connection) |
| `TEST_DATABASE_URL` | the Postgres tests (dropped and recreated) |

## Consequences

- No extra dependency, and nothing to learn to read the code.
- Values are strings; any parsing happens next to the code that uses them.
- If settings grow (many typed options, nested config), switch to a settings library then.

## Alternatives considered

- **pydantic-settings.** Typed and validated, but heavier than four strings need.
- **A config file.** Another file to keep out of git, with secrets in it.
