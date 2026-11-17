# 0022. The jobs connect as a limited role

**Status:** Accepted

## Context

Until now one connection string did everything: migrations, crawls, ingest and the graph job, all as the database owner. The owner can drop every table. On a server that runs unattended every night, a leaked or misused connection string should not be able to do that.

## Decision

- **Two connection strings.** `MIGRATIONS_DATABASE_URL` is the owner, used only by `alembic`. `DATABASE_URL` is the limited jobs role, used by every `soundshark` command.
- **`soundshark create-jobs-role`** creates the role (default `soundshark_jobs`), or rotates its password when it already exists. It connects as the owner, generates a random password, and writes the role's connection string straight into `.env` (mode 600). The password is never printed.
- **The role gets only what the jobs use:**
  - `CONNECT` on the database and `USAGE` on the schema;
  - `SELECT`, `INSERT`, `UPDATE` and `DELETE` on the tables (`COPY` needs only `INSERT`);
  - `USAGE` and `SELECT` on the sequences behind the id columns;
  - default privileges, so tables added by later migrations are covered without re-running the command;
  - read-only access to the migration-version table.
- **No schema changes:** no `CREATE`, `DROP`, `ALTER`, `TRUNCATE` or role management. A test checks each of these is refused.
- **The role is created in SQL.** Roles made in the hosting console or API are added to the provider's admin group, which is the opposite of limited.
- **The server's `.env` holds only the jobs role.** Migrations run at deploy time with the owner string supplied for that one command, so it never sits on the server.
- **The explorer API will get its own `SELECT`-only role** when it exists.

## Consequences

- A leaked jobs string can change rows, but it can't drop tables, change the schema or create roles. Every row can be rebuilt from the page store anyway ([0004](0004-fetch-once-parse-many.md)).
- Order matters on a fresh database: migrate first, then create the role.
- Rotating the password is one command; the old password stops working immediately.

## Alternatives considered

- **Keep using the owner everywhere.** Simplest, but one leak loses the database.
- **Create the role in the hosting console.** One click, but the role would join the admin group.
- **Grant `ALL` on the tables.** Shorter, but it includes `TRUNCATE`, `REFERENCES` and `TRIGGER`, which the jobs never need.
