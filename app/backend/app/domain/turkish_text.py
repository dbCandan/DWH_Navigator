"""The application's Turkish folding: the comparison form of names and model-server texts.

Lower-case with Turkish rules (``I`` to ``ı``, ``İ`` to ``i``), then Turkish and a few Latin
letters to ASCII, exactly as the source application's ``fold``. data-dictionary/PRDs/
003-llm-connection uses it for the uniqueness of integration names (Requirement 2) and for reading
a model server's refusal (Requirement 7).
"""

_TURKISH_LOWER = str.maketrans({"I": "ı", "İ": "i"})
_ASCII_FOLD = str.maketrans(
    {
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
        "â": "a",
        "î": "i",
        "û": "u",
        # Not Turkish, but they appear in banking text and must not break a comparison.
        "é": "e",
        "è": "e",
        "ä": "a",
    }
)


def fold(text: str) -> str:
    """Turkish lower case, then ASCII letters; the canonical comparison form of a string."""

    return text.translate(_TURKISH_LOWER).lower().translate(_ASCII_FOLD)
