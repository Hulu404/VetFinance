"""Removal of personal data of pet owners from bank statement texts.

Rule 6 of CLAUDE.md: full names of individuals are never stored. Legal entities and sole
proprietors ("ИП Фамилия Имя Отчество") are kept: they are counterparties, not clients.

What is removed from a purpose of payment:
- "Фамилия Имя Отчество" (the patronymic suffix is required, so ordinary capitalised words stay);
- "Фамилия И.О." and "И.О. Фамилия";
- every word of the name of an individual counterparty (the payer or the receiver) in any case form
  that starts with the same stem, plus the phones and e-mails.
A sole proprietor's name right after "ИП" is protected from all patterns.
"""

import re
from collections.abc import Iterable

_CAP = r"[А-ЯЁ][а-яё]+"
_SURNAME = rf"{_CAP}(?:-{_CAP})?"
_INITIALS = r"[А-ЯЁ]\.\s?[А-ЯЁ]\.?"
_PATRONYMIC = r"[А-ЯЁ][а-яё]*(?:ович|евич|ьич|ична|овна|евна|инична|кызы|оглы)"
_NOT_AFTER_IP = r"(?<!ИП )(?<!ИП )"

_FULL_NAME = re.compile(rf"{_NOT_AFTER_IP}\b{_SURNAME}\s+{_CAP}\s+{_PATRONYMIC}\b")
_SURNAME_INITIALS = re.compile(rf"{_NOT_AFTER_IP}\b{_SURNAME}\s+{_INITIALS}")
_INITIALS_SURNAME = re.compile(rf"{_NOT_AFTER_IP}\b{_INITIALS}\s*{_SURNAME}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:])")
_REPEATED_PUNCT = re.compile(r"([.,;:])(?:\s*[.,;:])+")
_SPACES = re.compile(r"\s{2,}")

# Abbreviations that start the name of an organisation or a government body.
_ORG_WORDS = frozenset(
    {
        "ооо",
        "оао",
        "зао",
        "пао",
        "ао",
        "нко",
        "ано",
        "ип",
        "уфк",
        "фгуп",
        "муп",
        "гуп",
        "фнс",
        "ифнс",
        "мифнс",
        "гу",
        "сфр",
        "пфр",
        "фсс",
        "осфр",
        "мку",
        "мбу",
        "гбу",
        "фгбу",
        "кфх",
        "тсж",
        "снт",
        "банк",
        "межрайонная",
        "управление",
        "отделение",
        "федеральное",
        "государственное",
        "муниципальное",
        "общество",
        "акционерное",
        "индивидуальный",
        "министерство",
        "администрация",
        "департамент",
        "казначейство",
    }
)
_QUOTES = ('"', "«", "»", "“", "”")
_MIN_NAME_TOKEN = 3
_MIN_STEM = 4


def is_legal_entity_name(name: str) -> bool:
    """True for names of organisations and sole proprietors, False for individuals."""
    stripped = name.strip()
    if not stripped:
        return False
    if any(q in stripped for q in _QUOTES):
        return True
    first = re.split(r"[\s.(]+", stripped, maxsplit=1)[0].casefold()
    return first in _ORG_WORDS


def _name_tokens(names: Iterable[str]) -> list[str]:
    tokens: list[str] = []
    for name in names:
        for token in re.split(r"[\s,.\-]+", name):
            if len(token) >= _MIN_NAME_TOKEN and token.casefold() not in _ORG_WORDS:
                tokens.append(token)
    return tokens


def _token_pattern(token: str) -> re.Pattern[str]:
    """Matches the token and its case forms: same stem (a word minus its last letters)."""
    stem = token[: max(_MIN_STEM, len(token) - 2)] if len(token) > _MIN_STEM else token
    return re.compile(
        rf"(?<![А-Яа-яЁё]){re.escape(stem)}[а-яё]{{0,3}}(?![А-Яа-яЁё])", re.IGNORECASE
    )


def _tidy(text: str) -> str:
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _REPEATED_PUNCT.sub(r"\1", text)
    text = _SPACES.sub(" ", text)
    return text.strip(" ,;:")


def strip_personal_names(text: str, known_names: Iterable[str] = ()) -> str:
    """Purpose of payment (or a free comment) without names of individuals."""
    result = text
    for token in _name_tokens(known_names):
        result = _token_pattern(token).sub("", result)
    for pattern in (_FULL_NAME, _SURNAME_INITIALS, _INITIALS_SURNAME, _PHONE, _EMAIL):
        result = pattern.sub("", result)
    return _tidy(result)


def public_counterparty(name: str, inn: str) -> tuple[str, str]:
    """(name, inn) that may be stored: both empty for individuals."""
    if is_legal_entity_name(name):
        return name.strip(), inn.strip()
    return "", ""
