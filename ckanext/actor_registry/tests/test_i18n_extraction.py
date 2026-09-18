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
