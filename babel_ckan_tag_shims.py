"""Minimal stand-ins for CKAN's own custom Jinja2 tags, for `pybabel
extract` only.

`pybabel extract` runs against a plain Jinja2 environment with no CKAN
installed. CKAN core registers real implementations of the `{% asset %}`,
{% snippet %}` and `{% ckan_extends %}` tags at app start-up (see
`ckan.lib.jinja_extensions`); without them, Jinja2's parser raises on any
template that uses one of those tags. Critically, Babel's jinja2 extractor
does NOT propagate that parse error -- it is swallowed, and the extractor
silently returns zero messages for the whole file, with no warning. Found
2026-09-15: 4 of this extension's 11 templates (every one using `{% asset
%}` or `{% snippet %}`) lost 100% of their strings this way on a first
extraction attempt that "succeeded" with no errors logged.

These shims don't need to behave like the real tags -- they are never
rendered, only parsed -- so each one just consumes tokens up to the
block's closing `%}` and emits a no-op node. Referenced from babel.cfg's
`[jinja2: ...]` section via `extensions=`. Re-run `pybabel extract`
after adding any *new* custom CKAN tag to a template, and add a
matching shim here if it starts silently dropping a file's strings
again -- the symptom is exactly what happened here: no error, just an
overall pot/po msgid count lower than a grep for `_(` in the templates
would suggest. `ckanext/actor_registry/tests/test_i18n_extraction.py`
guards against this regressing silently again.
"""

from jinja2 import nodes
from jinja2.ext import Extension


class _SkipTagExtension(Extension):
    """Consume every token up to the tag's closing `%}` and emit
    nothing. Works regardless of the tag's actual argument grammar
    (positional args, kwargs, none at all) since it never tries to
    parse an expression -- it only cares about finding the block end."""

    def parse(self, parser):
        token = next(parser.stream)
        while parser.stream.current.type != "block_end":
            next(parser.stream)
        return nodes.Output([], lineno=token.lineno)


class AssetShim(_SkipTagExtension):
    tags = {"asset"}


class SnippetShim(_SkipTagExtension):
    tags = {"snippet"}


class CkanExtendsShim(_SkipTagExtension):
    tags = {"ckan_extends"}
