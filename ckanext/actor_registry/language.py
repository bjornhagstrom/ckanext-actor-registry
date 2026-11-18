"""Which language a publisher's or contact point's name is shown in (0.7.0).

A record has one name, its default name, in the portal's default language
(``ckan.locale_default``), and may have a translation per language the portal
offers. A page shows the visitor's language when there is a translation, and
the default name otherwise. The export carries every language.
"""

from ckan.plugins import toolkit


def default_language():
    return toolkit.config.get("ckan.locale_default") or "en"


def current_language():
    """The page's language, or the default language outside a request."""
    try:
        return toolkit.h.lang() or default_language()
    except Exception:
        return default_language()


def offered_languages():
    """The languages a record can be translated into: the ones the portal offers, without its default language."""
    offered = _codes("ckan.locales_offered")
    filtered_out = set(_codes("ckan.locales_filtered_out"))
    default = default_language()
    seen = []
    for code in offered:
        # A regional variant of the default language (sv_SE beside sv) shows the default name too; a sibling of a
        # regional default (pt_PT beside pt_BR) is a language of its own.
        if code and not shows_default(code) and code not in filtered_out and code not in seen:
            seen.append(code)
    return seen


def _codes(option):
    value = toolkit.config.get(option) or []
    return value.split() if isinstance(value, str) else list(value)


def base(code):
    """``sv`` for ``sv_SE``: the language without its region or script."""
    return (code or "").replace("-", "_").split("_")[0]


def normalise(code):
    """A language code as CKAN writes it: ``pt_BR`` also for ``pt-BR``, so that both are one language."""
    return (code or "").replace("-", "_")


def candidates(code):
    """The translations to look for, in order: the language itself, then its base language (``sv_SE``, ``sv``)."""
    code = normalise(code)
    return [code] if base(code) == code else [code, base(code)]


def language_name(code):
    """The language's name in the page's language (``engelska`` on a Swedish page), or the code."""
    try:
        from babel import Locale
        return Locale.parse(code).get_display_name(current_language()) or code
    except Exception:
        return code


def bcp47(code):
    """CKAN's ``pt_BR`` as the export's language tag ``pt-BR``."""
    return (code or "").replace("_", "-")


def valid_code(code):
    """A language code as CKAN writes them (``sv``, ``pt_BR``, ``zh_Hant_TW``), at most 20 characters."""
    import re
    return isinstance(code, str) and len(code) <= 20 and re.fullmatch(r"[a-z]{2,3}([_-][A-Za-z0-9]{2,8})*", code) is not None

def shows_default(code):
    """Whether a page in this language shows the default name: the default language itself, or a regional variant of
    a default without a region (sv_SE when the default is sv). The same rule as ``offered_languages``."""
    default = default_language()
    return code == default or base(code) == default
