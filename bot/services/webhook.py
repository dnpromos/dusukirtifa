import asyncio
import logging
import uuid

from aiohttp import web

from bot.config import WEBHOOK_BASE_URL, WEBHOOK_PORT

logger = logging.getLogger(__name__)

_pending: dict[str, asyncio.Future] = {}

app = web.Application()


def get_callback_url() -> tuple[str, asyncio.Future]:
    callback_id = uuid.uuid4().hex[:12]
    future = asyncio.get_event_loop().create_future()
    _pending[callback_id] = future
    url = f"{WEBHOOK_BASE_URL}/wiro/callback/{callback_id}"
    return url, future


async def _handle_callback(request: web.Request) -> web.Response:
    callback_id = request.match_info["callback_id"]
    future = _pending.pop(callback_id, None)

    if not future or future.done():
        return web.json_response({"ok": False}, status=404)

    try:
        body = await request.json()
    except Exception:
        body = await request.text()

    future.set_result(body)
    logger.info(f"Wiro callback received: {callback_id}")
    return web.json_response({"ok": True})


def cleanup_future(callback_id: str):
    future = _pending.pop(callback_id, None)
    if future and not future.done():
        future.cancel()


app.router.add_post("/wiro/callback/{callback_id}", _handle_callback)


async def start_webhook_server():
    if not WEBHOOK_BASE_URL:
        logger.info("WEBHOOK_BASE_URL not set — webhook server disabled, using polling")
        return None

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()
    logger.info(f"Webhook server started on port {WEBHOOK_PORT}")
    return runner
