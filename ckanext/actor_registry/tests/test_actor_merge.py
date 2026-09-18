import uuid

import pytest
from bs4 import BeautifulSoup

from ckan import model as ckan_model
from ckan.plugins import toolkit
from ckan.tests import factories, helpers

from ckanext.actor_registry import model


pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry"),
    pytest.mark.usefixtures("with_plugins", "actor_registry_db"),
]


def _actor(name, **overrides):
    identifier = overrides.pop("id", str(uuid.uuid4()))
    item = model.Actor(
        id=identifier,
        name=name,
        actor_kind=overrides.pop("actor_kind", "organization"),
        uri=overrides.pop("uri", f"https://example.org/actor/{identifier}"),
        active=overrides.pop("active", True),
        **overrides,
    )
    ckan_model.Session.add(item)
    ckan_model.Session.flush()
    return item


def _contact(name, actor_id=None):
    identifier = str(uuid.uuid4())
    item = model.ContactPoint(
        id=identifier,
        name=name,
        actor_id=actor_id,
        uri=f"https://example.org/contact/{identifier}",
        active=True,
    )
    ckan_model.Session.add(item)
    ckan_model.Session.flush()
    return item


# See test_views.py for why token auth (not REMOTE_USER) is used here.
def _auth_headers(user_with_token):
    return {"Authorization": user_with_token["token"]}


def _csrf_token(response):
    field = BeautifulSoup(response.data, "html.parser").select_one(
        'input[name="_csrf_token"]'
    )
    assert field is not None
    return field["value"]


# --- Action-level: actor_registry_actor_merge --------------------------


def test_merge_writes_chosen_fields_moves_contacts_and_retires_source():
    keep = _actor("Kvarvarande nämnd")
    merge = _actor("Bortslagen nämnd", email="old@example.org")
    contact = _contact("Kontaktcenter", actor_id=merge.id)
    sysadmin = factories.Sysadmin()

    result = toolkit.get_action("actor_registry_actor_merge")(
        {"user": sysadmin["name"]},
        {
            "keep_id": keep.id,
            "merge_id": merge.id,
            "fields": {"email": "new@example.org"},
        },
    )

    ckan_model.Session.refresh(keep)
    ckan_model.Session.refresh(merge)
    ckan_model.Session.refresh(contact)

    assert result["moved_contact_points"] == 1
    assert keep.email == "new@example.org"
    assert keep.active is True
    assert merge.active is False
    assert merge.merged_into_id == keep.id
    assert contact.actor_id == keep.id


def test_merge_repoints_remembered_publisher_preference():
    keep = _actor("Kvarvarande nämnd")
    merge = _actor("Bortslagen nämnd")
    sysadmin = factories.Sysadmin()
    model.remember_publisher("user-1", merge.id)

    toolkit.get_action("actor_registry_actor_merge")(
        {"user": sysadmin["name"]},
        {"keep_id": keep.id, "merge_id": merge.id},
    )

    preferred = model.preferred_publisher("user-1")
    assert preferred is not None
    assert preferred.id == keep.id


def test_merge_rejects_merging_actor_with_itself():
    keep = _actor("Ensam nämnd")
    sysadmin = factories.Sysadmin()

    with pytest.raises(toolkit.ValidationError):
        toolkit.get_action("actor_registry_actor_merge")(
            {"user": sysadmin["name"]},
            {"keep_id": keep.id, "merge_id": keep.id},
        )


def test_merge_rejects_uri_as_a_mergeable_field():
    keep = _actor("A")
    merge = _actor("B")
    sysadmin = factories.Sysadmin()

    with pytest.raises(toolkit.ValidationError):
        toolkit.get_action("actor_registry_actor_merge")(
            {"user": sysadmin["name"]},
            {
                "keep_id": keep.id,
                "merge_id": merge.id,
                "fields": {"uri": "https://example.org/not-allowed"},
            },
        )


def test_merge_rejects_already_retired_source_actor():
    keep = _actor("A")
    already_merged = _actor("B", active=False)
    sysadmin = factories.Sysadmin()

    with pytest.raises(toolkit.ObjectNotFound):
        toolkit.get_action("actor_registry_actor_merge")(
            {"user": sysadmin["name"]},
            {"keep_id": keep.id, "merge_id": already_merged.id},
        )


def test_normal_user_cannot_call_merge_action():
    keep = _actor("A")
    merge = _actor("B")
    user = factories.User()

    with pytest.raises(toolkit.NotAuthorized):
        toolkit.get_action("actor_registry_actor_merge")(
            {"user": user["name"]},
            {"keep_id": keep.id, "merge_id": merge.id},
        )


# --- View-level: /actors/merge ------------------------------------------


def test_merge_page_rejects_anonymous_and_normal_users(app):
    a = _actor("A")
    b = _actor("B")

    assert app.get(f"/actors/merge?ids={a.id},{b.id}").status_code == 403

    user = factories.UserWithToken()
    assert (
        app.get(
            f"/actors/merge?ids={a.id},{b.id}", headers=_auth_headers(user)
        ).status_code
        == 403
    )


def test_merge_page_renders_comparison_for_sysadmin(app):
    a = _actor("Alfa nämnd")
    b = _actor("Beta nämnd")
    sysadmin = factories.SysadminWithToken()

    response = app.get(
        f"/actors/merge?ids={a.id},{b.id}", headers=_auth_headers(sysadmin)
    )

    assert response.status_code == 200
    assert "Alfa nämnd" in response.body
    assert "Beta nämnd" in response.body


def test_merge_submit_performs_merge_and_redirects_to_kept_actor(app):
    a = _actor("Alfa nämnd")
    b = _actor("Beta nämnd", email="beta@example.org")
    sysadmin = factories.SysadminWithToken()
    headers = _auth_headers(sysadmin)
    form = app.get(f"/actors/merge?ids={a.id},{b.id}", headers=headers)

    response = app.post(
        "/actors/merge",
        data={
            "_csrf_token": _csrf_token(form),
            "actor_a_id": a.id,
            "actor_b_id": b.id,
            "keep_id": a.id,
            "override_email": "beta@example.org",
        },
        headers=headers,
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.location.endswith(f"/actors/{a.id}")

    # The POST went through the Flask test client, i.e. a real HTTP
    # request/response cycle -- CKAN's app-context teardown detaches
    # objects loaded in the test's own Session, so `a`/`b` from before the
    # request are no longer valid to Session.refresh(). Re-fetch instead.
    keep = model.get_actor(a.id)
    merged = model.get_actor(b.id)
    assert keep.email == "beta@example.org"
    assert merged.active is False
    assert merged.merged_into_id == keep.id


# --- A merged (soft-retired) actor's URI still resolves -----------------
#
# Full RDF markup for a merged actor (e.g. dct:isReplacedBy) is explicitly
# a nice-to-have in aktorsregister-sammanslagning-plan.md, not blocking for
# the PoC -- there is no per-actor RDF/content-negotiation endpoint in this
# extension to extend yet (ckanext-dcat's RDF profile only covers dataset
# export, see test_rdf_endpoint.py). This pins the part that IS decided:
# the page must keep responding 200 with a clear pointer to the surviving
# actor, never a dead link or 404.
def test_merged_actor_page_still_resolves_with_a_clear_notice(app):
    a = _actor("Alfa nämnd")
    b = _actor("Beta nämnd")
    b.active = False
    b.merged_into_id = a.id
    ckan_model.Session.commit()

    response = app.get(f"/actors/{b.id}")

    assert response.status_code == 200
    assert "has been merged with" in response.body
    assert a.name in response.body
