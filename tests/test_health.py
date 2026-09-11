"""Unit test: /health route really registered (regression: it once 404'd)."""
import asyncio

import aiohttp
import aiohttp.web

from main import create_health_app


def test_health_endpoint_returns_200():
    async def go():
        runner = aiohttp.web.AppRunner(create_health_app())
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "127.0.0.1", 18081)
        await site.start()
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("http://127.0.0.1:18081/health") as r:
                    assert r.status == 200
                    assert await r.json() == {"status": "ok"}
                async with s.post("http://127.0.0.1:18081/health") as r:
                    assert r.status == 405  # GET-only
        finally:
            await runner.cleanup()

    asyncio.run(go())
