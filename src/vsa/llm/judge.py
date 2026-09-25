"""LLM judge over the top candidate objects (HANDOVER §10, ADR-002, ADR-003).

The model never searches and never names a field: it only picks ``candidate_id``s from
a list built from the dictionary. Unknown ids are dropped and counted (hallucination
indicator, §11). Scores combine as ``w_rule × rule + w_llm × llm``; an object the judge
does not pick gets llm = 0. Any failure returns ``None`` and the caller keeps the rule
result (ADR-008).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from vsa.llm.client import LLMClient
from vsa.llm.prompts import JUDGE_SCHEMA, JUDGE_SYSTEM, judge_user
from vsa.models import FlagKind, ObjectMatch

log = logging.getLogger(__name__)

MAX_COLUMNS_PER_CANDIDATE = 5
DESCRIPTION_CHARS = 220


@dataclass(slots=True)
class JudgeVerdict:
    confidence: float
    reason: str
    caveat: str
    usage: str


@dataclass(slots=True)
class JudgeResult:
    verdicts: dict[str, JudgeVerdict] = field(default_factory=dict)  # object_key -> verdict
    unknown_ids: int = 0
    seconds: float = 0.0


def candidate_payload(candidates: Sequence[ObjectMatch]) -> tuple[str, dict[str, str]]:
    """Compact JSON of the candidates and the id -> object_key map."""
    rows = []
    ids: dict[str, str] = {}
    for i, m in enumerate(candidates, 1):
        cid = f"t{i}"
        ids[cid] = m.object_key
        columns = []
        for h in m.columns[:MAX_COLUMNS_PER_CANDIDATE]:
            desc = h.col.description
            if len(desc) > DESCRIPTION_CHARS:
                desc = desc[:DESCRIPTION_CHARS].rsplit(" ", 1)[0] + "…"
            entry: dict[str, object] = {"alan": h.col.column, "aciklama": desc}
            if h.col.has_flag(FlagKind.MODEL_ESTIMATED):
                entry["uyari"] = "açıklama doğrulanmamış model tahmini"
            columns.append(entry)
        rows.append(
            {
                "candidate_id": cid,
                "tablo": m.object_key,
                "veri_seti": ", ".join(m.dataset_groups) or "-",
                "alanlar": columns,
            }
        )
    return json.dumps(rows, ensure_ascii=False, indent=1), ids


def judge(query: str, candidates: Sequence[ObjectMatch], client: LLMClient) -> JudgeResult | None:
    if not client.available or not candidates:
        return None
    payload, ids = candidate_payload(candidates)
    reply = client.chat_json(
        JUDGE_SYSTEM, judge_user(query, payload), JUDGE_SCHEMA, max_tokens=1200
    )
    if reply is None:
        return None
    result = JudgeResult()
    for item in reply.get("matches", []) or []:
        if not isinstance(item, dict):
            continue
        key = ids.get(str(item.get("candidate_id", "")).strip())
        if key is None:
            result.unknown_ids += 1
            log.warning("LLM bilinmeyen aday döndürdü: %s", item.get("candidate_id"))
            continue
        try:
            conf = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        result.verdicts[key] = JudgeVerdict(
            confidence=max(0.0, min(1.0, conf)),
            reason=str(item.get("reason", "")).strip(),
            caveat=str(item.get("caveat", "")).strip() or "-",
            usage=str(item.get("usage", "")).strip(),
        )
    return result
