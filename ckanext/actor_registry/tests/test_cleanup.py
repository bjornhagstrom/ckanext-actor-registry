"""Inactive or missing registry records still used by datasets: the publisher
field keeps an inactive publisher with clear messages, and the clean-up page
lists such references and replaces them on the datasets the user may edit."""

import uuid

import pytest

from ckan import model as ckan_model
from ckan.plugins import toolkit
from ckan.tests import factories, helpers

from ckanext.actor_registry import cleanup
from ckanext.actor_registry import model
from ckanext.actor_registry.tests.test_contact_migration import (
    _contact_point, _dataset, _get, _mark, _org, _page_mark, _set_column)


def _actor(name="City Board", active=True):
    item = model.Actor(id=str(uuid.uuid4()), name=name, actor_kind="organization",
                       uri=f"https://example.org/a/{uuid.uuid4()}", active=active)
    ckan_model.Session.add(item)
    ckan_model.Session.commit()
    return item


def _deactivate(record, merged_into=None):
    ckan_model.Session.expire_all()
    record = ckan_model.Session.merge(record)
    record.active = False
    if merged_into is not None:
        record.merged_into_id = merged_into.id
    ckan_model.Session.commit()


def _patch(user, dataset, **fields):
    return helpers.call_action("package_patch", context={"user": user}, id=dataset["id"], **fields)


def _show(dataset):
    return helpers.call_action("package_show", id=dataset["id"])


# --- The publisher field ---------------------------------------------------------------------


@_mark
def test_a_deactivated_publisher_does_not_lock_the_dataset():
    sysadmin = factories.Sysadmin()
    actor = _actor()
    dataset = _dataset(_org(), publisher_actor_id=actor.id)
    _deactivate(actor)
    assert _patch(sysadmin["name"], dataset, title="Renamed")["publisher_actor_id"] == actor.id


@_mark
def test_choosing_an_inactive_or_missing_publisher_names_it():
    sysadmin = factories.Sysadmin()
    actor = _actor(name="Old Board")
    _deactivate(actor)
    dataset = _dataset(_org())
    with pytest.raises(toolkit.ValidationError) as caught:
        _patch(sysadmin["name"], dataset, publisher_actor_id=actor.id)
    assert caught.value.error_dict["publisher_actor_id"] == [
        "The publisher “Old Board” is inactive and can no longer be chosen. Choose an active publisher."]
    with pytest.raises(toolkit.ValidationError) as caught:
        _patch(sysadmin["name"], dataset, publisher_actor_id="gone-1")
    assert caught.value.error_dict["publisher_actor_id"] == [
        "The selected publisher no longer exists (id gone-1). Choose another publisher."]


@_page_mark
def test_the_form_shows_an_inactive_publisher_and_does_not_offer_it_to_others(app):
    sysadmin = factories.SysadminWithToken()
    actor = _actor(name="Old Board")
    dataset = _dataset(_org(), publisher_actor_id=actor.id)
    _deactivate(actor)
    form = _get(app, sysadmin, f"/dataset/edit/{dataset['name']}")
    assert f'<option value="{actor.id}" selected data-unavailable="inactive">Old Board (inactive)</option>' in form
    assert 'data-publisher-unavailable="inactive"' in form
    new_form = _get(app, sysadmin, "/dataset/new")
    assert "Old Board" not in new_form


@_page_mark
def test_the_form_shows_a_missing_publisher(app):
    sysadmin = factories.SysadminWithToken()
    dataset = _dataset(_org())
    package = ckan_model.Package.get(dataset["id"])
    package.extras = dict(package.extras, publisher_actor_id="gone-1")
    ckan_model.Session.commit()
    from ckan.lib.search import rebuild
    rebuild(dataset["id"])
    form = _get(app, sysadmin, f"/dataset/edit/{dataset['name']}")
    assert 'data-unavailable="missing">Unknown publisher (gone-1)</option>' in form


# --- The clean-up survey --------------------------------------------------------------------


@_mark
def test_survey_lists_inactive_records_in_use_and_missing_references():
    sysadmin = factories.Sysadmin()
    org = _org()
    used, unused, active = _actor("Used Board"), _actor("Unused Board"), _actor("Active Board")
    old_contact = _contact_point(name="Old Desk")
    first = _dataset(org, publisher_actor_id=used.id, contact_point_ids=[old_contact.id])
    _dataset(org, publisher_actor_id=active.id)
    broken = _dataset(org)
    _set_column(broken["id"], contact_point_ids='["gone-contact"]')
    for record in (used, unused):
        _deactivate(record)
    _deactivate(old_contact)
    data = cleanup.survey(sysadmin["name"])
    assert [(entry["record"].name, entry["total"]) for entry in data["publishers"]] == [("Used Board", 1)]
    assert [entry["record"].name for entry in data["contact_points"]] == ["Old Desk"]
    assert [(entry["kind"], entry["id"]) for entry in data["missing"]] == [("contact_point", "gone-contact")]
    assert data["publishers"][0]["datasets"][0]["id"] == first["id"]
    assert cleanup.count(sysadmin["name"]) == 3


@_mark
def test_editors_see_only_entries_with_their_own_datasets():
    editor = factories.User()
    own, other = _org(users=[(editor, "editor")]), _org()
    shared, foreign = _actor("Shared Board"), _actor("Foreign Board")
    mine = _dataset(own, publisher_actor_id=shared.id)
    _dataset(other, publisher_actor_id=shared.id)
    _dataset(other, publisher_actor_id=foreign.id)
    _deactivate(shared)
    _deactivate(foreign)
    [entry] = cleanup.survey(editor["name"])["publishers"]
    assert entry["record"].name == "Shared Board"
    assert entry["total"] == 2 and [item["id"] for item in entry["datasets"]] == [mine["id"]]


@_mark
def test_a_merged_publisher_suggests_its_target():
    sysadmin = factories.Sysadmin()
    target, merged = _actor("New Board"), _actor("Old Board")
    _dataset(_org(), publisher_actor_id=merged.id)
    _deactivate(merged, merged_into=target)
    [entry] = cleanup.survey(sysadmin["name"])["publishers"]
    assert entry["merged_into"].id == target.id


@_mark
def test_broken_stored_values_do_not_break_the_survey():
    sysadmin = factories.Sysadmin()
    dataset = _dataset(_org())
    _set_column(dataset["id"], contact_point_ids="[not json")
    assert cleanup.survey(sysadmin["name"]) == {"publishers": [], "contact_points": [], "missing": []}


# --- Replacing ------------------------------------------------------------------------------


@_mark
def test_replace_a_publisher_only_on_the_users_datasets():
    editor = factories.User()
    own, other = _org(users=[(editor, "editor")]), _org()
    old, new = _actor("Old Board"), _actor("New Board")
    mine = _dataset(own, publisher_actor_id=old.id)
    theirs = _dataset(other, publisher_actor_id=old.id)
    _deactivate(old)
    changed, failures = cleanup.replace(editor["name"], "publisher", old.id, new.id)
    assert [item["id"] for item in changed] == [mine["id"]] and failures == []
    assert _show(mine)["publisher_actor_id"] == new.id
    assert _show(theirs)["publisher_actor_id"] == old.id


@_mark
def test_replace_a_contact_point_keeps_the_others_and_avoids_duplicates():
    sysadmin = factories.Sysadmin()
    org = _org()
    old, keep, new = _contact_point(name="Old"), _contact_point(name="Keep"), _contact_point(name="New")
    first = _dataset(org, contact_point_ids=[old.id, keep.id])
    second = _dataset(org, contact_point_ids=[old.id, new.id])
    _deactivate(old)
    cleanup.replace(sysadmin["name"], "contact_point", old.id, new.id)
    # Scheming keeps the list in the order of the choices (by name).
    assert sorted(_show(first)["contact_point_ids"]) == sorted([new.id, keep.id])
    assert _show(second)["contact_point_ids"] == [new.id]


@_mark
def test_remove_a_missing_contact_point_reference():
    sysadmin = factories.Sysadmin()
    keep = _contact_point(name="Keep")
    dataset = _dataset(_org())
    _set_column(dataset["id"], contact_point_ids=f'["gone-contact", "{keep.id}"]')
    changed, _ = cleanup.replace(sysadmin["name"], "contact_point", "gone-contact", cleanup.REMOVE)
    assert len(changed) == 1 and _show(dataset)["contact_point_ids"] == [keep.id]
    assert cleanup.survey(sysadmin["name"])["missing"] == []


@_mark
def test_remove_an_optional_publisher():
    sysadmin = factories.Sysadmin()
    old = _actor()
    dataset = _dataset(_org(), publisher_actor_id=old.id)
    _deactivate(old)
    cleanup.replace(sysadmin["name"], "publisher", old.id, cleanup.REMOVE)
    assert not _show(dataset).get("publisher_actor_id")


@_mark
def test_a_dataset_that_cannot_be_saved_is_reported_and_the_rest_are_changed():
    sysadmin = factories.Sysadmin()
    org = _org()
    old, new = _actor("Old"), _actor("New")
    good = _dataset(org, publisher_actor_id=old.id)
    bad = _dataset(org, title="Broken", publisher_actor_id=old.id)
    _set_column(bad["id"], notes="")
    _deactivate(old)
    changed, failures = cleanup.replace(sysadmin["name"], "publisher", old.id, new.id)
    assert [item["id"] for item in changed] == [good["id"]]
    assert [title for title, _message in failures] == ["Broken"]


@_mark
@pytest.mark.parametrize("case", ["same", "inactive_target", "missing_target", "kind", "nothing", "no_choice"])
def test_invalid_replacements_change_nothing(case):
    sysadmin = factories.Sysadmin()
    old, spare = _actor("Old"), _actor("Spare")
    dataset = _dataset(_org(), publisher_actor_id=old.id)
    _deactivate(old)
    kind, old_id, new_id = "publisher", old.id, spare.id
    if case == "same":
        new_id = old.id
    elif case == "inactive_target":
        _deactivate(spare)
    elif case == "missing_target":
        new_id = "gone"
    elif case == "kind":
        kind = "something"
    elif case == "nothing":
        old_id = spare.id
    elif case == "no_choice":
        new_id = ""
    with pytest.raises(cleanup.CleanupError):
        cleanup.replace(sysadmin["name"], kind, old_id, new_id)
    assert _show(dataset)["publisher_actor_id"] == old.id


# --- The page -------------------------------------------------------------------------------


@_page_mark
def test_the_page_hint_and_replace(app):
    sysadmin = factories.SysadminWithToken()
    old, new = _actor("Old Board"), _actor("New Board")
    dataset = _dataset(_org(), publisher_actor_id=old.id)
    _deactivate(old)
    html = _get(app, sysadmin, "/actor-registry/cleanup")
    assert f'data-cleanup-entry="{old.id}"' in html and "Old Board" in html
    assert '<option value="" disabled selected>Choose…</option>' in html
    for url in ("/actors", "/contactpoints"):
        assert "data-cleanup-hint" in _get(app, sysadmin, url)
    html = app.post("/actor-registry/cleanup/replace", headers={"Authorization": sysadmin["token"]},
                    data={"kind": "publisher", "old_id": old.id, "new_id": new.id},
                    follow_redirects=True).get_data(as_text=True)
    assert "data-cleanup-empty" in html
    assert _show(dataset)["publisher_actor_id"] == new.id


@_page_mark
def test_access_to_the_cleanup_page(app):
    member = factories.UserWithToken()
    _org(users=[(member, "member")])
    _get(app, member, "/actor-registry/cleanup", status=403)
    app.post("/actor-registry/cleanup/replace", headers={"Authorization": member["token"]},
             data={"kind": "publisher", "old_id": "x"}, status=403)
    assert "data-cleanup-hint" not in _get(app, member, "/contactpoints")


def _belongs_to_options(html):
    """The options of the "Belongs to organization" picker for a contact point."""
    import re
    selects = re.findall(r'<select[^>]*(?:data-field|name)="actor_id"[^>]*>(.*?)</select>', html, re.S)
    assert selects, "no 'Belongs to organization' picker found"
    return [label.strip() for select in selects for label in re.findall(r"<option[^>]*>([^<]*)</option>", select)]


@_page_mark
@pytest.mark.parametrize("url", ["/dataset/new", "/contactpoints/new"])
def test_belongs_to_organization_offers_only_active_publishers(app, url):
    sysadmin = factories.SysadminWithToken()
    _actor("Active Board")
    _deactivate(_actor("Old Board"))
    options = _belongs_to_options(_get(app, sysadmin, url))
    assert "Active Board" in options and "Old Board" not in options
