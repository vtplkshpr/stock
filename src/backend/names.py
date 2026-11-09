"""Name normalisation for counterparties without an organisation record (people, placeholder
lines). Organisations themselves are matched through the register in src/organizations.py."""

import re
import unicodedata

# Legal-form words that do not identify the company.
_LEGAL_FORMS = re.compile(
    r"\b(cong ty|ct|ctcp|cty|co phan|cp|tnhh|trach nhiem huu han|mot thanh vien|mtv|"
    r"jsc|joint stock company|company|limited|ltd)\b"
)  # not "co": without accents it is also "cơ" (as in "cơ khí")


def normalize(name: str) -> str:
    text = unicodedata.normalize("NFD", (name or "").lower()).replace("đ", "d")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = _LEGAL_FORMS.sub(" ", text)
    return " ".join(text.split())
