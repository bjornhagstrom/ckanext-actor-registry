"""Validation of actor (publisher) and contact point data -- ONE shared layer.

Everything that writes registry data goes through this module: the full forms, the
inline dialogs and the ``actor_registry_actor_merge`` action. The rules are CKAN
validators (``(value, context)`` returning the normalised value or raising
``toolkit.Invalid``) collected in schemas that CKAN's own ``navl`` machinery runs, the
same mechanism CKAN uses for its own objects. The result is an ordinary CKAN error
dict (``{field: [message, ...]}``), so a caller can show the first message (the forms)
or raise ``toolkit.ValidationError`` (an action, and any API added later).

Deliberately lenient where strictness would only annoy editors: a phone number is
checked only for plausible characters and length, and nothing is verified against the
network. An empty value is always valid (all of these fields are optional).

Reuse over reinvention: an email address is checked with CKAN's own ``email_validator``,
so the registry accepts and rejects what CKAN itself does (it is ASCII-only, so
internationalised domains are rejected -- CKAN's choice), plus one extra rule: the
domain must contain a dot, because CKAN itself accepts ``name@host``. CKAN's
``url_validator`` is deliberately NOT reused: it rejects hostnames that are not plain
ASCII, i.e. Swedish IDN domains such as ``räksmörgås.se``.

Two safety nets apply to every field:

* a maximum length, matching the database column (a longer value would otherwise be a
  database error, i.e. an HTTP 500);
* a value that is *unchanged* from what is already stored is not re-validated, so a
  record saved before a rule existed can still be edited (a dialog that does not show
  every field would otherwise be blocked by an error the user cannot see).
"""

import re
from urllib.parse import urlparse

import ckan.plugins.toolkit as toolkit

from ckanext.actor_registry import model as registry_model

ACTOR_KINDS = ("organization", "person")
URI_SCHEMES = ("http", "https", "urn")

_PHONE_CHARS = re.compile(r"^[0-9 +()\-./]+$")

# Field labels for the length message. They are existing, translated UI strings.
_LABELS = {
    "name": "Name",
    "actor_kind": "Kind",
    "actor_type": "Type",
    "identifier": "Identifier",
    "identifier_scheme": "Identifier scheme",
    "uri": "Persistent URI",
    "url": "URL",
    "email": "Email",
    "phone": "Phone",
    "description": "Description",
}


# --- Validators ---------------------------------------------------------------------------


def max_length(field, limit):
    """A validator that rejects a value longer than ``limit`` characters."""

    def validator(value, context):
        if value and len(value) > limit:
            raise toolkit.Invalid(
                toolkit._("{field} is too long: at most {max} characters.").format(
                    field=toolkit._(_LABELS.get(field, field)), max=limit
                )
            )
        return value

    return validator


def valid_email(value, context):
    value = (value or "").strip()
    if not value:
        return ""
    value = value.lower()
    message = toolkit._("Enter a valid email address, for example name@example.org.")
    try:
        toolkit.get_validator("email_validator")(value, {})
    except toolkit.Invalid:
        raise toolkit.Invalid(message)
    # CKAN accepts "name@host" (no top-level domain). In a public catalogue that is
    # nearly always a typo, so a dot in the domain is required on top of CKAN's check.
    if "." not in value.rsplit("@", 1)[-1]:
        raise toolkit.Invalid(message)
    return value


def valid_url(value, context):
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc or " " in value:
        raise toolkit.Invalid(toolkit._("Enter a full web address starting with http:// or https://."))
    return value


def valid_uri(value, context):
    """An absolute URI: ``http(s)://host/...`` or ``urn:...``; no spaces."""
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    ok = scheme in URI_SCHEMES and " " not in value and (
        bool(parsed.netloc) if scheme in ("http", "https") else bool(parsed.path)
    )
    if not ok:
        raise toolkit.Invalid(toolkit._("Enter an absolute URI starting with http://, https:// or urn:."))
    return value


def valid_phone(value, context):
    value = re.sub(r"\s+", " ", (value or "").strip())
    if not value:
        return ""
    digits = re.sub(r"\D", "", value)
    if not _PHONE_CHARS.match(value) or len(digits) < 5:
        raise toolkit.Invalid(
            toolkit._("Enter a phone number using digits, spaces and the characters + ( ) - only.")
        )
    return value


def valid_actor_kind(value, context):
    if value not in ACTOR_KINDS:
        raise toolkit.Invalid(toolkit._("The kind must be either organization or person."))
    return value


# --- Schemas -------------------------------------------------------------------------------
# Maximum lengths follow the database columns (String(255) etc.); text columns get a
# generous cap so a pasted document cannot be stored by accident. Field order is the
# order in which errors are reported.

ACTOR_SCHEMA = {
    "name": [max_length("name", 255)],
    "actor_kind": [valid_actor_kind],
    "actor_type": [max_length("actor_type", 2048), valid_uri],
    "identifier": [max_length("identifier", 255)],
    "identifier_scheme": [max_length("identifier_scheme", 255)],
    "uri": [max_length("uri", 2048), valid_uri],
    "url": [max_length("url", 2048), valid_url],
    "email": [max_length("email", 320), valid_email],
    "description": [max_length("description", 10000)],
}

CONTACT_POINT_SCHEMA = {
    "name": [max_length("name", 255)],
    "email": [max_length("email", 320), valid_email],
    "phone": [max_length("phone", 100), valid_phone],
    "url": [max_length("url", 2048), valid_url],
    "uri": [max_length("uri", 2048), valid_uri],
}


def validate(values, schema, existing=None):
    """Validate the fields of ``values`` that ``schema`` covers; return an error dict.

    ``values`` is updated in place with the normalised values (trimmed, lowercased
    email, ...). A field that is absent, or equal to the value already stored on
    ``existing``, is not checked (see the module docstring). Returns CKAN's usual
    ``{field: [message, ...]}`` mapping, empty when everything is valid.
    """
    to_check = {}
    for field in schema:
        if field not in values:
            continue
        if existing is not None and values[field] == (getattr(existing, field, None) or ""):
            continue
        to_check[field] = values[field]
    if not to_check:
        return {}
    data, errors = toolkit.navl_validate(to_check, {field: schema[field] for field in to_check}, {})
    for field in to_check:
        if field in data and field not in errors:
            values[field] = data[field]
    return errors


def validate_actor(values, existing=None):
    return validate(values, ACTOR_SCHEMA, existing)


def validate_contact_point(values, existing=None):
    return validate(values, CONTACT_POINT_SCHEMA, existing)


def first_error(errors, schema):
    """The first message of an error dict, in the schema's field order."""
    for field in schema:
        if errors.get(field):
            return errors[field][0]
    for messages in errors.values():
        if messages:
            return messages[0]
    return None


# --- Rules that need the registry ---------------------------------------------------------


def identifier_error(scheme, identifier, active=True, exclude_ids=()):
    """Localised error for an invalid identifier/scheme pair, or None.

    Identifier and scheme are optional, but if one is given both are required; the pair
    must be unique among active actors (the same identifier may exist under a different
    scheme). ``exclude_ids`` are actors that do not count as a clash (the actor being
    edited, or the one being merged away).
    """
    if bool(scheme) != bool(identifier):
        return toolkit._("Identifier and identifier scheme must be filled in together.")
    if not (scheme and identifier and active):
        return None
    clash = registry_model.find_active_actor_by_identifier(scheme, identifier)
    if clash and clash.id not in set(exclude_ids):
        return toolkit._(
            'The identifier "{identifier}" with scheme "{scheme}" is already used by the publisher "{name}".'
        ).format(identifier=identifier, scheme=scheme, name=clash.name)
    return None


def organization_error(actor_id, existing=None):
    """A contact point may only be linked to an existing, active actor.

    An unchanged, already-saved link is never re-validated: an edit must not be blocked
    because the owning organization was retired since.
    """
    if not actor_id or actor_id == getattr(existing, "actor_id", None):
        return None
    actor = registry_model.get_actor(actor_id)
    if not actor or not actor.active:
        return toolkit._("The selected organization does not exist or is no longer active.")
    return None


def actor_error(values, existing=None):
    """First validation error for an actor's values (normalises them in place), or None."""
    error = first_error(validate_actor(values, existing), ACTOR_SCHEMA)
    return error or identifier_error(
        values.get("identifier_scheme", ""), values.get("identifier", ""),
        active=values.get("active", True), exclude_ids=[existing.id] if existing is not None else (),
    )


def contact_point_error(values, existing=None):
    """First validation error for a contact point's values, or None."""
    error = first_error(validate_contact_point(values, existing), CONTACT_POINT_SCHEMA)
    return error or organization_error(values.get("actor_id"), existing)


# --- Tuple adapters (value, error) for single fields --------------------------------------
# Kept for callers and tests that check one value at a time.


def _pair(validator):
    def check(value):
        try:
            return validator(value, {}), None
        except toolkit.Invalid as error:
            return value, error.error

    return check


normalise_email = _pair(valid_email)
normalise_url = _pair(valid_url)
normalise_phone = _pair(valid_phone)
check_uri = _pair(valid_uri)
check_kind = _pair(valid_actor_kind)
