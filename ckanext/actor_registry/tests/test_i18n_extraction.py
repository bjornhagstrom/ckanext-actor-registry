"""Regression test for a silent-data-loss pitfall found 2026-09-15 while
setting up i18n for this extension (see babel_ckan_tag_shims.py at the
repo root): `pybabel extract` runs Jinja2's own parser with no CKAN
installed, so any template using one of CKAN's custom tags (`{% asset
%}`, `{% snippet %}`, `{% ckan_extends %}`) fails to parse -- and
Babel's jinja2 extractor swallows that parse error silently, returning
ZERO messages for the whole file, with no warning anywhere. On the
first extraction attempt here, 4 of this extension's 11 templates (every
one using `{% asset %}` or `{% snippet %}`) silently lost 100% of their
translatable strings this way; the msgid count "looked fine" (86) and
nothing in pybabel's own output hinted anything was missing.

This test pins per-file extraction coverage so a newly introduced custom
tag, or a broken/removed shim, is caught here -- loudly, in CI -- instead
of silently dropping a template's strings out of some future catalog
re-extraction with no error at all.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = REPO_ROOT / "ckanext" / "actor_registry" / "templates"

_GETTEXT_CALL = re.compile(r"_\(")


def _count_gettext_calls(path):
    return len(_GETTEXT_CALL.findall(path.read_text(encoding="utf-8")))


def test_pybabel_extraction_finds_every_translatable_string(tmp_path):
    pot_path = tmp_path / "extracted.pot"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [
            sys.executable, "-m", "babel.messages.frontend", "extract",
            "-F", "babel.cfg",
            "-o", str(pot_path),
            ".",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "pybabel extract failed:\n" + result.stdout + "\n" + result.stderr
    )

    pot_text = pot_path.read_text(encoding="utf-8")

    failures = []
    for template in sorted(TEMPLATES_DIR.rglob("*.html")):
        expected = _count_gettext_calls(template)
        if expected == 0:
            continue
        rel = template.relative_to(REPO_ROOT).as_posix()
        found = pot_text.count(rel)
        if found != expected:
            failures.append(
                f"{rel}: source has {expected} _() call(s) but only "
                f"{found} location reference(s) were extracted -- likely "
                f"a template parse failure being swallowed silently"
            )

    assert not failures, "\n".join(failures)


# The languages this project maintains itself, and so keeps complete. A
# contributed language may be partial: a missing string shows in English
# until someone translates it (Björn 2026-10-01).
MAINTAINED_LANGUAGES = ("sv", "sv_SE")


def test_every_extracted_string_is_translated(tmp_path):
    """A fresh extraction against the maintained catalogues (2026-10-01):
    the contact point deletion added 13 strings that never reached the .pot
    or the .po files, so they showed in English on Swedish pages."""
    from babel.messages.pofile import read_po

    pot_path = tmp_path / "extracted.pot"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(
        [sys.executable, "-m", "babel.messages.frontend", "extract",
         "-F", "babel.cfg", "-o", str(pot_path), "."],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, check=True,
    )
    with pot_path.open("rb") as f:
        extracted = {m.id for m in read_po(f) if m.id}

    i18n = REPO_ROOT / "ckanext" / "actor_registry" / "i18n"
    failures = []
    for language in MAINTAINED_LANGUAGES:
        po_path = i18n / language / "LC_MESSAGES" / "ckanext-actor-registry.po"
        with po_path.open("rb") as f:
            translated = {m.id for m in read_po(f) if m.id and m.string}
        for missing in sorted(extracted - translated, key=str):
            failures.append(f"{po_path.parent.parent.name}: {missing!r}")

    assert not failures, "Untranslated strings:\n" + "\n".join(failures)


def test_every_compiled_catalogue_is_offered():
    from ckanext.actor_registry.plugin import ActorRegistryPlugin

    plugin = ActorRegistryPlugin()
    shipped = sorted(p.parent.parent.name for p in
                     (REPO_ROOT / "ckanext" / "actor_registry" / "i18n").glob("*/LC_MESSAGES/*.mo"))
    assert plugin.i18n_locales() == shipped
    assert {"sv", "sv_SE"} <= set(shipped)


def test_every_catalogue_is_compiled_and_up_to_date():
    """CKAN loads the .mo, not the .po. A contributed language whose .mo is
    missing or stale would silently not be offered, or show old text."""
    from babel.messages.mofile import read_mo
    from babel.messages.pofile import read_po

    failures = []
    for po_path in sorted((REPO_ROOT / "ckanext" / "actor_registry" / "i18n").glob("*/LC_MESSAGES/*.po")):
        mo_path = po_path.with_suffix(".mo")
        locale = po_path.parent.parent.name
        if not mo_path.exists():
            failures.append(f"{locale}: no .mo; run pybabel compile")
            continue
        with po_path.open("rb") as f:
            po = {m.id: m.string for m in read_po(f) if m.id and m.string and not m.fuzzy}
        with mo_path.open("rb") as f:
            mo = {m.id: m.string for m in read_mo(f) if m.id}
        if po != mo:
            failures.append(f"{locale}: .mo does not match .po; run pybabel compile")
    assert not failures, "\n".join(failures)
