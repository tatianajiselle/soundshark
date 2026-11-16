# 0010. A public, read-only explorer with no accounts

**Status:** Accepted

## Context

The point is to let people explore a scene. Accounts would add sign-up flows, passwords, personal data and abuse handling, none of which help anyone explore.

## Decision

- The explorer is **public and read-only**, served by a small FastAPI app.
- There are **no user accounts**. Admin work (approving alias suggestions, re-running jobs) is done through command-line tools on the server, not a web login.
- It shows **derived connections and scores**, such as "played the same night 4 times since 2019", and links to the original event pages for the details. It is not a mirror of anyone's archive (see [0012](0012-data-ethics.md)).
- It is non-commercial.

## Consequences

- No personal data is collected, and there is very little to attack.
- Anything personalized (saved favourites, for example) would need a new decision.

## Alternatives considered

- **An admin web UI behind a login.** Convenient, but a login is a security surface for a single maintainer who already has a shell.
