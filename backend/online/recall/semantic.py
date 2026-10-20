import os

import httpx


async def semantic_recall(query, eligible_ids, top_k=100):
    async with httpx.AsyncClient(timeout=float(os.getenv("SEMANTIC_TIMEOUT", "10")), trust_env=False) as client:
        result = await client.post(os.getenv("SEMANTIC_URL", "http://semantic:8010") + "/search",
            json={"text": query, "eligible_ids": eligible_ids, "top_k": top_k,
                  "expected_version": os.getenv("SEMANTIC_INDEX_VERSION") or None})
        result.raise_for_status()
        return result.json()
