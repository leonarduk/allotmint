"""ISO 3166 country codes -> display names for look-through exposure (#9974).

Morningstar reports a fund's country exposure with ISO alpha-3 codes and an
ISIN starts with an ISO alpha-2 code. Both are mapped to one display name so a
directly held share and a fund's underlying holdings land in the same bucket.
The table covers the markets that appear in global/EM index funds; an unknown
code is returned as-is rather than guessed.
"""

from __future__ import annotations

from typing import Dict, Optional

# (alpha-2, alpha-3, display name)
_COUNTRIES: tuple[tuple[str, str, str], ...] = (
    ("AE", "ARE", "United Arab Emirates"),
    ("AR", "ARG", "Argentina"),
    ("AT", "AUT", "Austria"),
    ("AU", "AUS", "Australia"),
    ("BE", "BEL", "Belgium"),
    ("BM", "BMU", "Bermuda"),
    ("BR", "BRA", "Brazil"),
    ("CA", "CAN", "Canada"),
    ("CH", "CHE", "Switzerland"),
    ("CL", "CHL", "Chile"),
    ("CN", "CHN", "China"),
    ("CO", "COL", "Colombia"),
    ("CY", "CYP", "Cyprus"),
    ("CZ", "CZE", "Czech Republic"),
    ("DE", "DEU", "Germany"),
    ("DK", "DNK", "Denmark"),
    ("EG", "EGY", "Egypt"),
    ("ES", "ESP", "Spain"),
    ("FI", "FIN", "Finland"),
    ("FR", "FRA", "France"),
    ("GB", "GBR", "United Kingdom"),
    ("GG", "GGY", "Guernsey"),
    ("GR", "GRC", "Greece"),
    ("HK", "HKG", "Hong Kong"),
    ("HU", "HUN", "Hungary"),
    ("ID", "IDN", "Indonesia"),
    ("IE", "IRL", "Ireland"),
    ("IL", "ISR", "Israel"),
    ("IM", "IMN", "Isle of Man"),
    ("IN", "IND", "India"),
    ("IS", "ISL", "Iceland"),
    ("IT", "ITA", "Italy"),
    ("JE", "JEY", "Jersey"),
    ("JP", "JPN", "Japan"),
    ("KR", "KOR", "South Korea"),
    ("KW", "KWT", "Kuwait"),
    ("KY", "CYM", "Cayman Islands"),
    ("LU", "LUX", "Luxembourg"),
    ("MO", "MAC", "Macau"),
    ("MX", "MEX", "Mexico"),
    ("MY", "MYS", "Malaysia"),
    ("NL", "NLD", "Netherlands"),
    ("NO", "NOR", "Norway"),
    ("NZ", "NZL", "New Zealand"),
    ("PE", "PER", "Peru"),
    ("PH", "PHL", "Philippines"),
    ("PL", "POL", "Poland"),
    ("PT", "PRT", "Portugal"),
    ("QA", "QAT", "Qatar"),
    ("RU", "RUS", "Russia"),
    ("SA", "SAU", "Saudi Arabia"),
    ("SE", "SWE", "Sweden"),
    ("SG", "SGP", "Singapore"),
    ("TH", "THA", "Thailand"),
    ("TR", "TUR", "Turkey"),
    ("TW", "TWN", "Taiwan"),
    ("US", "USA", "United States"),
    ("VN", "VNM", "Vietnam"),
    ("ZA", "ZAF", "South Africa"),
)

_BY_CODE: Dict[str, str] = {}
for _a2, _a3, _name in _COUNTRIES:
    _BY_CODE[_a2] = _name
    _BY_CODE[_a3] = _name


def country_name(code: object) -> Optional[str]:
    """Display name for an ISO alpha-2/alpha-3 ``code``; the code itself if unknown, ``None`` if blank."""

    if not isinstance(code, str) or not code.strip():
        return None
    key = code.strip().upper()
    return _BY_CODE.get(key, key)


def country_from_isin(isin: object) -> Optional[str]:
    """Country of incorporation implied by an ISIN's two-letter prefix, or ``None``."""

    if not isinstance(isin, str) or len(isin.strip()) < 2:
        return None
    prefix = isin.strip()[:2].upper()
    if not prefix.isalpha():
        return None
    return country_name(prefix)
