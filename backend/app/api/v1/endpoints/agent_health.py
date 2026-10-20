import os

import httpx
from fastapi import APIRouter

from app.agent.llm_client import LLMClient

router = APIRouter()


@router.get("/agent/health")
async def health():
    semantic = {"ready": False}
    try:
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            response = await client.get(os.getenv("SEMANTIC_URL", "http://semantic:8010") + "/health")
            response.raise_for_status()
            semantic = response.json()
        expected = os.getenv("SEMANTIC_INDEX_VERSION")
        if expected and semantic.get("manifest", {}).get("version") != expected:
            semantic["ready"] = False
            semantic["error"] = "index_version_mismatch"
    except Exception as exc:
        semantic["error"] = type(exc).__name__
    return {"application": "CineWeave", "version": "0.1.0", "parser_mode": LLMClient().mode,
            "llm_configured": LLMClient().mode == "llm", "semantic": semantic,
            "explanations": "evidence_templates", "ready": bool(semantic.get("ready"))}
