"""Rules for one dictionary text: no doubt, no hedge, participation-banking wording.

These are the rules the hand-made dictionary was cleaned with (the owner's decisions):

* A Navigator field states what the code shows; a doubting or hedging sentence goes, and what was
  removed is returned so it can be kept outside the fields Navigator reads.
* The explanation speaks participation banking (kar payı, fon kullandırım, katılma hesabı, icare);
  the search terms carry the general banking words people type (faiz, kredi, mevduat, leasing).
  A quoted value is data the code writes and keeps its own spelling.
* A summary lists values only when the code holds them.

Every function is pure and idempotent: running it on its own output changes nothing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

TERMS_SENTENCE = re.compile(r"\s*Eş anlamlılar(?:/aranabilir terimler)?\s*:.*$", re.IGNORECASE | re.DOTALL)
TAG = re.compile(
    r"^\s*\[(?:MODEL TAHMİNİ|ORİJİNAL AÇIKLAMA HATALIYDI|BU OBJEDE FARKLI ANLAMDA)[^\]]*\]\s*",
    re.IGNORECASE,
)
DOUBT = re.compile(
    r"doğrulanmalı\w*|doğrulanması\s+gerek\w*|doğrulanamad\w*|teyit\s+edilmeli\w*|teyit\s+edilmesi\w*|"
    r"beklenmekte\w*|\bbeklenir\b|kesin değil\w*|kesinleşmemiş|muhtemel\w*|şüpheli|"
    r"iş birimi(?:yle| ile)|\bolası\b|kontrol edilmeli\w*|dayanağı (?:yok|bulunma)\w*|bazı durumlarda|"
    r"\byaklaşık\b",
    re.IGNORECASE,
)
HEDGE = re.compile(
    r"\b(?:genellikle|çoğunlukla|genelde|büyük olasılıkla|büyük ihtimalle)\b|"
    r"\b\w+(?:ılabilir|ilabilir|ulabilir|ülabilir)\b(?<!okunabilir)(?<!kullanılabilir)(?<!erişilebilir)|"
    r"\b\w+(?:meyebilir|mayabilir)\b|"
    r"\b(?:olabilir|olmayabilir|içerebilir|kapsayabilir|taşıyabilir|gelebilir|değişebilir|dolabilir)\b",
    re.IGNORECASE,
)
USAGE = re.compile(
    r"(?:analiz\w*|raporlama\w*|karşılaştırma\w*|izlenmesin\w*|takibin\w*)[^.;]*"
    r"(?:temel kırılım\w*|birincil (?:eşleştirme )?anahtar\w*|kullanılır|kullanılmaktadır|imkan tanır|imkân tanır|olanak sağlar)",
    re.IGNORECASE,
)
EXAMPLE = re.compile(r"\s*\((?:ör\.|örn\.|örneğin)\s*([^)]*)\)", re.IGNORECASE)
_AFFIRM = (
    (re.compile(r"\s+olması beklenmektedir\b", re.IGNORECASE), ""),
    (re.compile(r"\s+taşıması beklenmektedir\b", re.IGNORECASE), " taşır"),
    (re.compile(r"\s+göstermesi beklenmektedir\b", re.IGNORECASE), " gösterir"),
)
# A clause splits on ';' (or ', kapsam …') only outside brackets: '(…; ör. a, b)' stays whole.
_OUTSIDE_BRACKETS = r"(?![^()]*\))"
_SENTENCE_END = re.compile(
    r"(?<=[.!?])(?<![Öö]r\.)(?<!vb\.)(?<!bkz\.)(?<!örn\.)\s+(?=[A-ZÇĞİÖŞÜ0-9\[(\"'])"
)

_FAIZ = (
    (re.compile(r"\bfaiz\s+oranı", re.IGNORECASE), "kar payı oranı"),
    (re.compile(r"\bfaizi\b", re.IGNORECASE), "kar payı"),
    (re.compile(r"\bfaiz(?!siz)\b", re.IGNORECASE), "kar payı"),
)
_KEEP_KREDI = r"(?!\s+(?:kart|kayıt|büro|garanti|skor|not|kaybı|kayıp|zarar|sigorta)|\s*/\s*(?:debit|banka))"
_WORDING = (
    (re.compile(r"fon kullandırım kart", re.IGNORECASE), "kredi kart"),
    (re.compile(r"\bkredilerinin\b", re.IGNORECASE), "fon kullandırımlarının"),
    (re.compile(r"\bkredilerin\b", re.IGNORECASE), "fon kullandırımlarının"),
    (re.compile(r"\bkredileri\b", re.IGNORECASE), "fon kullandırımları"),
    (re.compile(r"\bkrediler\b", re.IGNORECASE), "fon kullandırımları"),
    (re.compile(r"\bkredinin\b", re.IGNORECASE), "fon kullandırımının"),
    (re.compile(r"\bkredisinin\b", re.IGNORECASE), "fon kullandırımının"),
    (re.compile(r"\bkredisi\b", re.IGNORECASE), "fon kullandırımı"),
    (re.compile(r"\bkrediye\b", re.IGNORECASE), "fon kullandırımına"),
    (re.compile(r"\bkredi\b" + _KEEP_KREDI, re.IGNORECASE), "fon kullandırım"),
    (re.compile(r"\bvadeli mevduat", re.IGNORECASE), "mevduat"),
    (re.compile(r"(?<!kredili )\bmevduat hesab", re.IGNORECASE), "katılma hesab"),
    (re.compile(r"(?<!kredili )\bmevduatların\b", re.IGNORECASE), "katılma hesaplarının"),
    (re.compile(r"(?<!kredili )\bmevduatlar\b", re.IGNORECASE), "katılma hesapları"),
    (re.compile(r"(?<!kredili )\bmevduatın\b", re.IGNORECASE), "katılma hesabının"),
    (re.compile(r"(?<!kredili )\bmevduatını\b", re.IGNORECASE), "katılma hesabını"),
    (re.compile(r"(?<!tasarruf )(?<!kredili )\bmevduatı\b", re.IGNORECASE), "katılma hesabı"),
    (re.compile(r"(?<!kredili )\bmevduat\b", re.IGNORECASE), "katılma hesabı"),
    (re.compile(r"\bleasing icare\b", re.IGNORECASE), "icare"),
    (re.compile(r"\bleasingin\b", re.IGNORECASE), "icarenin"),
    (re.compile(r"\bleasinge\b", re.IGNORECASE), "icareye"),
    (re.compile(r"\bleasing\b", re.IGNORECASE), "icare"),
)
_DOUBLED = re.compile(r"\b(fon kullandırım\w*|katılma hesab\w*|icare\w*)\s*(?:\(\1\)|/\s*\1)", re.IGNORECASE)
_GENERAL_TERMS = (
    (re.compile(r"\bkar payı oran", re.IGNORECASE), "faiz oranı"),
    (re.compile(r"\bkar payı", re.IGNORECASE), "faiz"),
    (re.compile(r"\bfon kullandırım", re.IGNORECASE), "kredi"),
    (re.compile(r"\bkatılma hesab", re.IGNORECASE), "mevduat"),
    (re.compile(r"\bicare", re.IGNORECASE), "leasing"),
    (re.compile(r"\bicare", re.IGNORECASE), "finansal kiralama"),
)
_QUOTED = re.compile(r"('[^']*')")
_ITEM = r"[^/·:(),]{1,30}"
_BRACKET = re.compile(r"\s*\(([^()]*)\)")
_LITERAL = re.compile(r"'([^'\n]{2,60})'")


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text.strip()) if s]


def _squash(text: str) -> str:
    return re.sub(r"\s{2,}", " ", text).strip()


def _keep_case(found: str, replacement: str) -> str:
    """'Leasing' at a sentence start becomes 'İcare', not 'icare'."""

    if found[:1].isupper() and replacement[:1].islower():
        head = {"i": "İ", "ı": "I"}.get(replacement[0], replacement[0].upper())
        return head + replacement[1:]
    return replacement


def capital(text: str) -> str:
    """A description opens with a capital, unless it opens with a name like iOS."""

    if text[:1].islower() and not re.match(r"[a-z]+[A-Z]", text):
        return _keep_case("X", text)
    return text


def _affirmed(sentence: str) -> str:
    first = sentence.split(";")[0]
    for pattern, replacement in _AFFIRM:
        first = pattern.sub(replacement, first)
    first = re.split(r",\s*(?:kapsam|içerik|alan)\b", first)[0]
    return "" if DOUBT.search(first) or HEDGE.search(first) else first.strip(" ,;.") + "."


def remove_doubt(text: str) -> tuple[str, list[str]]:
    """Doubting sentences go; their plain clauses stay. A text of doubt only keeps its claim."""

    removed: list[str] = []
    tag = TAG.match(text)
    if tag:
        removed.append(tag.group(0).strip())
        text = text[tag.end() :]
    kept: list[str] = []
    splitter = re.compile(r"(?:;|,\s*(?=(?:kapsam|alan|değer|bu|içerik)\b))" + _OUTSIDE_BRACKETS)
    for sentence in sentences(text):
        if not DOUBT.search(sentence):
            kept.append(sentence)
            continue
        removed.append(sentence)
        good = [c.strip() for c in splitter.split(sentence.rstrip(" .")) if c.strip() and not DOUBT.search(c)]
        if good:
            kept.append("; ".join(good).rstrip(" ,;") + ".")
    if not kept:
        for sentence in removed:
            plain = "" if sentence.startswith("[") else _affirmed(sentence)
            if plain:
                kept.append(plain)
                break
    return _squash(" ".join(kept)), removed


def remove_hedges(text: str, sources: str = "") -> tuple[str, list[str]]:
    """Hedging words, usage boilerplate and examples the sources do not hold go."""

    removed: list[str] = []
    sources = sources.casefold()

    def example(match: re.Match[str]) -> str:
        tokens = [
            t.strip(" '\"")
            for t in re.split(r"[,/;]| veya | ve ", match.group(1))
            if len(t.strip(" '\"")) > 1
        ]
        if any(token.casefold() in sources for token in tokens):
            return match.group(0)
        removed.append(match.group(0).strip())
        return ""

    text = EXAMPLE.sub(example, text)

    def aside(match: re.Match[str]) -> str:
        removed.append(match.group(0).strip())
        return ""

    text = re.sub(
        r"\s*\([^)]*\b(?:genellikle|olabilir|genelde|çoğunlukla)\b[^)]*\)", aside, text, flags=re.IGNORECASE
    )
    text = re.sub(r",?\s*\bgenellikle\s+", " ", text, flags=re.IGNORECASE)
    kept: list[str] = []
    for sentence in sentences(text):
        usage = USAGE.search(sentence) and not re.search(r"\d|'[^']+'", sentence)
        if not usage and not HEDGE.search(sentence):
            kept.append(sentence)
            continue
        removed.append(sentence)
        pattern = r"(?:;|\s+—\s+)" + _OUTSIDE_BRACKETS
        good = []
        for clause in re.split(pattern, sentence.rstrip(" .")):
            clause = clause.strip()
            if not clause or (usage and USAGE.search(clause)):
                continue
            if HEDGE.search(clause):
                # 'şubeden alınır ve … farklı olabilir': the plain first part is a statement.
                head = re.split(r"\s+ve\s+" + _OUTSIDE_BRACKETS, clause)[0].strip(" ,")
                if head == clause or HEDGE.search(head) or len(head.split()) < 3:
                    continue
                clause = head
            good.append(clause)
        if good:
            kept.append("; ".join(good) + ".")
    if not kept:
        return _squash(text), []
    return _squash(" ".join(kept)), removed


_NAME_BEFORE = re.compile(r"(?:^|[\s(])[A-ZÇĞİÖŞÜ][\wçğıöşüÇĞİÖŞÜ]*\s+$")


def _reworded(match: re.Match[str], replacement: str, text: str) -> str:
    """A capitalised word after a capitalised word is part of a name ('İşletme Kredileri Grubu')."""

    found = match.group(0)
    if found[:1].isupper() and _NAME_BEFORE.search(text[: match.start()]):
        return found
    return _keep_case(found, match.expand(replacement))


def participation_wording(text: str) -> str:
    """faiz → kar payı, kredi → fon kullandırım, mevduat → katılma hesabı, leasing → icare."""

    pieces = _QUOTED.split(text)
    for index in range(0, len(pieces), 2):
        for pattern, replacement in (*_FAIZ, *_WORDING):
            pieces[index] = pattern.sub(
                lambda m, r=replacement, piece=pieces[index]: _reworded(m, r, piece), pieces[index]
            )
    text = "".join(pieces)
    text = _DOUBLED.sub(r"\1", text)
    return re.sub(r"\bkatılıma hesap", "katılma hesap", text, flags=re.IGNORECASE)


def clean_description(text: str, sources: str = "") -> tuple[str, list[str]]:
    """The whole description pipeline; the removed pieces come back for the review column."""

    text = TERMS_SENTENCE.sub("", " ".join((text or "").split()))
    text, removed = remove_doubt(text)
    text, hedges = remove_hedges(text, sources)
    text = capital(participation_wording(text))
    return _squash(text), removed + hedges


def split_terms(value: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,;]", value or "") if t.strip()]


def clean_synonyms(synonyms: str, description: str = "") -> str:
    """Search terms: no hedged term, no duplicate, and the general banking word beside ours."""

    seen: set[str] = set()
    terms: list[str] = []
    for term in split_terms(synonyms):
        term = term.rstrip(".")
        # Search folds case, so 'Transaction Label' beside 'transaction label' is harmless: only an
        # exact repeat goes.
        if DOUBT.search(term) or HEDGE.search(term) or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    if terms and description:
        for pattern, word in _GENERAL_TERMS:
            if pattern.search(description) and not any(word.casefold() in t.casefold() for t in terms):
                seen.add(word)
                terms.append(word)
    return ", ".join(terms)


def code_literals(code: Iterable[str]) -> str:
    """The quoted values code writes ('Yatırım Fonu', 'TRY'): a summary may list them."""

    return " ".join(m for body in code for m in _LITERAL.findall(body or ""))


def _unsupported(items: list[str], support: str) -> bool:
    items = [i.strip() for i in items if i.strip()]
    if len(items) < 2:
        return False
    hits = sum(1 for i in items if i.casefold().split()[-1][:5] in support)
    return hits / len(items) < 0.5


def drop_unsupported_lists(summary: str, support: str) -> str:
    """Value lists (a/b/c, or several values in brackets) that neither evidence nor code holds."""

    support = support.casefold()

    def bracket(match: re.Match[str]) -> str:
        items = re.split(r"\s*[/,]\s*", match.group(1))
        return "" if len(items) >= 2 and _unsupported(items, support) else match.group(0)

    summary = _BRACKET.sub(bracket, summary)
    kept: list[str] = []
    for part in summary.split("·"):
        part = part.strip()
        bare = part.split(":", 1)[-1]
        if re.fullmatch(rf"\s*(?:{_ITEM}/){{2,}}{_ITEM}\s*", bare) and _unsupported(bare.split("/"), support):
            if ":" not in part:
                continue
            part = part.split(":", 1)[0].strip()
        if part:
            kept.append(part)
    return " · ".join(kept)


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut.rsplit(" ", 1)[0].rstrip(" ·,;:(") if " " in cut else cut


def clean_summary(summary: str, support: str = "", limit: int = 70) -> str:
    """A short label: no doubt, no hedge, no example, no value list the code does not hold."""

    summary = " ".join((summary or "").split())
    summary = EXAMPLE.sub("", summary)
    parts = [p.strip() for p in summary.split("·")]
    summary = " · ".join(p for p in parts if p and not DOUBT.search(p) and not HEDGE.search(p))
    cleaned = drop_unsupported_lists(summary, support) or summary
    return clip(cleaned, limit)
