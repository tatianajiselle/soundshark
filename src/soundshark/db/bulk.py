from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection


async def copy_into(
    connection: AsyncConnection, table: str, columns: Sequence[str], records: list[tuple[Any, ...]]
) -> None:
    if not records:
        return
    pooled_connection = await connection.get_raw_connection()
    asyncpg_connection = pooled_connection.driver_connection
    if asyncpg_connection is None:
        raise RuntimeError("the database connection was closed before COPY")
    await asyncpg_connection.copy_records_to_table(table, records=records, columns=list(columns))
