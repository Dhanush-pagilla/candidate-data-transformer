"""Location normalisation — ISO-3166 alpha-2 country resolution via pycountry."""
from __future__ import annotations
import pycountry

_COUNTRY_ALIAS_MAP: dict[str, str] = {
    "UK": "GB", "ENGLAND": "GB", "BRITAIN": "GB",
    "USA": "US", "UAE": "AE", "KSA": "SA",
}


def _resolve_country_code(token: str | None) -> str | None:
    """Convert a country string to validated ISO-3166 alpha-2 code, or None."""
    if not token:
        return None
    upper = token.strip().upper()
    if upper in _COUNTRY_ALIAS_MAP:
        return _COUNTRY_ALIAS_MAP[upper]
    result = pycountry.countries.get(alpha_2=upper)
    if result:
        return result.alpha_2
    try:
        matches = pycountry.countries.search_fuzzy(token.strip())
        if matches:
            return matches[0].alpha_2
    except LookupError:
        pass
    return None


def _normalize_location(raw: str | None) -> dict:
    """
    Parse a free-text location string into:
        { "city": str | None, "region": str | None, "country": str | None }
    Country code is validated ISO-3166 alpha-2 via pycountry.
    """
    empty: dict = {"city": None, "region": None, "country": None}
    if not raw:
        return empty
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return empty
    city        = parts[0] if len(parts) >= 1 else None
    region      = parts[1] if len(parts) >= 2 else None
    country_raw = parts[-1] if len(parts) >= 2 else None
    country     = _resolve_country_code(country_raw)
    if len(parts) == 1 and country:
        city = None
    return {"city": city, "region": region, "country": country}
