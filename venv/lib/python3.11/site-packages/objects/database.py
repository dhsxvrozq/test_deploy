from typing import Optional
import asyncpg
from typing import Optional


class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(self.dsn)

    async def close(self):
        if self.pool:
            await self.pool.close()
