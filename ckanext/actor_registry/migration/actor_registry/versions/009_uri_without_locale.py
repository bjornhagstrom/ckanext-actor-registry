"""Drop the page language from the URIs the registry made.

Before 0.6.0 a publisher or contact point created on a page in another
language than the default got that language in its URI
(``https://example.org/sv/actors/<id>``). Only a URI the registry made itself
is changed: one that ends with the record's own page and id, and has exactly
one path segment that is a language CKAN knows. That segment is removed,
wherever ``ckan.root_path`` put it. A URI someone entered, one without such a
segment (``https://example.org/geo/actors/<id>``), or one whose new form is
already taken, is left as it is.

There is no way back: the language is not kept. Take a backup first.

Revision ID: actor_registry_009
Revises: actor_registry_008
"""

import os
import re

from alembic import op
import sqlalchemy as sa


revision = "actor_registry_009"
down_revision = "actor_registry_008"
branch_labels = None
depends_on = None

TABLES = (("actor_registry_actor", "actors"), ("contactpoints_contact_point", "contactpoints"))


def known_locales():
    """The languages CKAN knows: its catalogues and the ones it offers."""
    from ckan.lib import i18n
    locales = {"en"}
    try:
        folder = i18n.get_ckan_i18n_dir()
        locales.update(name for name in os.listdir(folder) if os.path.isdir(os.path.join(folder, name)))
    except Exception:
        pass
    try:
        locales.update(i18n.get_locales())
    except Exception:
        pass
    return locales


def without_locale(uri, page, row_id, locales):
    """The URI without its one language segment, or None to leave it as it is."""
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*://[^/]+)((?:/[^/]+)*)/{}/{}$".format(page, re.escape(row_id)), uri or "")
    if not match:
        return None
    segments = [segment for segment in match.group(2).split("/") if segment]
    kept = [segment for segment in segments if segment not in locales]
    if len(kept) != len(segments) - 1:
        return None
    return match.group(1) + "".join("/" + segment for segment in kept) + "/{}/{}".format(page, row_id)


def upgrade():
    connection = op.get_bind()
    locales = known_locales()
    for table, page in TABLES:
        rows = connection.execute(sa.text(f"SELECT id, uri FROM {table}")).fetchall()
        for row_id, uri in rows:
            new_uri = without_locale(uri, page, row_id, locales)
            if not new_uri:
                continue
            taken = any(connection.execute(sa.text(f"SELECT 1 FROM {other} WHERE uri = :uri"), {"uri": new_uri}).first()
                        for other, _page in TABLES)
            if not taken:
                connection.execute(sa.text(f"UPDATE {table} SET uri = :uri WHERE id = :id"), {"uri": new_uri, "id": row_id})


def downgrade():
    # The language is not kept, so the old URIs cannot be restored.
    pass
