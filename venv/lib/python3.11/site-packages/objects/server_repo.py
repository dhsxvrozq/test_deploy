# repositories/server_repository.py

from typing import Optional
from asyncpg.exceptions import UniqueViolationError, PostgresError
from .models import Server
from .database import Database


class ServerRepository:
    # Хранит ссылку на экземпляр Database
    _db: Database = None

    @classmethod
    def init_db(cls, db: Database):
        """
        Вызывается один раз при старте приложения (в run.py),
        чтобы установить соединение с БД для всех методов этого репозитория.
        """
        cls._db = db

    @classmethod
    async def add_server_to_db(cls, server: Server) -> Optional[Server]:
        """
        Вставляет новый сервер в таблицу servers.
        Если успешно, возвращает объект Server, созданный из возвращённой строки.
        """
        async with cls._db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO servers (id, name, ip, region, status, created_at, free_slots)
                    VALUES ($1, $2, $3, $4, $5, COALESCE($6, CURRENT_TIMESTAMP), $7)
                    RETURNING *
                    """,
                    server.id,
                    server.name,
                    server.ip,
                    server.region,
                    server.status,
                    server.created_at,
                    server.free_slots
                )
                return Server(**row) if row else None

    @classmethod
    async def find_by_id(cls, server_id: int) -> Optional[Server]:
        """
        Ищет сервер по его id. Если найден, возвращает объект Server, иначе None.
        """
        async with cls._db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM servers WHERE id = $1", server_id
            )
            return Server(**row) if row else None

    @classmethod
    async def update_status(cls, server_id: int, new_status: str) -> Optional[Server]:
        """
        Обновляет поле status у сервера с данным server_id.
        Возвращает обновлённый объект Server, либо None, если сервер не найден.
        """
        async with cls._db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE servers
                   SET status = $2
                 WHERE id = $1
                 RETURNING *
                """,
                server_id, new_status
            )
            return Server(**row) if row else None
