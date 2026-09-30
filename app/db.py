import asyncpg
from typing import List, Dict, Any, Optional
from app.config import AppConfig


class Database:
    def __init__(self, config: AppConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=self.config.database_host,
                port=self.config.database_port,
                user=self.config.database_user,
                password=self.config.database_pass,
                database=self.config.database_name,
                min_size=1,
                max_size=10,
                command_timeout=60,
            )

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            records = await conn.fetch(query, *args)
            return [dict(r) for r in records]

    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(query, *args)
            return dict(record) if record else None

    async def fetchval(self, query: str, *args) -> Any:
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def get_cars(self) -> List[Dict[str, Any]]:
        query = """
            SELECT id, name, model, vin, efficiency, exterior_color, trim_badging
            FROM cars
            ORDER BY display_priority ASC, name ASC;
        """
        return await self.fetch(query)

    async def get_teslamate_settings(self) -> Optional[Dict[str, Any]]:
        query = """
            SELECT unit_of_length, unit_of_temperature, unit_of_pressure, preferred_range
            FROM settings
            LIMIT 1;
        """
        return await self.fetchrow(query)
