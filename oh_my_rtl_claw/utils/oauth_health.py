from __future__ import annotations

import httpx


async def check_openai_oauth_proxy(base_url: str) -> dict[str, object]:
    models_url = base_url.rstrip("/") + "/models"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(models_url)
            response.raise_for_status()
            data = response.json()
            models = [item.get("id", "") for item in data.get("data", [])]
            return {"ok": True, "models": models}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "models": []}
