from datetime import datetime

from ckan import model
from ckan.plugins import toolkit
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, bindparam, inspect, text
from sqlalchemy.dialects.postgresql import ARRAY, TEXT as PG_TEXT
from sqlalchemy.orm import relationship

from ckanext.actor_registry import language


# The two scheming fields the registry links datasets through, and ckanext-dcat's
# free-text contact point that the migration reads. Only these keys may be
# interpolated into SQL below.
_EXTRA_KEYS = ("publisher_actor_id", "contact_point_ids", "contact")
_extras_are_a_column = None


def _extras_in_package_column():
    """Where a dataset's extras live in this CKAN.

    CKAN 2.12 keeps them in a jsonb column, ``package.extras``. CKAN 2.11
    keeps them in the ``package_extra`` table (one row per key). The registry
    supports both, so the SQL that reads them is built from
    :func:`extra_text` / :func:`extra_present` instead of naming either layout.
    """
    global _extras_are_a_column
    if _extras_are_a_column is None:
        columns = {column["name"] for column in inspect(model.meta.engine).get_columns("package")}
        _extras_are_a_column = "extras" in columns
    return _extras_are_a_column


def extra_text(key):
    """SQL for a package's extra ``key`` as text (NULL when absent).

    Meant to be used inside a query ``FROM package``.
    """
    assert key in _EXTRA_KEYS, key
    if _extras_in_package_column():
        return "(extras ->> '%s')" % key
    return (
        "(SELECT pe.value FROM package_extra pe "
        "WHERE pe.package_id = package.id AND pe.key = '%s' AND pe.state = 'active')" % key
    )


def contact_ids_jsonb():
    """SQL for a package's ``contact_point_ids`` as a jsonb array, never failing.

    Meant to be used inside a query ``FROM package``. Read the same way as
    ``helpers._id_list``: a JSON list of ids as it is, a bare id as a list of
    one, and anything else (empty, missing, broken JSON) as an empty list. A
    plain ``::jsonb`` cast would make the whole query fail on a single dataset
    with a broken stored value, as old imports can have.
    """
    contacts = extra_text("contact_point_ids")
    return (
        "(CASE"
        " WHEN {c} ~ '^\\s*\\[\\s*(\"[^\"\\\\]*\"\\s*(,\\s*\"[^\"\\\\]*\"\\s*)*)?\\]\\s*$'"
        " THEN ({c})::jsonb"
        " WHEN btrim(coalesce({c}, '')) <> '' AND left(btrim({c}), 1) <> '['"
        " THEN jsonb_build_array(btrim({c}))"
        " ELSE '[]'::jsonb END)"
    ).format(c=contacts)


def extra_present(key):
    """SQL that is true when a package has an extra called ``key``."""
    assert key in _EXTRA_KEYS, key
    if _extras_in_package_column():
        return "(extras ? '%s')" % key
    return (
        "EXISTS (SELECT 1 FROM package_extra pe "
        "WHERE pe.package_id = package.id AND pe.key = '%s' AND pe.state = 'active')" % key
    )


class ActorTranslation(toolkit.BaseModel):
    """A publisher's name and description in one more language (0.7.0)."""

    __tablename__ = "actor_registry_actor_translation"

    actor_id = Column(String(36), ForeignKey("actor_registry_actor.id", ondelete="CASCADE"), primary_key=True)
    lang = Column(String(20), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)


class ContactPointTranslation(toolkit.BaseModel):
    """A contact point's name in one more language (0.7.0)."""

    __tablename__ = "actor_registry_contact_point_translation"

    contact_point_id = Column(String(36), ForeignKey("contactpoints_contact_point.id", ondelete="CASCADE"),
                              primary_key=True)
    lang = Column(String(20), primary_key=True)
    name = Column(String(255), nullable=False)


class _Translated:
    """Names per language for a record with ``translations`` (see ``language``)."""

    def translation(self, lang):
        lang = language.normalise(lang)
        for row in self.translations:
            if language.normalise(row.lang) == lang:
                return row
        return None

    def shown_translation(self):
        """The translation for the page's language (or its base language), or None."""
        current = language.current_language()
        if language.shows_default(current):
            return None
        for code in language.candidates(current):
            row = self.translation(code)
            if row is not None and row.name:
                return row
        return None

    @property
    def display_name(self):
        """The name in the page's language, or the default name."""
        row = self.shown_translation()
        return row.name if row else self.name

    def name_translated(self):
        """``{language: name}`` with the default name in the default language, or {} without translations,
        so that a record without translations is exported exactly as before."""
        # A translation in the default language (stored before the portal changed its default) never replaces
        # the default name.
        names = {row.lang: row.name for row in self.translations if row.name and not language.shows_default(row.lang)}
        if not names:
            return {}
        names[language.default_language()] = self.name
        return names

    def set_translations(self, values):
        """Replace the translations with ``{language: {"name": ..., "description": ...}}``; a language without
        a name is removed."""
        # pt-BR and pt_BR are one language; the default language has the default name and no translation.
        wanted = {language.normalise(lang): fields for lang, fields in values.items()
                  if str(fields.get("name") or "").strip() and not language.shows_default(language.normalise(lang))}
        for row in list(self.translations):
            if row.lang not in wanted:
                self.translations.remove(row)
        for lang, fields in wanted.items():
            row = self.translation(lang)
            if row is None:
                row = self._translation_class(lang=lang, name="")
                self.translations.append(row)
            row.name = str(fields["name"]).strip()
            if hasattr(row, "description"):
                row.description = str(fields.get("description") or "").strip() or None

    def translations_dict(self):
        result = {}
        for row in sorted(self.translations, key=lambda r: r.lang):
            entry = {"name": row.name}
            if hasattr(row, "description"):
                entry["description"] = row.description or ""
            result[row.lang] = entry
        return result


class Actor(_Translated, toolkit.BaseModel):
    """An organization or person that can fulfil metadata roles."""

    __tablename__ = "actor_registry_actor"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    actor_kind = Column(String(30), nullable=False, default="organization")
    actor_type = Column(Text, nullable=True)
    identifier = Column(String(255), nullable=True)
    identifier_scheme = Column(String(255), nullable=True)
    uri = Column(Text, nullable=False, unique=True)
    url = Column(Text, nullable=True)
    email = Column(String(320), nullable=True)
    description = Column(Text, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    merged_into_id = Column(
        String(36), ForeignKey("actor_registry_actor.id", ondelete="SET NULL"), nullable=True
    )
    created = Column(DateTime, nullable=False, default=datetime.utcnow)
    modified = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    translations = relationship(ActorTranslation, cascade="all, delete-orphan", lazy="selectin",
                                passive_deletes=True)
    _translation_class = ActorTranslation

    @property
    def display_description(self):
        row = self.shown_translation()
        return (row.description if row and row.description else None) or self.description or ""

    def as_dict(self):
        return {
            "display_name": self.display_name, "display_description": self.display_description,
            "translations": self.translations_dict(), "name_translated": self.name_translated(),
            "id": self.id, "name": self.name, "kind": self.actor_kind,
            "type": self.actor_type or "", "identifier": self.identifier or "",
            "identifier_scheme": self.identifier_scheme or "", "uri": self.uri,
            "url": self.url or "", "email": self.email or "",
            "description": self.description or "", "active": bool(self.active),
            "merged_into_id": self.merged_into_id or "",
        }


class ContactPoint(_Translated, toolkit.BaseModel):
    __tablename__ = "contactpoints_contact_point"

    id = Column(String(36), primary_key=True)
    actor_id = Column(String(36), ForeignKey("actor_registry_actor.id"), nullable=True)
    name = Column(String(255), nullable=False)
    email = Column(String(320), nullable=True)
    phone = Column(String(100), nullable=True)
    url = Column(Text, nullable=True)
    uri = Column(Text, nullable=False, unique=True)
    active = Column(Boolean, nullable=False, default=True)
    created = Column(DateTime, nullable=False, default=datetime.utcnow)
    modified = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    translations = relationship(ContactPointTranslation, cascade="all, delete-orphan", lazy="selectin",
                                passive_deletes=True)
    _translation_class = ContactPointTranslation

    def as_dict(self):
        return {
            "display_name": self.display_name,
            "translations": self.translations_dict(), "name_translated": self.name_translated(),
            "id": self.id,
            "actor_id": self.actor_id or "",
            "name": self.name,
            "email": self.email or "",
            "phone": self.phone or "",
            "url": self.url or "",
            "uri": self.uri,
            "active": bool(self.active),
        }


def get_contact_point(contact_id):
    return model.Session.query(ContactPoint).filter(ContactPoint.id == contact_id).first()


def get_contact_point_by_uri(uri):
    if not uri:
        return None
    return model.Session.query(ContactPoint).filter(ContactPoint.uri == uri).first()


def all_contact_points(include_inactive=False):
    query = model.Session.query(ContactPoint)
    if not include_inactive:
        query = query.filter(ContactPoint.active.is_(True))
    return by_display_name(query.order_by(ContactPoint.name.asc()).all())


def get_actor(actor_id):
    return model.Session.query(Actor).filter(Actor.id == actor_id).first()


def get_actor_by_uri(uri):
    if not uri:
        return None
    return model.Session.query(Actor).filter(Actor.uri == uri).first()


def registry_uri_owner(uri, exclude_actor_id=None, exclude_contact_point_id=None):
    """Return the registry entity that already owns a URI, if any.

    Actor and contact point URIs must be distinct. They identify different RDF
    resources (normally a FOAF agent and a vCard kind respectively), even when
    the contact point belongs to the actor.
    """
    if not uri:
        return None
    actor = get_actor_by_uri(uri)
    if actor and actor.id != exclude_actor_id:
        return "actor"
    contact = get_contact_point_by_uri(uri)
    if contact and contact.id != exclude_contact_point_id:
        return "contact_point"
    return None


def all_actors(include_inactive=False):
    query = model.Session.query(Actor)
    if not include_inactive:
        query = query.filter(Actor.active.is_(True))
    return by_display_name(query.order_by(Actor.name.asc()).all())


def by_display_name(items):
    """Records in the order of the names the page shows. In the default language that is the database's order of
    the default names, unchanged; in another language the translated names decide (0.7.0)."""
    if language.shows_default(language.current_language()) or not any(item.translations for item in items):
        return items
    return sorted(items, key=lambda item: (item.display_name or "").casefold())


def find_active_actor_by_identifier(identifier_scheme, identifier, exclude_actor_id=None):
    """The active actor already using this (scheme, identifier) pair, if any."""
    if not identifier_scheme or not identifier:
        return None
    query = model.Session.query(Actor).filter(
        Actor.active.is_(True),
        Actor.identifier_scheme == identifier_scheme,
        Actor.identifier == identifier,
    )
    if exclude_actor_id:
        query = query.filter(Actor.id != exclude_actor_id)
    return query.first()


def actors_merged_into(actor_id):
    """Actors whose ``merged_into_id`` points at ``actor_id``.

    Used by the delete flow (``actor_registry_actor_delete``) to warn a
    sysadmin before they permanently delete an actor that one or more
    other, already-merged actors still redirect to. Deleting the target
    doesn't fail -- ``merged_into_id`` is ``ondelete=SET NULL`` -- but
    those other actors' "merged with X" pointers silently go stale, so
    the caller needs to know about it up front rather than after the
    fact.
    """
    return by_display_name(
        model.Session.query(Actor)
        .filter(Actor.merged_into_id == actor_id)
        .order_by(Actor.name.asc())
        .all()
    )


def datasets_for_actor(actor_id):
    """Active dataset ids linked to this actor, split by link type.

    Returns ``{"publisher": [...], "contact_point": [...]}``:

    - "publisher": datasets where this actor is the direct
      ``publisher_actor_id`` (scheming single-select field).
    - "contact_point": datasets that list one of this actor's contact
      points in ``contact_point_ids`` (scheming multi-select field) --
      an indirect link, via ``ContactPoint.actor_id``.

    Both scheming fields live in the dataset's extras -- a jsonb column on CKAN
    2.12, the ``package_extra`` table on 2.11 (see ``extra_text``). SQLAlchemy
    query direct against that column rather than Solr, so results are
    correct independently of indexing/lag. ``publisher_actor_id`` is
    stored as a plain JSON string; ``contact_point_ids`` is stored as a
    JSON string whose *content* is itself a JSON-encoded list (ckanext-
    scheming's standard "multiple_select" behaviour) -- hence the
    ``->> ... ::jsonb`` double-decode below for that field.

    Ids are returned regardless of dataset visibility/privacy. Callers
    that display results to a non-sysadmin should run them through
    ``package_search(fq='id:(...)')`` for permission filtering, the same
    way an organization's dataset list already does.
    """
    session = model.Session

    publisher_rows = session.execute(
        text(
            """
            SELECT id FROM package
            WHERE state = 'active'
              AND {publisher} = :actor_id
            """.format(publisher=extra_text("publisher_actor_id"))
        ),
        {"actor_id": actor_id},
    )
    publisher_ids = [row.id for row in publisher_rows]

    contact_point_ids = [
        contact.id
        for contact in session.query(ContactPoint).filter(ContactPoint.actor_id == actor_id).all()
    ]

    via_contact_point_ids = []
    if contact_point_ids:
        stmt = text(
            """
            SELECT id FROM package
            WHERE state = 'active'
              AND {present}
              AND {contacts} ?| :contact_point_ids
            """.format(present=extra_present("contact_point_ids"), contacts=contact_ids_jsonb())
        ).bindparams(bindparam("contact_point_ids", type_=ARRAY(PG_TEXT)))
        contact_rows = session.execute(stmt, {"contact_point_ids": contact_point_ids})
        via_contact_point_ids = [row.id for row in contact_rows]

    return {"publisher": publisher_ids, "contact_point": via_contact_point_ids}


def datasets_for_contact_point(contact_point_id):
    """Active dataset ids that list this exact contact point in
    ``contact_point_ids`` (a scheming multi-select field, double-encoded --
    see ``datasets_for_actor`` above for the storage details).

    This is the direct counterpart to ``datasets_for_actor``'s
    "contact_point" bucket, but keyed by a specific contact point id rather
    than by the actor that owns it -- used when deleting a contact point
    directly (``actor_registry_contactpoint_delete``), independent of
    whether it belongs to an actor at all.
    """
    session = model.Session
    stmt = text(
        """
        SELECT id FROM package
        WHERE state = 'active'
          AND {present}
          AND {contacts} ? :contact_point_id
        """.format(present=extra_present("contact_point_ids"), contacts=contact_ids_jsonb())
    )
    rows = session.execute(stmt, {"contact_point_id": contact_point_id})
    return [row.id for row in rows]


# Modes of ``linked_datasets`` that list datasets that MISS something (no subject ids needed):
# both a publisher and a contact point ("none"), only the publisher, only the contact
# point, or either one.
MISSING_MODES = ("none", "no_publisher", "no_contact_point", "either")


def linked_datasets(link, subject_ids, is_sysadmin=False, org_ids=(), page=1, per_page=10, only_org_ids=None,
                    field_types=None, filters=None):
    """One page of the datasets linked to registry records, plus the total.

    Reads straight from the database (the source of truth; the search index
    can hold stale documents) and returns ``(rows, total)``, ``rows`` being
    ``{"id", "name", "title", "owner_org", "organization", "private", "modified",
    "has_publisher", "has_contact_point"}`` dicts sorted by title, A-Z (``organization``
    is the owner organisation's title).

    ``link`` is ``"publisher"`` (``publisher_actor_id`` equals one of
    ``subject_ids``) or ``"contact_point"`` (``contact_point_ids`` lists one
    of them). See ``datasets_for_actor`` for how both scheming fields are
    stored. ``"none"`` lists the datasets with NEITHER a publisher NOR a
    contact point (the same definition as ``datasets_without_actor_link``);
    ``"no_publisher"`` those without a publisher, ``"no_contact_point"`` those without
    a contact point and ``"either"`` those missing at least one of the two. For all four
    ``subject_ids`` is ignored.

    Only ``active`` datasets are returned. Visibility is enforced HERE, in
    the same query that counts and pages: private datasets are included
    only for sysadmins or when the dataset's organisation is in ``org_ids``
    (the viewer's organisations). The caller must never post-filter.
    ``only_org_ids`` (a list) further keeps only the datasets of those organisations,
    e.g. to count what an editor may edit.

    ``field_types`` (``{"publisher": types, "contact_point": types}``) makes a dataset
    lack a publisher or a contact point only when its type has that field, so a schema
    without the publisher field never puts its datasets on the To do list for it; rows
    then also say ``publisher_field`` and ``contact_point_field``. Without it every type
    is taken to have both fields. Rows also give ``publisher_id`` and ``contact_point_ids``.

    ``filters`` (the To do page, 0.6.0) narrows the list: ``q`` text in the title, name or
    description, ``tag`` a list of tag names (all of them), ``org`` a list of organisation ids
    (any of them).
    """
    query = _dataset_query(link, subject_ids, is_sysadmin, org_ids, only_org_ids, field_types, filters)
    if query is None:
        return [], 0
    where, params, statement = query["where"], query["params"], query["statement"]
    publisher_missing, contact_points_missing = query["publisher_missing"], query["contact_points_missing"]
    publisher_field, contact_point_field = query["publisher_field"], query["contact_point_field"]
    session = model.Session
    total = session.execute(statement("SELECT count(*) FROM package WHERE " + where), params).scalar()
    page = max(int(page), 1)
    rows = session.execute(
        statement(
            "SELECT id, name, title, owner_org, private, metadata_modified, "
            "NOT " + publisher_missing + " AS has_publisher, NOT " + contact_points_missing
            + " AS has_contact_point, " + publisher_field + " AS publisher_field, " + contact_point_field
            + " AS contact_point_field, " + extra_text("publisher_actor_id") + " AS publisher_id, "
            + contact_ids_jsonb() + " AS contact_point_ids FROM package WHERE " + where
            + " ORDER BY lower(coalesce(nullif(title, ''), name)), name LIMIT :limit OFFSET :offset"
        ),
        dict(params, limit=per_page, offset=(page - 1) * per_page),
    ).fetchall()
    # The organisation's title for each row (2026-10-04: the lists show where a
    # dataset lives and when it last changed). A second, separate query keeps
    # the paged query on the package table alone.
    org_titles = {}
    owner_ids = {r.owner_org for r in rows if r.owner_org}
    if owner_ids:
        org_titles = {
            g.id: g.title or g.name
            for g in session.query(model.Group).filter(model.Group.id.in_(owner_ids))
        }
    return [
        {"id": r.id, "name": r.name, "title": r.title or r.name, "owner_org": r.owner_org,
         "organization": org_titles.get(r.owner_org, ""), "private": bool(r.private),
         "modified": r.metadata_modified, "has_publisher": bool(r.has_publisher),
         "has_contact_point": bool(r.has_contact_point), "publisher_field": bool(r.publisher_field),
         "contact_point_field": bool(r.contact_point_field), "publisher_id": r.publisher_id or "",
         "contact_point_ids": [str(item) for item in (r.contact_point_ids or [])]}
        for r in rows
    ], total


def linked_dataset_facets(link, is_sysadmin=False, org_ids=(), only_org_ids=None, field_types=None, filters=None,
                          limit=200):
    """The tags and organisations of the datasets ``linked_datasets`` lists with the same
    arguments, for the To do page's filters (0.6.0): ``{"tags": [(name, count)], "organizations":
    [(id, title, count)]}``, the most common first. The tags count with every filter, since
    another tag narrows the list further; the organisations leave their own filter out, since
    another organisation widens it."""
    filters = dict(filters or {})
    session = model.Session
    facets = {}
    for key in ("tags", "organizations"):
        query = _dataset_query(link, [], is_sysadmin, org_ids, only_org_ids, field_types,
                               {k: v for k, v in filters.items() if key == "tags" or k != "org"})
        if query is None:
            return {"tags": [], "organizations": []}
        if key == "tags":
            sql = ("SELECT t.name, count(*) AS n FROM (SELECT id FROM package WHERE " + query["where"]
                   + ") p JOIN package_tag pt ON pt.package_id = p.id AND pt.state = 'active' "
                   "JOIN tag t ON t.id = pt.tag_id GROUP BY t.name ORDER BY n DESC, lower(t.name) LIMIT :facet_limit")
            facets[key] = [(r.name, r.n) for r in session.execute(
                query["statement"](sql), dict(query["params"], facet_limit=limit))]
        else:
            sql = ("SELECT g.id, coalesce(nullif(g.title, ''), g.name) AS title, count(*) AS n FROM "
                   "(SELECT owner_org FROM package WHERE " + query["where"] + ") p "
                   "JOIN \"group\" g ON g.id = p.owner_org "
                   "GROUP BY g.id, g.title, g.name ORDER BY lower(coalesce(nullif(g.title, ''), g.name))")
            facets[key] = [(r.id, r.title, r.n) for r in session.execute(query["statement"](sql), query["params"])]
    return facets


def _filter_values(value):
    """A filter's values as a list: the To do page sends a list, a single string still works."""
    if not value:
        return []
    return [value] if isinstance(value, str) else [item for item in value if item]


def _dataset_query(link, subject_ids, is_sysadmin, org_ids, only_org_ids, field_types, filters):
    """The WHERE clause, its parameters and the pieces ``linked_datasets`` and
    ``linked_dataset_facets`` build their statements from; None when nothing can match."""
    filters = filters or {}
    subject_ids = [str(item) for item in subject_ids if item]
    if link not in MISSING_MODES and not subject_ids:
        return None
    publisher = extra_text("publisher_actor_id")
    publisher_missing = "({publisher} IS NULL OR {publisher} = '')".format(publisher=publisher)
    contact_points_missing = "({contacts} = '[]'::jsonb)".format(contacts=contact_ids_jsonb())
    publisher_field = contact_point_field = "true"
    if field_types is not None:
        publisher_field = "(type = ANY(:publisher_types))"
        contact_point_field = "(type = ANY(:contact_point_types))"
        publisher_missing = "({} AND {})".format(publisher_field, publisher_missing)
        contact_points_missing = "({} AND {})".format(contact_point_field, contact_points_missing)
    if link in MISSING_MODES:
        link_clause = {
            "none": "{p} AND {c}",
            "no_publisher": "{p}",
            "no_contact_point": "{c}",
            "either": "({p} OR {c})",
        }[link].format(p=publisher_missing, c=contact_points_missing)
    elif link == "publisher":
        link_clause = "{publisher} = ANY(:subject_ids)".format(publisher=publisher)
    elif link == "contact_point":
        link_clause = "{contacts} ?| :subject_ids".format(contacts=contact_ids_jsonb())
    else:
        raise ValueError("link must be 'publisher', 'contact_point' or one of %s" % (MISSING_MODES,))

    where = (
        "state = 'active' AND (" + link_clause + ") "
        "AND (:all_visible OR private = false OR owner_org = ANY(:org_ids))"
    )
    array = ARRAY(PG_TEXT)
    params = {"all_visible": bool(is_sysadmin), "org_ids": [str(item) for item in org_ids]}
    if link not in MISSING_MODES:
        params["subject_ids"] = subject_ids
    if only_org_ids is not None:
        where += " AND owner_org = ANY(:only_org_ids)"
        params["only_org_ids"] = [str(item) for item in only_org_ids]
    q = (filters.get("q") or "").strip()
    if q:
        where += (" AND (title ILIKE :q ESCAPE '\\' OR name ILIKE :q ESCAPE '\\'"
                  " OR coalesce(notes, '') ILIKE :q ESCAPE '\\')")
        params["q"] = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    # Several tags narrow the list (a dataset has them all), several organisations widen it (a dataset
    # belongs to one of them), as in CKAN's own search.
    for number, tag in enumerate(_filter_values(filters.get("tag"))):
        where += (" AND EXISTS (SELECT 1 FROM package_tag pt JOIN tag t ON t.id = pt.tag_id"
                  " WHERE pt.package_id = package.id AND pt.state = 'active' AND t.name = :tag_%d)" % number)
        params["tag_%d" % number] = tag
    orgs = _filter_values(filters.get("org"))
    if orgs:
        where += " AND owner_org = ANY(:filter_orgs)"
        params["filter_orgs"] = orgs
    if field_types is not None:
        params["publisher_types"] = sorted(field_types.get("publisher") or [])
        params["contact_point_types"] = sorted(field_types.get("contact_point") or [])

    def statement(sql):
        binds = [bindparam("org_ids", type_=array)]
        if link not in MISSING_MODES:
            binds.append(bindparam("subject_ids", type_=array))
        if only_org_ids is not None:
            binds.append(bindparam("only_org_ids", type_=array))
        # Only the ones this statement uses: the count leaves out the row's columns.
        binds += [bindparam(name, type_=array) for name in ("publisher_types", "contact_point_types", "filter_orgs")
                  if ":" + name in sql]
        return text(sql).bindparams(*binds)

    return {"where": where, "params": params, "statement": statement,
            "publisher_missing": publisher_missing, "contact_points_missing": contact_points_missing,
            "publisher_field": publisher_field, "contact_point_field": contact_point_field}


def datasets_without_actor_link():
    """Ids of active datasets with NEITHER a publisher NOR a contact-point link.

    A dataset only qualifies when it is missing *both* actor-managed
    fields (Björn's confirmed definition, 2026-09-15): no
    ``publisher_actor_id`` at all (missing key or blank string) AND no
    non-empty ``contact_point_ids`` (missing key, blank string, or an
    empty JSON list -- see ``datasets_for_actor`` above for why that
    field is double-decoded). This is meant for activating the extension
    on an existing installation, where every dataset predates any actor
    link: it surfaces the backlog that still needs linking.

    Ids are returned regardless of dataset visibility/privacy -- run
    through ``package_search(fq='id:(...)')`` for permission filtering
    before displaying to a non-sysadmin, same as ``datasets_for_actor``.
    """
    session = model.Session

    rows = session.execute(
        text(
            """
            SELECT id FROM package
            WHERE state = 'active'
              AND ({publisher} IS NULL OR {publisher} = '')
              AND {contacts} = '[]'::jsonb
            """.format(
                publisher=extra_text("publisher_actor_id"),
                present=extra_present("contact_point_ids"),
                contacts=contact_ids_jsonb(),
            )
        )
    )
    return [row.id for row in rows]


class UserPreference(toolkit.BaseModel):
    """Small per-CKAN-user preferences owned by the registry extension."""

    __tablename__ = "actor_registry_user_preference"

    user_id = Column(String(36), primary_key=True)
    publisher_actor_id = Column(
        String(36), ForeignKey("actor_registry_actor.id", ondelete="SET NULL"), nullable=True
    )
    modified = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class RecentContactPoint(toolkit.BaseModel):
    """A contact point recently used by a CKAN user."""

    __tablename__ = "actor_registry_recent_contact_point"

    user_id = Column(String(36), primary_key=True)
    contact_point_id = Column(
        String(36), ForeignKey("contactpoints_contact_point.id", ondelete="CASCADE"),
        primary_key=True,
    )
    used_at = Column(DateTime, nullable=False, default=datetime.utcnow)


def preferred_publisher(user_id):
    if not user_id:
        return None
    preference = model.Session.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not preference or not preference.publisher_actor_id:
        return None
    actor = get_actor(preference.publisher_actor_id)
    return actor if actor and actor.active else None


def remember_publisher(user_id, actor_id):
    if not user_id or not actor_id or not get_actor(actor_id):
        return
    preference = model.Session.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if preference:
        preference.publisher_actor_id = actor_id
        preference.modified = datetime.utcnow()
    else:
        model.Session.add(UserPreference(user_id=user_id, publisher_actor_id=actor_id))
    # Package create/update owns the surrounding transaction.
    model.Session.flush()


def recent_contact_points(user_id, limit=3):
    if not user_id:
        return []
    return (
        model.Session.query(ContactPoint)
        .join(RecentContactPoint, RecentContactPoint.contact_point_id == ContactPoint.id)
        .filter(RecentContactPoint.user_id == user_id, ContactPoint.active.is_(True))
        .order_by(RecentContactPoint.used_at.desc(), ContactPoint.name.asc())
        .limit(limit)
        .all()
    )


def remember_contact_points(user_id, contact_ids):
    if not user_id or not contact_ids:
        return
    if isinstance(contact_ids, str):
        contact_ids = [contact_ids]
    now = datetime.utcnow()
    for contact_id in contact_ids:
        if not get_contact_point(contact_id):
            continue
        recent = (
            model.Session.query(RecentContactPoint)
            .filter(
                RecentContactPoint.user_id == user_id,
                RecentContactPoint.contact_point_id == contact_id,
            )
            .first()
        )
        if recent:
            recent.used_at = now
        else:
            model.Session.add(
                RecentContactPoint(user_id=user_id, contact_point_id=contact_id, used_at=now)
            )
    model.Session.flush()
