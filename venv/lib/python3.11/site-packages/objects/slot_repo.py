# repositories/slot_repository.py

import logging
import asyncpg
from typing import Optional
from .models import Slot           # Pydantic-модель Slot
from .database import Database     # ваш класс Database с self.pool

logger = logging.getLogger(__name__)


class SlotRepository:
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
    async def add_slots(cls, server_name: str, ip: str, num_slots: int = 40) -> None:
        """
        Создаёт num_slots новых записей в таблице slots для заданного server_name и ip.
        """
        records = [(server_name, ip) for _ in range(num_slots)]
        async with cls._db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """
                    INSERT INTO slots (server_name, ip)
                    VALUES ($1, $2)
                    """,
                    records
                )
        logger.info(f"Добавлено {num_slots} слотов для сервера '{server_name}' (IP: {ip}).")

    @classmethod
    async def find_free_slot(cls) -> Optional[Slot]:
        """
        Находит первый свободный слот (tg_id IS NULL) в таблице slots и возвращает объект Slot.
        Если свободных слотов нет — возвращает None.
        """
        async with cls._db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                  FROM slots
                 WHERE tg_id IS NULL
                 ORDER BY slot_id ASC
                 LIMIT 1
                """
            )

        if row:
            logger.debug(f"Найден свободный слот: {row['slot_id']}")
            return Slot(**row)
        else:
            logger.debug("Свободных слотов не найдено.")
            return None

    @classmethod
    async def assign_user_to_slot(cls, tg_id: int) -> Optional[Slot]:
        """
        Присваивает первому свободному слоту пользователя с данным tg_id.
        Возвращает объект Slot, если операция успешна, или None, если свободных слотов нет.
        """
        async with cls._db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    UPDATE slots
                       SET tg_id = $1,
                           assigned_at = CURRENT_TIMESTAMP
                     WHERE slot_id = (
                         SELECT slot_id
                           FROM slots
                          WHERE tg_id IS NULL
                          ORDER BY slot_id ASC
                          LIMIT 1
                     )
                     RETURNING *
                    """,
                    tg_id
                )

        if row:
            logger.info(f"Пользователь {tg_id} присвоен к слоту {row['slot_id']}.")
            return Slot(**row)
        else:
            logger.info(f"Не удалось найти свободный слот для пользователя {tg_id}.")
            return None

    @classmethod
    async def clear_slot(cls, slot_id: int, trial: bool) -> None:
        """
        Очищает указанный слот (сбрасывает tg_id и assigned_at).
        Если trial=True, правит таблицу trial_slots, иначе slots.
        """
        table = 'trial_slots' if trial else 'slots'
        async with cls._db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    f"""
                    UPDATE {table}
                       SET tg_id = NULL,
                           assigned_at = NULL
                     WHERE slot_id = $1
                    """,
                    slot_id
                )
        logger.info(f"Слот {slot_id} очищен в таблице '{table}'.")
