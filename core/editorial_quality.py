"""Editorial text normalization and quality gates for generated news copy."""

from __future__ import annotations

import re

SERBIAN_COPY_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[Ii]zvještaj([a-zčćžšđ]*)\b"), r"izveštaj\1"),
    (re.compile(r"\bizvještaj([a-zčćžšđ]*)\b", re.IGNORECASE), r"izveštaj\1"),
    (re.compile(r"\bizvještav([a-zčćžšđ]*)\b", re.IGNORECASE), r"izveštav\1"),
    (re.compile(r"\b[Ii]zvješтај([a-zčćžšđ]*)\b"), r"izveštaj\1"),
    (re.compile(r"\bizgorjele\b", re.IGNORECASE), "izgorele"),
    (re.compile(r"\bnarativa\b", re.IGNORECASE), "narativ"),
    (re.compile(r"\bsublimat\b", re.IGNORECASE), "pregled"),
    (re.compile(r"\bCelosno\b"), "Celo"),
    (re.compile(r"\bcelosno\b"), "celo"),
)


WEAK_EDITORIAL_ABSTRACTIONS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bglobalne i lokalne ose napetosti\b", re.IGNORECASE),
    re.compile(r"\bpreplitanje unutrašnjih i spoljašnjih napetosti\b", re.IGNORECASE),
    re.compile(r"\blegitimnost institucija\b", re.IGNORECASE),
    re.compile(r"\bširi trend\b", re.IGNORECASE),
    re.compile(r"\bšira neizvesnost\b", re.IGNORECASE),
    re.compile(r"\bsimbol šire\b", re.IGNORECASE),
    re.compile(r"\bukazuje na širi\b", re.IGNORECASE),
    re.compile(r"\bugrožava stabilnost\b", re.IGNORECASE),
    re.compile(r"\bugrožavaju stabilnost\b", re.IGNORECASE),
    re.compile(r"\bgubitak institucionalnog uticaja\b", re.IGNORECASE),
    re.compile(r"\bkomercijalizacije i medijskog spektakla\b", re.IGNORECASE),
    re.compile(r"\bпоширок тренд\b", re.IGNORECASE),
    re.compile(r"\bпоширока неизвесност\b", re.IGNORECASE),
    re.compile(r"\bлегитимноста на институциите\b", re.IGNORECASE),
)


UNPROFESSIONAL_EDITORIAL_ARTIFACTS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\buredničk(?:i|og|om)\s+centar\b", re.IGNORECASE),
    re.compile(r"\bredakcijsk(?:i|og|om)\s+centar\b", re.IGNORECASE),
    re.compile(r"\bуредничкиот\s+центар\b", re.IGNORECASE),
    re.compile(r"\bуреднички\s+центар\b", re.IGNORECASE),
    re.compile(r"\bредакцискиот\s+центар\b", re.IGNORECASE),
    re.compile(r"\bредакциски\s+центар\b", re.IGNORECASE),
)


def normalize_serbian_editorial_text(text: str) -> str:
    """Normalize common Serbian/Bosnian/Croatian leaks in generated Serbian copy."""
    clean = str(text or "")
    for pattern, replacement in SERBIAN_COPY_REPLACEMENTS:
        clean = pattern.sub(replacement, clean)
    return re.sub(r"[ \t]{2,}", " ", clean).strip()


def weak_editorial_abstraction_count(text: str) -> int:
    """Count broad editorial claims that usually read as unsupported AI abstraction."""
    value = str(text or "")
    return sum(1 for pattern in WEAK_EDITORIAL_ABSTRACTIONS if pattern.search(value))


def has_unprofessional_editorial_artifact(text: str) -> bool:
    """Detect invented newsroom/meta entities that read like AI artifacts."""
    value = str(text or "")
    return any(pattern.search(value) for pattern in UNPROFESSIONAL_EDITORIAL_ARTIFACTS)


def has_repetitive_media_framing(text: str) -> bool:
    """Detect mechanical repetition of source-comparison phrasing."""
    value = str(text or "").casefold()
    repeated_markers = (
        "mediji se razlikuju",
        "izvori se razlikuju",
        "javno važno",
        "ostaje nejasno",
        "се разликуваат",
        "јавно важно",
        "останува нејасно",
    )
    return any(value.count(marker) > 2 for marker in repeated_markers)
