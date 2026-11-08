"""One-sentence personalized advisory (P1).

Primary path: **Foundry Local** running a small model (phi-4-mini) on the
Snapdragon NPU/GPU, via the OpenAI-compatible endpoint, with a hard 2 s timeout.
Any failure (Foundry is *preview, no SLA*) -> deterministic **template**
advisory keyed on risk level + top factor.  The system never blocks or crashes
on the LLM.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("vayumitra.advisory")

ADVISORY_SYSTEM_PROMPT = (
    "You are VayuMitra, an asthma-care air-quality assistant. Given a JSON "
    "context of the user's current air readings, risk level and profile, reply "
    "with exactly ONE actionable sentence (max 30 words) telling the user what "
    "to do RIGHT NOW. No preamble, no markdown, no lists."
)

# Templates keyed on (level, top_factor-ish). Kept short and specific.
_TEMPLATES = {
    "critical": {
        "high PM2.5": "Air quality is hazardous now - move indoors, close windows, "
                      "start your purifier and keep your reliever inhaler within reach.",
        "elevated VOC / gas": "Strong fumes detected - leave this area immediately, "
                              "get fresh air and use your reliever inhaler if breathing tightens.",
        "default": "Critical air-quality event - move to clean air now and keep your "
                   "reliever inhaler ready.",
    },
    "high": {
        "high PM2.5": "Pollution is climbing fast - limit exertion, head indoors and "
                      "pre-empt symptoms with your prescribed steps.",
        "humidity out of comfort range": "Humidity is aggravating - move somewhere drier "
                                         "and slow your breathing; keep medication nearby.",
        "default": "Risk is high - reduce activity, prefer indoor clean air and monitor "
                   "your breathing closely.",
    },
    "moderate": {
        "default": "Conditions are worsening - take it easy, avoid strenuous outdoor "
                   "activity and keep your inhaler handy.",
    },
    "low": {
        "default": "Air quality is comfortable - normal activity is fine; carry your "
                   "reliever inhaler as usual.",
    },
}


def template_advisory(level: str, top_factors: List[str]) -> str:
    by_level = _TEMPLATES.get(level, _TEMPLATES["low"])
    top = top_factors[0] if top_factors else "default"
    return by_level.get(top, by_level["default"])


class AdvisoryEngine:
    """Lazy Foundry Local client; falls back to templates on any error."""

    def __init__(self, enabled: bool, model_alias: str = "phi-4-mini") -> None:
        self.enabled = enabled
        self.model_alias = model_alias
        self._client = None
        self._model_id: Optional[str] = None
        self._init_attempted = False

    def _ensure_client(self) -> bool:
        if self._client is not None:
            return True
        if self._init_attempted:
            return False
        self._init_attempted = True
        try:
            import openai
            from foundry_local import FoundryLocalManager  # type: ignore

            m = FoundryLocalManager(self.model_alias)  # auto-selects NPU variant
            self._client = openai.OpenAI(base_url=m.endpoint, api_key=m.api_key)
            self._model_id = m.get_model_info(self.model_alias).id
            log.info("Foundry Local ready: %s", self._model_id)
            return True
        except Exception as e:
            log.info("Foundry Local unavailable (%s) -> template advisories", e)
            self._client = None
            return False

    def advise(self, ctx: Dict, level: str, top_factors: List[str]) -> Tuple[str, str]:
        """Return ``(advisory_text, source)`` where source is 'llm' or 'template'."""
        if self.enabled and self._ensure_client():
            try:
                import json

                r = self._client.chat.completions.create(
                    model=self._model_id,
                    messages=[
                        {"role": "system", "content": ADVISORY_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(ctx)},
                    ],
                    max_tokens=60,
                    temperature=0.3,
                    timeout=2,
                )
                text = (r.choices[0].message.content or "").strip()
                if text:
                    return text, "llm"
            except Exception as e:
                log.debug("Foundry advisory failed (%s) -> template", e)
        return template_advisory(level, top_factors), "template"
