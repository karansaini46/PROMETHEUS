#!/usr/bin/env python3
"""CLI wrapper to run PROMETHEUS development database seed."""

import asyncio

from services.api.db import AsyncSessionLocal
from services.api.seed import seed_database


async def run():
    print("Seeding PROMETHEUS development database...")
    async with AsyncSessionLocal() as session:
        await seed_database(session)
    print("Database seeding completed successfully.")


if __name__ == "__main__":
    asyncio.run(run())
