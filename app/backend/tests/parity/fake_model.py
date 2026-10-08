"""The deterministic fake analyst model of the parity test. Standard library only.

Both sides run this very code. Every reply is built from the prompt (the catalog ids, the
hints, the material's tables and columns, the look-alike fields) and from choices derived
from the SHA-256 digest of the question, so the same question always gets the same reply.
The replies deliberately exercise the checks of the analyst flow: unknown ids, table names in
place of ids, made-up and lower-case columns, low and malformed confidences, catalog ids and
"vX (vX)" echoes in free text, sentences naming tables that do not exist, typo remarks, the
core concept fields in every combination, verdict and missing-part mixes, and notes naming
real and made-up look-alike fields. Scenarios end a question in each way the flow can end.

A side wraps the core in an adapter for its own model port and turns the failure kinds below
into its own failure form (the source's ``last_error`` text, the target's failure class).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

MODEL = "fake-analyst"

# Scenarios a question of the parity set can carry.
NORMAL = "normal"
STEP1_FAILED = "step1_failed"
STEP2_FAILED = "step2_failed"
NO_CANDIDATES = "no_candidates"
CONTEXT_EXCEEDED = "context_exceeded"
TIMEOUT = "timeout"
CONNECTION_REFUSED = "connection_refused"
HTTP_500 = "http_500"
SERVER_DOWN = "server_down"
SERVER_UNAUTHORIZED = "server_unauthorized"
NO_MODEL = "no_model"
EMPTY_DICTIONARY = "empty_dictionary"
SCENARIOS = (
    NORMAL,
    STEP1_FAILED,
    STEP2_FAILED,
    NO_CANDIDATES,
    CONTEXT_EXCEEDED,
    TIMEOUT,
    CONNECTION_REFUSED,
    HTTP_500,
    SERVER_DOWN,
    SERVER_UNAUTHORIZED,
    NO_MODEL,
    EMPTY_DICTIONARY,
)
# Scenarios whose "Analiz yapılamadı" reason question-analysis Requirement 5 changes on purpose
# (the source's text carries the server address or the server's error body).
CHANGED_REASON = frozenset({SERVER_DOWN, HTTP_500})

# Failure kinds of a chat call and of the server check; each side maps them to its port.
FAIL_INVALID_JSON = "invalid_json"
FAIL_CONTEXT = "context_exceeded"
FAIL_TIMEOUT = "timeout"
FAIL_CONNECTION = "connection_refused"
FAIL_HTTP_500 = "http_500"
DOWN_CONNECT = "connect_refused"
DOWN_UNAUTHORIZED = "unauthorized"

_STEP1_FAILURE = {
    STEP1_FAILED: FAIL_INVALID_JSON,
    CONTEXT_EXCEEDED: FAIL_CONTEXT,
    CONNECTION_REFUSED: FAIL_CONNECTION,
}
_STEP2_FAILURE = {STEP2_FAILED: FAIL_INVALID_JSON, TIMEOUT: FAIL_TIMEOUT, HTTP_500: FAIL_HTTP_500}

_CATALOG = re.compile(r"^(T\d+) \| (\S+) \| ", re.MULTILINE)
_HINT = re.compile(r"^- (T\d+) (\S+) \(kavramlar: ", re.MULTILINE)
_HEADER = re.compile(r"^### (T\d+) · (\S+) · Talep eden birim: ", re.MULTILINE)
_COLUMN = re.compile(r"^- ([^\s:\[]+)(?: \[[^\]]*\])*: ", re.MULTILINE)
_SIMILAR = re.compile(r"^- ([^\s:\[.]+\.[^\s:\[.]+\.[^\s:\[.]+)\.([^\s:\[]+)", re.MULTILINE)
_WORD = re.compile(r"\w{3,}")

T = TypeVar("T")


class Chooser:
    """Choices derived from a seed by SHA-256: the same on every Python version."""

    def __init__(self, seed: str) -> None:
        self.seed = seed
        self.n = 0

    def number(self, k: int) -> int:
        self.n += 1
        digest = hashlib.sha256(f"{self.seed}#{self.n}".encode()).digest()
        return int.from_bytes(digest[:8], "big") % k

    def chance(self, num: int, den: int) -> bool:
        return self.number(den) < num

    def pick(self, items: Sequence[T]) -> T:
        return items[self.number(len(items))]

    def subset(self, items: Sequence[T], k: int) -> list[T]:
        pool = list(items)
        out: list[T] = []
        while pool and len(out) < k:
            out.append(pool.pop(self.number(len(pool))))
        return out


class FakeAnalyst:
    """The core: records every call and answers it, or names the failure of the call."""

    model = MODEL

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Mapping[str, Any], int]] = []
        self.query = ""
        self.scenario = NORMAL

    def begin(self, query: str, scenario: str) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"bilinmeyen senaryo: {scenario}")
        self.calls = []
        self.query = query
        self.scenario = scenario

    @property
    def available(self) -> bool:
        return self.scenario != NO_MODEL

    def health(self) -> str:
        """ "" when the server answers, else the kind of failure."""
        if self.scenario == SERVER_DOWN:
            return DOWN_CONNECT
        if self.scenario == SERVER_UNAUTHORIZED:
            return DOWN_UNAUTHORIZED
        return ""

    def reply(
        self, system: str, user: str, schema: Mapping[str, Any], max_tokens: int
    ) -> tuple[dict[str, Any] | None, str]:
        """(reply, "") or (None, failure kind)."""
        self.calls.append((system, user, schema, max_tokens))
        first = "candidates" in schema.get("properties", {})
        failure = (_STEP1_FAILURE if first else _STEP2_FAILURE).get(self.scenario, "")
        if failure:
            return None, failure
        seed = hashlib.sha256(self.query.encode("utf-8")).hexdigest()
        chooser = Chooser(f"{seed}/{1 if first else 2}")
        if first:
            return self._shortlist(system, user, chooser), ""
        return self._report(user, chooser), ""

    # ------------------------------------------------------------------ step 1

    def _shortlist(self, system: str, user: str, c: Chooser) -> dict[str, Any]:
        catalog = dict(_CATALOG.findall(system))
        hinted = list(dict.fromkeys(t for t, _ in _HINT.findall(user)))
        pool = hinted or list(catalog)
        words = _WORD.findall(self.query)
        interpretation = c.pick(["", f"Talep {len(words)} kelimeyle {words[:1]} soruyor."])
        if self.scenario == NO_CANDIDATES:
            return {
                "interpretation": interpretation,
                "candidates": [],
                "confusables": [],
                "search_terms": words[:3],
                "families": [],
            }
        chosen = c.subset(pool, 1 + c.number(8))
        candidates: list[Any] = []
        for tid in chosen:
            form = c.number(10)
            key = catalog.get(tid, "")
            if form == 0 and key:
                ident = key.rsplit(".", 1)[-1]
            elif form == 1 and key:
                ident = key
            elif form == 2:
                ident = f"`{tid}`"
            else:
                ident = tid
            candidates.append({"id": ident, "why": f"{tid} talebe uyuyor"})
        if c.chance(1, 2):
            candidates.append({"id": "T9999", "why": "katalogda yok"})
        if c.chance(1, 5):
            candidates.append("geçersiz öğe")
        if candidates and c.chance(1, 6):
            candidates.append(candidates[0])
        rest = [t for t in pool if t not in chosen]
        confusables: list[Any] = [
            {"id": t, "why": "benzer ama yanıltıcı"} for t in c.subset(rest, c.number(4))
        ]
        if chosen and c.chance(1, 4):
            confusables.append({"id": chosen[0], "why": "aday da"})
        if c.chance(1, 4):
            confusables.append({"id": "T8888", "why": "katalogda yok"})
        terms: list[Any] = [*words[: c.number(9)], *c.subset(_COLUMN_WORDS, c.number(6))]
        if c.chance(1, 4):
            terms += ["", "  ", 42]
        reply: dict[str, Any] = {
            "interpretation": interpretation,
            "candidates": candidates,
            "confusables": confusables,
            "search_terms": terms if c.number(8) else "tek metin",
            "families": self._families(catalog, words, c),
        }
        if c.chance(1, 10):
            del reply["families"]
        return reply

    @staticmethod
    def _families(catalog: Mapping[str, str], words: Sequence[str], c: Chooser) -> list[Any]:
        families: list[Any] = []
        names = [k.rsplit(".", 1)[-1].lstrip("v") for k in catalog.values()]
        for i in range(c.number(5)):
            terms = [*c.subset(names, 1 + c.number(2)), *c.subset(_COLUMN_WORDS, c.number(3))]
            terms += list(words[i : i + c.number(3)])
            families.append({"name": c.pick(["", f"aile {i + 1}", "kart bilgisi"]), "terms": terms})
        if c.chance(1, 4):
            families.append({"name": "boş aile", "terms": []})
        if c.chance(1, 6):
            families.append("aile değil")
        return families

    # ------------------------------------------------------------------ step 2

    def _report(self, user: str, c: Chooser) -> dict[str, Any]:
        material, _, similar_part = user.partition("\n\nKARIŞTIRILABİLİR ALANLAR")
        tables = _HEADER.findall(material)
        columns: dict[str, list[str]] = {}
        for (tid, _), body in zip(tables, _HEADER.split(material)[3::3], strict=True):
            columns[tid] = _COLUMN.findall(body)
        similar = [f"{key}.{col}" for key, col in _SIMILAR.findall(similar_part)]
        chosen = c.subset(tables, 1 + c.number(6))
        recs: list[Any] = [self._recommendation(t, k, columns[t], c) for t, k in chosen]
        if recs and c.chance(1, 12):
            recs.append(dict(recs[0]))
        if c.chance(1, 10):
            recs.append("öneri değil")
        first_tid, first_key = chosen[0] if chosen else ("T1", "DB.S.vYok")
        first_obj = first_key.rsplit(".", 1)[-1]
        first_col = (columns.get(first_tid) or ["Kolon"])[0]
        reply: dict[str, Any] = {
            "verdict": c.pick(
                [
                    "VAR",
                    "VAR",
                    "VAR",
                    "KISMEN VAR",
                    "KISMEN VAR",
                    "KISMEN VAR",
                    "BULUNAMADI",
                    "YOK",
                    "",
                ]
            ),
            "summary": self._summary(first_key, first_obj, first_tid, c),
            "recommendations": recs,
            "design": self._design(chosen, c),
            "attention": [
                *c.subset(
                    [
                        "Dept/Debt yazım hatasına dikkat.",
                        f"{first_obj}.{first_col} dikkatle yorumlanmalı.",
                        "Kapsam farkı olabilir.",
                        f"{first_tid} tablosu (ör. aylık) güncellenir.",
                        "SYNDM.ZZZ.vHayalet tablosu kullanılmamalı.",
                    ],
                    c.number(5),
                )
            ],
            "notes": self._notes(similar, first_obj, first_col, c),
            "missing": c.subset(
                ["kart rengi geçmişi", "", "şube kırılımı", "aylık seri", "hane geliri"],
                c.number(6),
            ),
        }
        self._core(reply, chosen, columns, c)
        if c.chance(1, 8):
            del reply["verdict"]
        return reply

    @staticmethod
    def _recommendation(tid: str, key: str, cols: Sequence[str], c: Chooser) -> dict[str, Any]:
        obj = key.rsplit(".", 1)[-1]
        picked = c.subset(cols, 1 + c.number(6))
        names: list[Any] = list(picked)
        if names and c.chance(1, 3):
            names[0] = str(names[0]).lower()
        if c.chance(1, 3):
            names.append("UydurmaAlan")
        if names and c.chance(1, 4):
            names[-1] = f"{tid}.{names[-1]}"
        if picked and c.chance(1, 5):
            names.append(f"{key}.{picked[0]}")
        if c.chance(1, 9):
            names = []
        elif c.chance(1, 10):
            names = ["YokKolon1", "YokKolon2"]
        col = picked[0] if picked else "Kolon"
        form = c.number(12)
        ident = obj if form == 0 else key if form == 1 else "T9999" if form == 2 else tid
        reason = f"{tid} tablosu {obj} kapsamında kayıt tutar."
        if c.chance(1, 2):
            reason += f" {tid} ({obj}) ana kaynaktır."
        if c.chance(1, 3):
            reason += " SYNDM.ZZZ.vUydurmaTablo tablosu da bakılabilir."
        if c.chance(1, 2):
            reason += f" {col} alanı talebi karşılar (ör. aylık kırılım). Vb. alanlar da var!"
        if c.chance(1, 6):
            reason = "=1+1 " + reason
        rec: dict[str, Any] = {
            "id": ident,
            "covers": c.pick(["", f"{obj} künyesi: {col}", "Kart künyesi: statü, limit"]),
            "columns": names,
            "reason": reason,
            "caveat": c.pick(
                [
                    "-",
                    "",
                    f"{col} alanı dikkatle kullanılmalı.",
                    f"{col} ek kart sahibidir. Kolon adında yazım hatası var.",
                    f"Dept/Debt typo: {col}. {col} snapshot değerdir.",
                    f"{tid}.{col} hesap seviyesindedir.",
                ]
            ),
            "usage": c.pick(["", f"{obj} isteniyorsa ilk tercih.", "Tamamlayıcı kaynak."]),
            "confidence": c.pick(
                [
                    0.92,
                    0.88,
                    0.85,
                    0.81,
                    0.78,
                    0.7,
                    0.66,
                    0.55,
                    0.5,
                    0.49,
                    0.3,
                    1.2,
                    -0.1,
                    "0.75",
                    "yüksek",
                    None,
                ]
            ),
        }
        if c.chance(1, 15):
            del rec["confidence"]
        return rec

    @staticmethod
    def _summary(key: str, obj: str, tid: str, c: Chooser) -> str:
        prefix = c.pick(["VAR.", "KISMEN VAR —", "BULUNAMADI:", "", "YOK.", "VAR"])
        body = [
            f"Ana kaynak {key}.",
            f"{obj} (ör. kart bazlı) kullanılmalı.",
            "SYNDM.ZZZ.vHayalet ayrıca bakılmalı.",
            f"{tid} tablosu da var.",
            "Talep kısmen karşılanıyor!",
        ]
        return " ".join([prefix, *c.subset(body, 1 + c.number(5))]).strip()

    @staticmethod
    def _design(chosen: Sequence[tuple[str, str]], c: Chooser) -> list[Any]:
        if not chosen:
            return []
        t0, k0 = chosen[0]
        lines: list[Any] = [f"Tek tablo yeterli: {t0} ({k0.rsplit('.', 1)[-1]})."]
        if len(chosen) > 1:
            t1 = chosen[1][0]
            lines.append(f"{t0} + {t1}, CustomerPartyId üzerinden birleştirilir.")
        if c.chance(1, 4):
            lines.append("SYNDM.ZZZ.vHayalet ile birleştirilir.")
        if c.chance(1, 6):
            lines.append("")
        return c.subset(lines, c.number(len(lines) + 1))

    @staticmethod
    def _notes(similar: Sequence[str], obj: str, col: str, c: Chooser) -> list[Any]:
        real = c.pick(similar) if similar else f"SYNDM.ZZZ.{obj}.{col}"
        notes: list[Any] = [
            {"scope": "Uyarı", "title": "Yanıltıcı alan", "text": f"{real} farklı bir kavramdır."},
            {"scope": "Top 5 dışı", "title": "Başka aday", "text": f"{real} alanı da var."},
            {"scope": "Top 5 dışı", "title": "Uydurma", "text": "SYNDM.ZZZ.vHayalet.Kolon var."},
            {"scope": "", "title": "", "text": f"{obj} için netleştirme gerekir."},
            {"scope": "Kapsam", "title": "Boş", "text": ""},
            {"scope": "Türetme", "title": "T12 hesabı", "text": "T12 (vX) oranı türetilir."},
            "not değil",
        ]
        return c.subset(notes, c.number(len(notes) + 1))

    @staticmethod
    def _core(
        reply: dict[str, Any],
        chosen: Sequence[tuple[str, str]],
        columns: Mapping[str, Sequence[str]],
        c: Chooser,
    ) -> None:
        def ref(i: int) -> str:
            tid = chosen[i][0]
            cols = columns.get(tid) or ["Kolon"]
            return f"{tid}.{cols[c.number(len(cols))]}"

        form = c.number(14)  # 9-13: a valid core column, the most common reply
        if form == 0 or not chosen:
            return  # an older reply: no core fields at all
        reply["core_concept"] = c.pick(["kart limit doluluğu", "", "hane geliri"])
        if form == 1 or form > 8:
            reply.update(core_found=True, core_columns=[ref(0)])
        elif form == 2:
            reply.update(core_found=True, core_columns=[ref(len(chosen) - 1)])
        elif form == 3:
            reply.update(core_found=False, core_columns=[])
        elif form == 4:
            reply.update(core_found=True, core_columns=[])
        elif form == 5:
            reply.update(core_found=True, core_columns=[f"{chosen[0][0]}.UydurmaAlan"])
        elif form == 6:
            reply.update(core_found=True, core_columns=["T9999.Kolon", ""])
        elif form == 7:
            refs = [ref(i) for i in range(len(chosen))]
            reply.update(core_found=True, core_columns=[*refs, refs[-1].lower()])
        else:
            reply.update(core_columns=[ref(0)])


_COLUMN_WORDS = (
    "Limit",
    "Period",
    "Amount",
    "Tutar",
    "Bakiye",
    "Score",
    "Tenure",
    "Sector",
    "Card",
    "Risk",
    "kıdem",
    "mevduat",
    "işlem",
    "PD",
    "KKB",
)
