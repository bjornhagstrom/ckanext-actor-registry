# I18n plan: English source strings + Swedish translation

Status: **implemented 2026-09-15.** Templates, Python and JS strings
rewritten to English source with `_()`, `babel.cfg` + a real
`pybabel extract`-generated catalog added (`i18n/sv/LC_MESSAGES/
ckanext-actor-registry.po`/`.mo`), `ITranslation` wired into `plugin.py`,
compile step added to `ckan/dev-install-extras.sh`, and CHANGELOG.md/
README.md/CONTRIBUTING.md updated to reflect 0.1 status per the note
below.

Two things worth knowing that this plan didn't anticipate, both found
during implementation:

1. **`ckanext-skelleftea`'s existing `.po` is not an extraction-based
   catalog** (contrary to the "same mechanism" framing below) -- it is a
   small, hand-written override of *CKAN core's own* English vocabulary
   (`"Dataset"` -> `"Datamängd"` etc.), not an extraction of
   `ckanext-skelleftea`'s own template strings. `ckanext-actor-registry`'s
   catalog, by contrast, is a real `pybabel extract`-generated one, since
   its templates/Python had zero `_()` markers and only novel strings.
   The underlying mechanism (gettext/`ITranslation`/`pybabel compile`) is
   identical either way.
2. **`pybabel extract` silently drops an entire template's strings**, with
   no error and no warning, if the template uses one of CKAN's own custom
   Jinja tags (`{% asset %}`, `{% snippet %}`, `{% ckan_extends %}`) --
   Babel's jinja2 extractor swallows the resulting parse error. 4 of this
   extension's 11 templates were affected on the first extraction attempt.
   Fixed with small shim Jinja2 extensions in `babel_ckan_tag_shims.py`
   (repo root) referenced from `babel.cfg`, and pinned against regressing
   again by `ckanext/actor_registry/tests/test_i18n_extraction.py`.

Also settled explicitly with Björn before this work started (2026-09-15):
this plan is about UI text only. It has no relationship to, and does not
require, an Action API for the registry, nor `ckanext-fluent`-style
multilingual *data* fields on `Actor`/`ContactPoint` or dataset fields --
both were raised and explicitly deferred/declined as separate, unrelated
questions.

## Decision

Follow the same convention CKAN core and `ckanext-skelleftea` already use:
**English is the source language** (the literal text in templates/Python is
English, wrapped in `_()`), and Swedish is a translation catalog compiled
from it. This is the opposite of the extension's current state, where
Swedish is hardcoded directly with no `_()` markers at all.

Rationale: this is CKAN's own convention (an English-source extension is
what other installations expect), and it lets us reuse a proven, already
-working mechanism in this exact repo (`ckanext-skelleftea`'s
`i18n/sv/LC_MESSAGES/ckanext-skelleftea.po`/`.mo`, compiled via `pybabel
compile` in `ckan/dev-install-extras.sh`) instead of inventing a new one.

## Why this is not "just add a language file"

Confirmed by code inspection: zero `_()`/gettext markers exist anywhere in
`ckanext-actor-registry` today. Every UI string (Jinja templates, Python
flash messages/form labels) is a hardcoded Swedish literal. Flipping to
English-source means rewriting each of those strings at the source, not
adding a translation on top of what's there.

## Scope of work

1. **Templates** (`ckanext/actor_registry/templates/**/*.html`): wrap every
   user-facing string in `{{ _("...") }}`, with the literal text rewritten
   in English (e.g. `<h1>Aktörer</h1>` -> `<h1>{{ _("Actors") }}</h1>`).
2. **Python** (`views.py`, `plugin.py`, anywhere else with flash messages,
   form validation errors, or other user-facing text): same treatment,
   `from ckan.common import _` (or however CKAN 2.11/2.12 exposes it) and
   wrap each string, English at the source.
3. **JS** (`actor-quick-create.js`, `quick-create.js`, ~7 strings): standard
   `.po`/`.mo` compilation does not cover JavaScript. Recommendation: don't
   build a separate JS i18n system for 7 strings. Instead, render the
   already-translated text server-side (via Jinja `_()`, so it goes through
   the normal catalog) into `data-*` attributes on the elements the JS
   already reads from, and have the JS pull text from there instead of
   hardcoding it. Smaller, more consistent with the rest of the fix than a
   second translation mechanism.
4. **Catalog scaffolding**: add an `i18n/` directory mirroring
   `ckanext-skelleftea`'s layout. Extract messages with `pybabel extract`
   (needs a small `babel.cfg`-equivalent mapping covering `**.py` and
   `templates/**.html` -- `ckanext-skelleftea` doesn't keep a `babel.cfg`
   file in the repo, so check exactly how its `.pot`/`.po` were originally
   generated before assuming the same invocation works unchanged here).
   Create `i18n/sv/LC_MESSAGES/ckanext-actor-registry.po`.
5. **Swedish translations**: for every extracted `msgid` (the new English
   string), the `msgstr` is the *original* Swedish text that's already in
   the extension today -- this is not new translation work, it's moving
   text we already know is correct into the right slot. Only genuinely new
   strings (if any appear during the rewrite) need fresh Swedish text.
6. **Compile step**: add the same `pybabel compile -d .../i18n -D
   ckanext-actor-registry` step to `ckan/dev-install-extras.sh` (alongside
   the existing skelleftea one) so the dev stack picks it up automatically.
7. **Docs**: update `CHANGELOG.md`, `README.md` and `CONTRIBUTING.md` to
   reflect that i18n is now a 0.1 feature, not a 0.2 TODO.

## Testing / regression risk

- Existing Python tests may assert against the current Swedish literal
  strings directly (e.g. checking flash message text) -- these will need
  updating to check for the English source string (default locale) instead,
  or to explicitly force the `sv` locale and check the translated text.
  Needs a check before assuming "just wrap strings" is risk-free.
- Manually verify both locales after the change: default (English) shows
  the new English text everywhere, and Swedish (however this project
  selects a locale -- check how `ckanext-skelleftea`'s pages get `sv`)
  still shows exactly the same Swedish text users see today.
- JS-driven UI (quick-create flows) needs its own manual check in both
  locales once the data-attribute approach is in place.

## Rough effort

Mechanical but touches most files in the extension: every template, the
main Python files, plus the JS refactor and catalog scaffolding. Not a
quick fix, but well understood and low-risk given `ckanext-skelleftea`
already proves the mechanism works in this exact stack. Suggest doing it as
its own focused pass (not mixed with other feature work), with a dedicated
test run before considering it done.

## Locale selection (decided 2026-09-09)

No locale switcher inside actor-registry itself -- it follows whatever
locale the CKAN installation/session is already using, same as every
other extension in this portal. This is also exactly how CKAN's own i18n
system is designed to work in general: locale is a portal-wide setting
(`ckan.locale_default`/`ckan.locale_order` plus the user's browser/session
preference), and an extension just ships a `.po`/`.mo` catalog under its
own gettext domain -- it plugs into the same mechanism CKAN core and every
other extension use, it doesn't run its own separate locale logic. So this
plan needs no special locale-detection code at all, just the catalog.

## Known scope gap (found 2026-09-15, during manual verification): header nav links not translated

Björn noticed the sysadmin-only "Aktörer"/"Kontaktpunkter" shortcuts in
the site header still show in Swedish even on `/en/...` pages. Root
cause: those two `<a>` links live in **`ckanext-skelleftea`**'s
`templates/header.html` (`block header_site_navigation_tabs`), a
different extension from `ckanext-actor-registry` -- they're plain
hardcoded Swedish strings, never wrapped in `_()` at all (added before
i18n was in scope for this project). This is expected, not a bug in the
work covered by this plan, which was scoped to `ckanext-actor-registry`
only (see "Locale selection" above and the explicit no-API/no-fluent,
UI-text-only scope decision from 2026-09-15's session).

Not fixed as part of this plan. Per Björn (2026-09-15): these shortcuts
shouldn't live in the header nav at all long-term (they're a dev/testing
convenience) -- and the underlying architecture (own IBlueprint routes,
sysadmin-gated via `_require_sysadmin()`) is already exactly right, this
is purely a navigation/discoverability fix, not a redesign.

**Concrete recommended fix (researched 2026-09-15, not yet implemented):**
CKAN's own recommended pattern (current as of 2.11+, confirmed against
this project's 2.12) for a plugin to add a tab to CKAN's own
`/ckan-admin` area is overriding `templates/admin/base.html`'s
`content_primary_nav` block with `h.build_nav_icon()`. (An older,
programmatic `toolkit.add_ckan_admin_tab()` helper existed 2015-2.10 but
was REMOVED in CKAN 2.11 in favour of this template pattern -- so for
this project's CKAN 2.12, the template override below is the only
supported route, not a shortcut being skipped.) Add this new file to
**`ckanext-actor-registry`** (not `ckanext-skelleftea` -- these are
actor-registry's own pages, ownership belongs with the extension that
defines the routes):

```jinja
{# ckanext/actor_registry/templates/admin/base.html #}
{% ckan_extends %}

{% block content_primary_nav %}
  {{ super() }}
  {{ h.build_nav_icon('actor_registry.actors_index', _('Actors'), icon='building') }}
  {{ h.build_nav_icon('actor_registry.contactpoints_index', _('Contact points'), icon='address-book') }}
{% endblock %}
```

`{{ super() }}` + append is the SAFE case of the `{{ super() }}`
CSS-scoping fallgrop documented in `claude-session-konventioner.md`
(core's `content_primary_nav` block is a flat list of `build_nav_icon()`
calls, nothing nested to land inside of). `/ckan-admin` is already
sysadmin-gated by CKAN core itself, matching the existing route
authorization. Using `_()` here (already actor-registry's own i18n
domain) fixes the translation gap above as a side effect, for free.
Once this lands, remove the two hardcoded links from
`ckanext-skelleftea/templates/header.html` (`block
header_site_navigation_tabs`).

Sources: [ckan/ckan issue #2351](https://github.com/ckan/ckan/issues/2351),
[PR #2363 (added, later removed in 2.11)](https://github.com/ckan/ckan/pull/2363),
[ckan/ckan/templates/admin/base.html (2.12.0)](https://github.com/ckan/ckan/blob/ckan-2.12.0/ckan/templates/admin/base.html).

## Future work: a visible language switcher in the GUI (requested 2026-09-15)

Currently locale selection is purely URL-prefix-based (`/en/...`,
`/sv/...`) plus browser Accept-Language negotiation for the unprefixed
default -- there's no way for a visitor to switch language via a UI
control. Björn asked (2026-09-15) for a language switcher to be added to
the backlog. Not scoped or designed yet -- needs its own pass: where it
lives in the header (see the header-nav scope gap above, since that's the
same template), whether it's actor-registry's concern or
`ckanext-skelleftea`'s (likely the latter, since it's a portal-wide
concern, not specific to actors/contact points), and how it interacts
with CKAN's standard `?locale=` /session-based locale switching if CKAN
core already provides a mechanism to hook into rather than building one
from scratch.
