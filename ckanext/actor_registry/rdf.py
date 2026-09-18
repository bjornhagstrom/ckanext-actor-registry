import re


def telephone_uri(phone):
    """Return a conservative ``tel:`` URI without changing phone semantics."""
    if not phone:
        return ""
    value = str(phone).strip()
    if value.lower().startswith("tel:"):
        value = value[4:]
    normalized = re.sub(r"[^0-9+]", "", value)
    return f"tel:{normalized}" if normalized else ""
