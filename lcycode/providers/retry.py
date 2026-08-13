"""Small retry/backoff helper for transient provider failures
(timeouts, connection resets, 5xx) — before we give up on a key or
provider entirely."""
import asyncio
import functools

import httpx

TRANSIENT_STATUS = {500, 502, 503, 504}


def with_retry(max_attempts=3, base_delay=0.75):
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return await fn(*args, **kwargs)
                except httpx.TimeoutException as e:
                    last_exc = e
                except httpx.HTTPStatusError as e:
                    if e.response.status_code not in TRANSIENT_STATUS:
                        raise
                    last_exc = e
                if attempt < max_attempts - 1:
                    await asyncio.sleep(base_delay * (2 ** attempt))
            raise last_exc
        return wrapper
    return decorator
