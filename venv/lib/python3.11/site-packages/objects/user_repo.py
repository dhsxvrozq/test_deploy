# objects/user_repo.py

import logging
from typing import Optional, List, Dict, Any
from asyncpg.exceptions import PostgresError

from .models import User          # Модель пользователя
from .database import Database      # Ваш класс Database, у которого есть атрибут .pool

logger = logging.getLogger(__name__)


class UserRepository:
    # Здесь мы сохраним ссылку на экземпляр Database
    _db: Database = None

    @classmethod
    def init_db(cls, db: Database):
        """
        Вызывается один раз при старте приложения (в run.py), 
        чтобы установить соединение с БД для всех методов этого репозитория.
        """
        cls._db = db

    @classmethod
    async def create(cls, user: User) -> User:
        """
        Вставка нового пользователя (или обновление, если такой tg_id уже есть).
        Возвращает объект User, созданный из возвращённой строки.
        """
        async with cls._db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (tg_id, trial, vless_key, slot_id, subscription_end)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (tg_id) DO UPDATE
                  SET trial = EXCLUDED.trial,
                      vless_key = EXCLUDED.vless_key,
                      slot_id = EXCLUDED.slot_id,
                      subscription_end = EXCLUDED.subscription_end
                RETURNING *
                """,
                user.tg_id, user.trial, user.vless_key,
                user.slot_id, user.subscription_end
            )
            if not row:
                raise ValueError("Не удалось создать или обновить пользователя")
            return User(**row)

    @classmethod
    async def find_by_tg_id(cls, tg_id: int) -> Optional[User]:
        """
        Поиск пользователя по Telegram ID. 
        Если не найден, возвращает None.
        """
        async with cls._db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE tg_id = $1", tg_id
            )
            return User(**row) if row else None

    @classmethod
    async def update(cls, user: User) -> User:
        """
        Полное обновление полей пользователя (кроме tg_id). 
        Предполагается, что объект user уже получен ранее (из БД или создан).
        """
        async with cls._db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE users
                   SET trial = $2,
                       vless_key = $3,
                       slot_id = $4,
                       subscription_end = $5
                 WHERE tg_id = $1
                 RETURNING *
                """,
                user.tg_id, user.trial, user.vless_key,
                user.slot_id, user.subscription_end
            )
            if not row:
                raise ValueError("Пользователь не найден")
            return User(**row)

    @classmethod
    async def is_subscription_active(cls, tg_id: int) -> bool:
        """
        Проверка, активна ли подписка у пользователя с данным tg_id.
        Возвращает True, если subscription_end > текущее UTC-время.
        """
        user = await cls.find_by_tg_id(tg_id)
        if not user or not user.subscription_end:
            return False

        from datetime import datetime, timezone
        return user.subscription_end > datetime.now(timezone.utc)

    @classmethod
    async def assign_slot(cls, tg_id: int, slot_id: int) -> Optional[User]:
        """
        Назначает пользователю слот и устанавливает trial = TRUE, subscription_end = NOW() + 24ч.
        Возвращает обновлённого User либо None, если пользователь не найден.
        """
        async with cls._db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    UPDATE users
                       SET slot_id = $1,
                           trial = TRUE,
                           subscription_end = CURRENT_TIMESTAMP + INTERVAL '24 hours'
                     WHERE tg_id = $2
                     RETURNING *
                    """,
                    slot_id, tg_id
                )
                return User(**row) if row else None

    @classmethod
    async def update_vless_key(cls, tg_id: int, vless_key: str) -> User:
        """
        Обновляет только поле vless_key у пользователя с данным tg_id.
        """
        async with cls._db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE users
                   SET vless_key = $2
                 WHERE tg_id = $1
                 RETURNING *
                """,
                tg_id, vless_key
            )
            if not row:
                raise ValueError("Пользователь не найден")
            return User(**row)

    @classmethod
    async def fetch_expired_users(cls) -> List[Dict[str, Any]]:
        """
        Возвращает список словарей 
        {id, tg_id, slot_id, trial} 
        для всех пользователей, у которых subscription_end < NOW().
        """
        async with cls._db.pool.acquire() as conn:
            try:
                records = await conn.fetch(
                    """
                    SELECT id, tg_id, slot_id, trial
                      FROM users
                     WHERE subscription_end < NOW()
                    """
                )
                users = [dict(record) for record in records]
                logger.debug(f"Найдено {len(users)} пользователей с истёкшей подпиской")
                return users

            except PostgresError as e:
                logger.error(f"Ошибка БД при получении пользователей: {e}")
                raise
            except Exception as e:
                logger.error(f"Непредвиденная ошибка при получении пользователей: {e}")
                raise

    @classmethod
    async def deactivate_user_subscription(cls, user_id: int) -> None:
        """
        Деактивирует подписку пользователя (id в базе).
        Сбрасывает vless_key, slot_id и subscription_end в NULL.
        """
        async with cls._db.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    await conn.execute(
                        """
                        UPDATE users
                           SET vless_key = NULL,
                               slot_id = NULL,
                               subscription_end = NULL
                         WHERE id = $1
                        """,
                        user_id
                    )
                    logger.info(f"Подписка для пользователя с id {user_id} деактивирована")

                except PostgresError as e:
                    logger.error(f"Ошибка БД при деактивации подписки для id={user_id}: {e}")
                    raise
                except Exception as e:
                    logger.error(f"Непредвиденная ошибка при деактивации подписки для id={user_id}: {e}")
                    raise
