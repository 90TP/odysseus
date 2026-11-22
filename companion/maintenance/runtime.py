"""Wire the maintainer to Odysseus' real agent loop and LLM route."""

from __future__ import annotations

import logging

from companion.maintenance.config import MaintenanceConfig
from companion.maintenance.monitor import AerithMaintainer

logger = logging.getLogger(__name__)

_maintainer: AerithMaintainer | None = None


def get_maintainer() -> AerithMaintainer | None:
    return _maintainer


def build_maintainer(config: MaintenanceConfig | None = None) -> AerithMaintainer | None:
    global _maintainer
    config = config or MaintenanceConfig.from_env()
    if not config.enabled:
        return None

    def _route():
        if not config.owner:
            raise RuntimeError("Set AERITH_MAINTENANCE_OWNER to the Odysseus user Aerith works as")
        from companion.routes import _resolve_aerith_route
        return _resolve_aerith_route(config.owner)

    async def agent(prompt: str, workspace: str) -> str:
        from companion.aerith_agent import run_aerith_agent
        url, model, headers = _route()
        response, _history, _metrics = await run_aerith_agent(
            owner=config.owner, message=prompt, endpoint_url=url, model=model,
            headers=headers, workspace=workspace,
        )
        return response

    def llm(prompt: str) -> str:
        from src.llm_core import llm_call
        url, model, headers = _route()
        return llm_call(url, model, [{"role": "user", "content": prompt}], headers=headers,
                        temperature=0.3, max_tokens=1500)

    try:
        from src.constants import DEEP_RESEARCH_DIR
    except Exception:  # pragma: no cover
        DEEP_RESEARCH_DIR = ""
    _maintainer = AerithMaintainer(config, agent=agent, llm=llm, research_dir=DEEP_RESEARCH_DIR)
    return _maintainer
