"""Fast typed-decision backend for the agent's "what should I do this
turn" choice — the one decision every turn needs regardless of whether
anything gets generated. A full LLM call for a 6-way multiple choice is
overkill; Jev/Laya answer it directly as calibrated probabilities.

Prefers the hosted Jev API (TYPESAFE_API_KEY) since it needs no local
download. Falls back to a local Laya model (pip install laya) if no key
is set. Falls back to None — caller should use the LLM instead — if
neither is available, so this is a pure optimization, never a hard
dependency.
"""
import os

import httpx

TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY")
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"

ACTION_CRITERIA = {
    "claim_task": "claim an open task matching this agent's role, when one exists and the agent owns nothing unfinished yet",
    "propose_task": "propose a new task because no open task matches this agent's role",
    "write_code": "write/commit code for a task the agent already owns and hasn't finished",
    "update_task_status": "mark an owned task done because its code is already committed",
    "post_message": "post a short discussion message — a question, status update, or coordination note",
    "noop": "do nothing this turn",
}

_laya_router = None
_laya_unavailable = False


def _laya():
    global _laya_router, _laya_unavailable
    if _laya_unavailable:
        return None
    if _laya_router is None:
        try:
            from laya import Router

            _laya_router = Router()
        except Exception:
            _laya_unavailable = True
            return None
    return _laya_router


def choose_action(state_text: str) -> str | None:
    """Returns one of ACTION_CRITERIA's keys, or None if no typed-decision
    backend is configured/installed (caller falls back to an LLM call)."""
    questions = {
        "action": {
            "type": "choice",
            "instructions": "What should this agent do next?",
            "criteria": ACTION_CRITERIA,
        }
    }

    if TYPESAFE_API_KEY:
        try:
            resp = httpx.post(
                TYPESAFE_URL,
                headers={"Authorization": f"Bearer {TYPESAFE_API_KEY}"},
                json={"state": state_text, "model": "jev-latest", "questions": questions},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()["answers"]["action"]["choice"]
        except Exception:
            pass  # fall through to a local model, then to None

    router = _laya()
    if router:
        try:
            result = router.predict(state_text, questions)
            return result["answers"]["action"]["choice"]
        except Exception:
            pass

    return None
