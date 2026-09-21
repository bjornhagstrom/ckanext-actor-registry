"""The shared validation layer: one set of rules for the forms, the dialogs and the
merge action, run with CKAN's own navl machinery and reporting CKAN's error dicts."""

import uuid

import pytest

from ckan import model as ckan_model
from ckan.plugins import toolkit
from ckan.tests import factories

from ckanext.actor_registry import model, validation

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry"),
    pytest.mark.usefixtures("with_plugins", "actor_registry_db"),
]


def _actor(name, **extra):
    actor_id = str(uuid.uuid4())
    ckan_model.Session.add(
        model.Actor(id=actor_id, name=name, actor_kind="organization",
                    uri=f"https://example.org/actor/{actor_id}", active=extra.pop("active", True), **extra)
    )
    ckan_model.Session.commit()
    return model.get_actor(actor_id)


def _merge(keep, merge, **fields):
    sysadmin = factories.Sysadmin()
    return toolkit.get_action("actor_registry_actor_merge")(
        {"user": sysadmin["name"]}, {"keep_id": keep.id, "merge_id": merge.id, "fields": fields}
    )


# --- The layer itself ---------------------------------------------------------------------


def test_validate_returns_a_ckan_style_error_dict_and_normalises_in_place():
    values = {"name": "x" * 300, "email": " INFO@Example.ORG ", "url": "ftp://x", "phone": "call me"}

    errors = validation.validate(values, {**validation.ACTOR_SCHEMA, "phone": validation.CONTACT_POINT_SCHEMA["phone"]})

    assert set(errors) == {"name", "url", "phone"}
    assert all(isinstance(messages, list) and messages for messages in errors.values())
    assert values["email"] == "info@example.org"  # valid, so normalised


def test_a_valid_record_gives_no_errors():
    values = {"name": "Ok", "actor_kind": "person", "email": "a@example.org", "url": "https://example.org",
              "uri": "urn:uuid:6e8bc430-9c3a-11d9-9669-0800200c9a66", "actor_type": "https://example.org/t"}

    assert validation.validate_actor(values) == {}


def test_first_error_follows_the_schema_order_not_the_dict_order():
    errors = {"email": ["email problem"], "name": ["name problem"]}

    assert validation.first_error(errors, validation.ACTOR_SCHEMA) == "name problem"


def test_unchanged_values_are_not_revalidated_but_changed_ones_are():
    legacy = _actor("Gammal", email="Broken..Mail@@x")

    assert validation.validate_actor({"email": "Broken..Mail@@x"}, existing=legacy) == {}
    assert "email" in validation.validate_actor({"email": "another..broken@@x"}, existing=legacy)


def test_identifier_error_rules():
    first = _actor("Först", identifier="A-1", identifier_scheme="SCHEME")
    assert validation.identifier_error("SCHEME", "") and validation.identifier_error("", "A-1")  # together
    assert "Först" in validation.identifier_error("SCHEME", "A-1")  # names the clash
    assert validation.identifier_error("OTHER", "A-1") is None  # other scheme is fine
    assert validation.identifier_error("SCHEME", "A-1", active=False) is None  # only active ones clash
    assert validation.identifier_error("SCHEME", "A-1", exclude_ids=[first.id]) is None


# --- The merge action now validates what it writes ------------------------------------------


def test_merge_rejects_an_invalid_chosen_value():
    keep, gone = _actor("Kvar"), _actor("Bort")

    with pytest.raises(toolkit.ValidationError) as caught:
        _merge(keep, gone, email="not-an-email")

    assert "fields" in caught.value.error_dict
    assert "valid email" in caught.value.error_dict["fields"][0]
    ckan_model.Session.expire_all()
    assert model.get_actor(gone.id).active is True  # nothing was changed
    assert not model.get_actor(keep.id).email


def test_merge_rejects_a_too_long_value_instead_of_failing_in_the_database():
    keep, gone = _actor("Kvar2"), _actor("Bort2")

    with pytest.raises(toolkit.ValidationError) as caught:
        _merge(keep, gone, name="x" * 300)

    assert "at most 255" in caught.value.error_dict["fields"][0]


def test_merge_rejects_an_identifier_that_clashes_with_a_third_publisher():
    keep, gone = _actor("Kvar3"), _actor("Bort3")
    _actor("Tredje", identifier="X-9", identifier_scheme="ORG")

    with pytest.raises(toolkit.ValidationError) as caught:
        _merge(keep, gone, identifier="X-9", identifier_scheme="ORG")

    assert "Tredje" in caught.value.error_dict["fields"][0]
    ckan_model.Session.expire_all()
    assert model.get_actor(gone.id).active is True


def test_merge_rejects_half_an_identifier_pair():
    keep, gone = _actor("Kvar4"), _actor("Bort4")

    with pytest.raises(toolkit.ValidationError) as caught:
        _merge(keep, gone, identifier="ONLY-ID")

    assert "together" in caught.value.error_dict["fields"][0]


def test_a_valid_merge_still_works_including_taking_over_the_retired_identifier():
    keep = _actor("Kvar5")
    gone = _actor("Bort5", identifier="Z-1", identifier_scheme="ORG")

    _merge(keep, gone, identifier="Z-1", identifier_scheme="ORG", email="Ny@Example.org", url="https://example.org")

    ckan_model.Session.expire_all()
    merged = model.get_actor(keep.id)
    assert (merged.identifier, merged.identifier_scheme, merged.email) == ("Z-1", "ORG", "ny@example.org")
    assert model.get_actor(gone.id).active is False
