"""The application's one Turkish folding helper: the comparison form of every Turkish text.

Lower-case with Turkish rules (``I`` to ``ı``, ``İ`` to ``i``), then Turkish and a few Latin
letters to ASCII, exactly as the source application's ``text/normalize.py``. Every Turkish
comparison uses it: the question analysis's normalization (data-dictionary/PRDs/
004-question-analysis), the word lists (002-vocabulary-management), the uniqueness of
integration names and the reading of a model server's refusal (003-llm-connection Requirement 2
and 7) and the password policy's list and name comparison (application-foundation/PRDs/
001-user-accounts Requirement 3). No other module changes letter case.
"""

_TR_LOWER = str.maketrans({"I": "ı", "İ": "i"})

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
        # Not Turkish, but appear in banking text and should not break tokens.
        "é": "e",
        "è": "e",
        "ä": "a",
    }
)


def tr_lower(text: str) -> str:
    """Lowercase with Turkish rules: ``I -> ı`` and ``İ -> i``."""
    return text.translate(_TR_LOWER).lower()


def ascii_fold(text: str) -> str:
    """Fold Turkish characters to ASCII. Expects already-lowercased text."""
    return text.translate(_ASCII_FOLD)


def fold(text: str) -> str:
    """Turkish lowercase + ASCII fold. Canonical comparison form for any string."""
    return ascii_fold(tr_lower(text))
