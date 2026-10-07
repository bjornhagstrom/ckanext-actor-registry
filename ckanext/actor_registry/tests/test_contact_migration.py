"""Migrate to Actor Registry, step 1 (contact points): the rules, every variant
of the free-text contact fields, faulty data, permissions and the page."""

import uuid

import pytest

from ckan import model as ckan_model
from ckan.plugins import toolkit
from ckan.tests import factories, helpers

from ckanext.actor_registry import contact_migration as cm
from ckanext.actor_registry import model


# --- The rules, without a database --------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    (None, ""), ("", ""), ("  a   b \t c ", "a b c"), ("\n", ""),
])
def test_clean_collapses_whitespace(raw, expected):
    assert cm.clean(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    (" Data@Example.ORG ", ("data@example.org", True)),
    ("n/a", ("n/a", False)),
    ("name@host", ("name@host", False)),
    ("two@example.org, three@example.org", ("two@example.org, three@example.org", False)),
    ("", ("", False)),
    (None, ("", False)),
])
def test_normalise_email(raw, expected):
    assert cm.normalise_email(raw) == expected


def _row(**fields):
    return dict({field: "" for field in cm.SOURCE_FIELDS}, **fields)


def test_maintainer_is_the_source():
    details = cm.contact_source(_row(maintainer="GIS Support", maintainer_email="GIS@example.org",
                                     author="Ann", author_email="ann@example.org"))
    assert details["source"] == "maintainer"
    assert (details["name"], details["email"]) == ("GIS Support", "gis@example.org")
    assert details["also"] == {"name": "Ann", "email": "ann@example.org"}


def test_author_is_the_source_only_without_a_maintainer():
    details = cm.contact_source(_row(author="Ann", author_email="ann@example.org"))
    assert details["source"] == "author" and details["also"] is None


def test_a_maintainer_email_alone_is_enough():
    details = cm.contact_source(_row(maintainer_email="desk@example.org", author="Ann"))
    assert details["source"] == "maintainer" and details["name"] == ""


def test_whitespace_only_maintainer_falls_back_to_the_author():
    details = cm.contact_source(_row(maintainer="  ", maintainer_email="\t", author="Ann"))
    assert details["source"] == "author"


def test_the_same_author_in_other_letter_case_is_not_also_mentioned():
    details = cm.contact_source(_row(maintainer="Open Data Desk", maintainer_email="desk@example.org",
                                     author="open data desk", author_email="DESK@example.org"))
    assert details["also"] is None


def test_no_contact_details_at_all():
    assert cm.contact_source(_row()) is None
    assert cm.contact_source(_row(maintainer=" ", author="\n")) is None


def test_an_invalid_email_is_kept_but_not_used():
    details = cm.contact_source(_row(maintainer="Desk", maintainer_email="n/a"))
    assert details["email"] == "" and not details["email_valid"] and details["raw_email"] == "n/a"


@pytest.mark.parametrize("fields, key", [
    ({"maintainer": "Desk", "maintainer_email": "Desk@Example.org"}, "email:desk@example.org"),
    ({"maintainer": "Open  Data DESK"}, "name:open data desk"),
    ({"maintainer": "Desk", "maintainer_email": "n/a"}, "name:desk"),
    ({"maintainer_email": "n/a"}, "name:n/a"),
])
def test_candidate_keys(fields, key):
    assert cm.candidate_key(cm.contact_source(_row(**fields))) == key


def test_fingerprint_follows_the_values_but_not_whitespace():
    base = cm.fingerprint(_row(maintainer="Desk"))
    assert cm.fingerprint(_row(maintainer="  Desk ")) == base
    assert cm.fingerprint(_row(maintainer="Desk", author="Ann")) != base


# --- With a database ----------------------------------------------------------------------

integration = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry scheming_datasets"),
    pytest.mark.ckan_config(
        "scheming.dataset_schemas", "ckanext.actor_registry.examples:actor_registry_schema.yaml"),
    pytest.mark.ckan_config("scheming.presets", "ckanext.scheming:presets.json"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db"),
]


def _mark(test):
    """Integration marks for tests that call the module directly (they need a
    request context for url_for)."""
    test = pytest.mark.usefixtures("with_request_context")(test)
    return _page_mark(test)


def _page_mark(test):
    """Integration marks for tests that go through the test client."""
    for mark in reversed(integration):
        test = mark(test)
    return test


def _org(users=()):
    return factories.Organization(users=[{"name": user["name"], "capacity": capacity}
                                         for user, capacity in users])


def _dataset(org, **fields):
    sysadmin = factories.Sysadmin()
    return helpers.call_action(
        "package_create", context={"user": sysadmin["name"]}, name=f"d-{uuid.uuid4().hex[:12]}",
        title=fields.pop("title", "Dataset"), notes="Description.", owner_org=org["id"], **fields)


def _contact_point(name="Open Data Desk", email="desk@example.org", active=True):
    item = model.ContactPoint(id=str(uuid.uuid4()), name=name, email=email,
                              uri=f"https://example.org/cp/{uuid.uuid4()}", active=active)
    ckan_model.Session.add(item)
    ckan_model.Session.commit()
    return item


def _set_column(dataset_id, **values):
    """Write faulty data straight into the database, as old imports may have."""
    package = ckan_model.Package.get(dataset_id)
    for key, value in values.items():
        if key == "contact_point_ids":
            package.extras = dict(package.extras, contact_point_ids=value)
        else:
            setattr(package, key, value)
    ckan_model.Session.commit()
    # package_show (and so package_patch) reads the search index copy.
    from ckan.lib.search import rebuild
    rebuild(dataset_id)


@_mark
def test_survey_groups_by_email_and_counts_name_variants():
    sysadmin = factories.Sysadmin()
    org = _org()
    for name, email in [("Open Data Desk", "desk@example.org"), ("Open Data Desk", "DESK@example.org "),
                        ("Opendata", "desk@example.org"), ("GIS Support", "gis@example.org")]:
        _dataset(org, maintainer=name, maintainer_email=email)
    data = cm.survey(sysadmin["name"])
    desk, gis = data["candidates"]
    assert desk["email"] == "desk@example.org" and len(desk["datasets"]) == 3
    assert desk["variants"] == [("Open Data Desk", 2), ("Opendata", 1)]
    assert desk["suggested_name"] == "Open Data Desk"
    assert gis["suggested_name"] == "GIS Support"
    assert data["counts"] == {"old": 4, "linked": 0, "skipped": 0, "remaining": 4, "no_contact": 0,
                              "changed": 0}


@_mark
def test_survey_groups_by_name_without_a_valid_email_and_reports_it():
    sysadmin = factories.Sysadmin()
    org = _org()
    # CKAN rejects such an address today, but older or imported data has them.
    _set_column(_dataset(org, maintainer="Desk")["id"], maintainer_email="n/a")
    _dataset(org, maintainer=" desk ")
    [candidate] = cm.survey(sysadmin["name"])["candidates"]
    assert candidate["key"] == "name:desk" and candidate["email"] == ""
    assert candidate["invalid_emails"] == ["n/a"]


@_mark
def test_survey_counts_linked_no_contact_and_ignores_deleted_datasets():
    sysadmin = factories.Sysadmin()
    org = _org()
    contact = _contact_point()
    _dataset(org, maintainer="Desk", contact_point_ids=[contact.id])
    _dataset(org)
    deleted = _dataset(org, maintainer="Gone")
    helpers.call_action("package_delete", context={"user": sysadmin["name"]}, id=deleted["id"])
    data = cm.survey(sysadmin["name"])
    assert data["candidates"] == []
    assert data["counts"] == {"old": 1, "linked": 1, "skipped": 0, "remaining": 0, "no_contact": 1,
                              "changed": 0}


@_mark
@pytest.mark.parametrize("stored", ["[not json", "[]", "", '["deleted-contact"]'])
def test_broken_or_empty_contact_point_values_count_as_not_linked(stored):
    sysadmin = factories.Sysadmin()
    dataset = _dataset(_org(), maintainer="Desk")
    _set_column(dataset["id"], contact_point_ids=stored)
    data = cm.survey(sysadmin["name"])
    if stored == '["deleted-contact"]':
        # A reference is a link, even to a deleted record; the worklist and the
        # dataset page deal with those.
        assert data["counts"]["linked"] == 1
    else:
        assert [c["key"] for c in data["candidates"]] == ["name:desk"]


@_mark
def test_editors_see_only_their_own_organizations_datasets():
    editor, member = factories.User(), factories.User()
    own = _org(users=[(editor, "editor"), (member, "member")])
    other = _org()
    _dataset(own, maintainer="Own Desk", maintainer_email="own@example.org", private=True)
    _dataset(other, maintainer="Other Desk", maintainer_email="other@example.org")
    assert [c["email"] for c in cm.survey(editor["name"])["candidates"]] == ["own@example.org"]
    assert not cm.can_migrate(member["name"])
    assert cm.survey(member["name"])["candidates"] == []
    assert not cm.can_migrate("")


@_mark
def test_create_links_the_datasets_and_never_changes_the_original_fields():
    sysadmin = factories.Sysadmin()
    org = _org()
    first = _dataset(org, maintainer="Desk", maintainer_email="desk@example.org", author="Ann")
    second = _dataset(org, maintainer="Opendata", maintainer_email="desk@example.org")
    linked, failures, contact = cm.apply(sysadmin["name"], "create", [first["id"], second["id"]],
                                         name=" Open  Data Desk ", email="Desk@Example.org")
    assert failures == [] and len(linked) == 2
    assert (contact.name, contact.email) == ("Open Data Desk", "desk@example.org")
    shown = helpers.call_action("package_show", id=first["id"])
    assert shown["contact_point_ids"] == [contact.id]
    assert (shown["maintainer"], shown["maintainer_email"], shown["author"]) == ("Desk", "desk@example.org", "Ann")
    decisions = ckan_model.Session.query(cm.MigrationDecision).all()
    assert {(d.package_id, d.status, d.contact_point_id) for d in decisions} == {
        (first["id"], "linked", contact.id), (second["id"], "linked", contact.id)}
    assert cm.survey(sysadmin["name"])["counts"]["linked"] == 2


@_mark
def test_a_whole_group_is_applied_by_key_except_the_datasets_left_out():
    sysadmin = factories.Sysadmin()
    org = _org()
    datasets = [_dataset(org, maintainer="Desk", maintainer_email="desk@example.org") for _ in range(3)]
    [candidate] = cm.survey(sysadmin["name"])["candidates"]
    linked, failures, contact = cm.apply(sysadmin["name"], "create", [], name="Open Data Desk", email="desk@example.org",
                                         group_key=candidate["key"], exclude_ids=[datasets[1]["id"]])
    assert failures == [] and {item["id"] for item in linked} == {datasets[0]["id"], datasets[2]["id"]}
    [candidate] = cm.survey(sysadmin["name"])["candidates"]
    assert [item["id"] for item in candidate["datasets"]] == [datasets[1]["id"]]


@_mark
def test_an_unknown_group_key_changes_nothing():
    sysadmin = factories.Sysadmin()
    _dataset(_org(), maintainer="Desk", maintainer_email="desk@example.org")
    with pytest.raises(cm.MigrationError):
        cm.apply(sysadmin["name"], "create", ["not-used"], name="Open Data Desk", email="desk@example.org",
                 group_key="email:nobody@example.org")
    assert cm.survey(sysadmin["name"])["counts"]["linked"] == 0


@_page_mark
def test_a_large_group_is_shown_compactly_and_applied_through_the_page(app, monkeypatch):
    from ckanext.actor_registry import views
    monkeypatch.setattr(views, "MIGRATION_LARGE_GROUP", 2)
    sysadmin = factories.SysadminWithToken()
    org = _org()
    datasets = [_dataset(org, title=f"Set {number}", maintainer="Desk", maintainer_email="desk@example.org")
                for number in range(4)]
    html = _get(app, sysadmin)
    # No per-dataset "include" field: only "leave out" boxes, and the group key.
    assert "data-large-group" in html and 'name="group_key" value="email:desk@example.org"' in html
    assert 'name="dataset_ids"' not in html and html.count('name="exclude_ids"') == 4
    response = app.post("/actor-registry/migrate/apply", headers={"Authorization": sysadmin["token"]},
                        data={"action": "create", "group_key": "email:desk@example.org", "name": "Open Data Desk",
                              "email": "desk@example.org", "exclude_ids": [datasets[3]["id"]], "page": "1"},
                        follow_redirects=True)
    assert 'data-count="linked">3<' in response.get_data(as_text=True)
    assert helpers.call_action("package_show", id=datasets[3]["id"]).get("contact_point_ids") in (None, [], "")


@_mark
def test_link_to_an_existing_contact_point_and_a_subset_stays_for_later():
    sysadmin = factories.Sysadmin()
    org = _org()
    contact = _contact_point()
    first = _dataset(org, maintainer="Desk", maintainer_email="desk@example.org")
    second = _dataset(org, maintainer="Desk", maintainer_email="desk@example.org")
    [candidate] = cm.survey(sysadmin["name"])["candidates"]
    assert [item.id for item in candidate["matches"]] == [contact.id]
    cm.apply(sysadmin["name"], "existing", [first["id"]], contact_point_id=contact.id)
    [candidate] = cm.survey(sysadmin["name"])["candidates"]
    assert [item["id"] for item in candidate["datasets"]] == [second["id"]]


@_mark
def test_one_email_can_become_two_contact_points():
    sysadmin = factories.Sysadmin()
    org = _org()
    maps = _dataset(org, maintainer="Map Services", maintainer_email="gis@example.org")
    gis = _dataset(org, maintainer="GIS Support", maintainer_email="gis@example.org")
    _, _, first = cm.apply(sysadmin["name"], "create", [maps["id"]], name="Map Services", email="gis@example.org")
    _, _, second = cm.apply(sysadmin["name"], "create", [gis["id"]], name="GIS Support", email="gis@example.org")
    assert first.id != second.id and first.email == second.email


@_mark
def test_skip_and_undo_and_a_changed_dataset_comes_back():
    sysadmin = factories.Sysadmin()
    org = _org()
    dataset = _dataset(org, maintainer="Ann Person", maintainer_email="ann@example.org")
    cm.apply(sysadmin["name"], "skip", [dataset["id"]])
    data = cm.survey(sysadmin["name"])
    assert data["candidates"] == [] and data["counts"]["skipped"] == 1
    assert cm.unskip(sysadmin["name"], dataset["id"])
    assert cm.survey(sysadmin["name"])["counts"]["remaining"] == 1
    assert not cm.unskip(sysadmin["name"], dataset["id"])

    cm.apply(sysadmin["name"], "skip", [dataset["id"]])
    helpers.call_action("package_patch", context={"user": sysadmin["name"]}, id=dataset["id"],
                        maintainer_email="ann.person@example.org")
    assert cm.survey(sysadmin["name"])["counts"]["remaining"] == 1


@_mark
@pytest.mark.parametrize("action, kwargs, message", [
    ("create", {"name": "", "email": "desk@example.org"}, "Name or role is required."),
    ("create", {"name": "Desk", "email": "n/a"}, "valid email"),
    ("existing", {"contact_point_id": "no-such-contact"}, "active contact point"),
    ("bogus", {}, "Choose what to do"),
])
def test_invalid_decisions_change_nothing(action, kwargs, message):
    sysadmin = factories.Sysadmin()
    dataset = _dataset(_org(), maintainer="Desk", maintainer_email="desk@example.org")
    with pytest.raises(cm.MigrationError, match=message):
        cm.apply(sysadmin["name"], action, [dataset["id"]], **kwargs)
    assert ckan_model.Session.query(model.ContactPoint).count() == 0
    assert ckan_model.Session.query(cm.MigrationDecision).count() == 0


@_mark
def test_an_inactive_contact_point_cannot_be_chosen():
    sysadmin = factories.Sysadmin()
    contact = _contact_point(active=False)
    dataset = _dataset(_org(), maintainer="Desk", maintainer_email="desk@example.org")
    with pytest.raises(cm.MigrationError):
        cm.apply(sysadmin["name"], "existing", [dataset["id"]], contact_point_id=contact.id)


@_mark
def test_datasets_outside_the_users_scope_are_ignored_even_if_posted():
    editor = factories.User()
    _org(users=[(editor, "editor")])
    foreign = _dataset(_org(), maintainer="Desk", maintainer_email="desk@example.org")
    with pytest.raises(cm.MigrationError, match="Select at least one dataset"):
        cm.apply(editor["name"], "skip", [foreign["id"], "not-a-dataset", ""])
    with pytest.raises(cm.MigrationError):
        cm.apply(editor["name"], "create", [], name="Desk")


@_mark
def test_a_dataset_that_fails_validation_is_reported_and_the_rest_are_linked():
    sysadmin = factories.Sysadmin()
    org = _org()
    good = _dataset(org, maintainer="Desk", maintainer_email="desk@example.org")
    bad = _dataset(org, title="Broken", maintainer="Desk", maintainer_email="desk@example.org")
    _set_column(bad["id"], notes="")  # the schema requires a description
    linked, failures, contact = cm.apply(sysadmin["name"], "create", [good["id"], bad["id"]], name="Desk")
    assert [item["id"] for item in linked] == [good["id"]]
    assert [title for title, _message in failures] == ["Broken"]
    assert contact is not None


@_mark
def test_a_new_contact_point_is_removed_when_no_dataset_could_be_linked():
    sysadmin = factories.Sysadmin()
    bad = _dataset(_org(), maintainer="Desk", maintainer_email="desk@example.org")
    _set_column(bad["id"], notes="")
    linked, failures, contact = cm.apply(sysadmin["name"], "create", [bad["id"]], name="Desk")
    assert linked == [] and len(failures) == 1 and contact is None
    assert ckan_model.Session.query(model.ContactPoint).count() == 0


@_mark
def test_without_a_contact_points_field_nothing_is_migratable(monkeypatch):
    monkeypatch.setattr(cm, "migratable_types", lambda: [])
    sysadmin = factories.Sysadmin()
    _dataset(_org(), maintainer="Desk")
    assert cm.survey(sysadmin["name"])["candidates"] == []


# --- The page -----------------------------------------------------------------------------


def _get(app, user, url="/actor-registry/migrate", status=200):
    headers = {"Authorization": user["token"]} if user else {}
    return app.get(url, headers=headers, status=status).get_data(as_text=True)


@_page_mark
def test_the_page_lists_candidates_and_the_overview(app):
    sysadmin = factories.SysadminWithToken()
    org = _org()
    _dataset(org, title="Bathing sites", maintainer="Desk", maintainer_email="desk@example.org",
             author="Ann", author_email="ann@example.org")
    html = _get(app, sysadmin)
    assert "Migrate to Actor Registry" in html
    assert 'data-candidate="email:desk@example.org"' in html
    assert "Bathing sites" in html and "data-also-mentioned" in html
    assert 'data-count="remaining"><strong>1</strong>' in html


@_page_mark
def test_access_to_the_page(app):
    editor, member = factories.UserWithToken(), factories.UserWithToken()
    _org(users=[(editor, "editor"), (member, "member")])
    _get(app, editor)
    _get(app, member, status=403)
    _get(app, None, status=403)
    assert "/actor-registry/migrate" in _get(app, editor, url="/contactpoints")
    assert "/actor-registry/migrate" not in _get(app, member, url="/contactpoints")


@_page_mark
def test_posting_a_decision_through_the_page(app):
    sysadmin = factories.SysadminWithToken()
    dataset = _dataset(_org(), maintainer="Desk", maintainer_email="desk@example.org")
    response = app.post("/actor-registry/migrate/apply", headers={"Authorization": sysadmin["token"]},
                        data={"action": "create", "dataset_ids": [dataset["id"]], "name": "Open Data Desk",
                              "email": "desk@example.org", "page": "1"}, follow_redirects=True)
    html = response.get_data(as_text=True)
    # Flash messages are not kept between requests authenticated by API token,
    # so check the outcome instead.
    assert 'data-count="linked">1<' in html
    assert helpers.call_action("package_show", id=dataset["id"])["contact_point_ids"]
    assert "Nothing remains to migrate." in html


@_page_mark
def test_a_forbidden_post_is_refused(app):
    member = factories.UserWithToken()
    _org(users=[(member, "member")])
    app.post("/actor-registry/migrate/apply", headers={"Authorization": member["token"]},
             data={"action": "skip"}, status=403)
    app.post("/actor-registry/migrate/unskip", headers={"Authorization": member["token"]},
             data={"dataset_id": "x"}, status=403)


# --- Step 2: changes in the source after linking -------------------------------------------


def _linked(org=None, **fields):
    """A dataset linked through the migration, and its contact point."""
    sysadmin = factories.Sysadmin()
    fields = fields or {"maintainer": "Desk", "maintainer_email": "desk@example.org"}
    dataset = _dataset(org or _org(), **fields)
    _, _, contact = cm.apply(sysadmin["name"], "create", [dataset["id"]],
                             name=fields.get("maintainer") or "Desk", email=fields.get("maintainer_email", ""))
    return sysadmin, dataset, contact


def _change(sysadmin, dataset, **fields):
    helpers.call_action("package_patch", context={"user": sysadmin["name"]}, id=dataset["id"], **fields)


@_mark
def test_a_change_after_linking_is_flagged_with_before_and_after():
    sysadmin, dataset, contact = _linked()
    assert cm.survey(sysadmin["name"])["changed"] == []
    _change(sysadmin, dataset, maintainer_email="opendata@example.org")
    data = cm.survey(sysadmin["name"])
    [item] = data["changed"]
    assert data["counts"]["changed"] == 1
    assert item["previous"]["maintainer_email"] == "desk@example.org"
    assert item["values"]["maintainer_email"] == "opendata@example.org"
    assert item["contact_point"].id == contact.id and item["contact_point_in_dataset"]
    assert item["usage"] == 1


@_mark
def test_a_whitespace_only_change_is_not_flagged():
    sysadmin, dataset, _ = _linked()
    _set_column(dataset["id"], maintainer="  Desk  ")
    assert cm.survey(sysadmin["name"])["changed"] == []


@_mark
def test_datasets_linked_by_hand_are_never_flagged():
    sysadmin = factories.Sysadmin()
    contact = _contact_point()
    dataset = _dataset(_org(), maintainer="Desk", contact_point_ids=[contact.id])
    _change(sysadmin, dataset, maintainer="Someone else")
    assert cm.survey(sysadmin["name"])["changed"] == []


@_mark
def test_keep_clears_the_flag_until_the_next_change():
    sysadmin, dataset, contact = _linked()
    _change(sysadmin, dataset, maintainer="Open Data Desk")
    assert cm.resolve_change(sysadmin["name"], dataset["id"], "keep") is None
    assert cm.survey(sysadmin["name"])["changed"] == []
    assert registry_contact(contact.id).name == "Desk"
    _change(sysadmin, dataset, maintainer="Data Desk")
    assert len(cm.survey(sysadmin["name"])["changed"]) == 1


def registry_contact(contact_id):
    ckan_model.Session.expire_all()
    return model.get_contact_point(contact_id)


@_mark
def test_update_changes_the_contact_point_for_every_dataset_using_it():
    sysadmin = factories.Sysadmin()
    org = _org()
    first = _dataset(org, maintainer="Desk", maintainer_email="desk@example.org")
    second = _dataset(org, maintainer="Desk", maintainer_email="desk@example.org")
    _, _, contact = cm.apply(sysadmin["name"], "create", [first["id"], second["id"]], name="Desk",
                             email="desk@example.org")
    _change(sysadmin, first, maintainer="Open Data Desk", maintainer_email="opendata@example.org")
    [item] = cm.survey(sysadmin["name"])["changed"]
    assert item["usage"] == 2
    cm.resolve_change(sysadmin["name"], first["id"], "update", name="Open Data Desk", email="OpenData@example.org")
    updated = registry_contact(contact.id)
    assert (updated.name, updated.email) == ("Open Data Desk", "opendata@example.org")
    assert helpers.call_action("package_show", id=second["id"])["contact_point_ids"] == [contact.id]
    assert cm.survey(sysadmin["name"])["changed"] == []


@_mark
@pytest.mark.parametrize("name, email, message", [
    ("", "desk@example.org", "Name or role is required."),
    ("Desk", "n/a", "valid email"),
])
def test_an_invalid_update_changes_nothing(name, email, message):
    sysadmin, dataset, contact = _linked()
    _change(sysadmin, dataset, maintainer="Open Data Desk")
    with pytest.raises(cm.MigrationError, match=message):
        cm.resolve_change(sysadmin["name"], dataset["id"], "update", name=name, email=email)
    assert registry_contact(contact.id).name == "Desk"
    assert len(cm.survey(sysadmin["name"])["changed"]) == 1


@_mark
def test_link_another_contact_point_replaces_only_the_migrated_one():
    sysadmin, dataset, contact = _linked()
    extra = _contact_point(name="Statistics", email="stats@example.org")
    _change(sysadmin, dataset, contact_point_ids=[contact.id, extra.id])
    target = _contact_point(name="GIS Support", email="gis@example.org")
    _change(sysadmin, dataset, maintainer="GIS Support", maintainer_email="gis@example.org")
    cm.resolve_change(sysadmin["name"], dataset["id"], "existing", contact_point_id=target.id)
    assert helpers.call_action("package_show", id=dataset["id"])["contact_point_ids"] == [target.id, extra.id]
    assert registry_contact(contact.id).name == "Desk"
    assert cm.survey(sysadmin["name"])["changed"] == []


@_mark
def test_create_a_new_contact_point_from_the_new_details():
    sysadmin, dataset, contact = _linked()
    _change(sysadmin, dataset, maintainer="GIS Support", maintainer_email="gis@example.org")
    new = cm.resolve_change(sysadmin["name"], dataset["id"], "create", name="GIS Support", email="gis@example.org")
    assert new.id != contact.id
    assert helpers.call_action("package_show", id=dataset["id"])["contact_point_ids"] == [new.id]


@_mark
def test_when_the_migrated_contact_point_was_removed_by_hand_update_is_refused():
    sysadmin, dataset, contact = _linked()
    other = _contact_point(name="Other", email="other@example.org")
    _change(sysadmin, dataset, contact_point_ids=[other.id], maintainer="Changed")
    [item] = cm.survey(sysadmin["name"])["changed"]
    assert not item["contact_point_in_dataset"]
    with pytest.raises(cm.MigrationError, match="no longer in use"):
        cm.resolve_change(sysadmin["name"], dataset["id"], "update", name="Changed")
    target = _contact_point(name="Target", email="target@example.org")
    cm.resolve_change(sysadmin["name"], dataset["id"], "existing", contact_point_id=target.id)
    assert helpers.call_action("package_show", id=dataset["id"])["contact_point_ids"] == [other.id, target.id]


@_mark
def test_an_inactive_contact_point_cannot_be_updated_but_can_be_replaced():
    sysadmin, dataset, contact = _linked()
    registry_contact(contact.id).active = False
    ckan_model.Session.commit()
    # The schema rejects a dataset that lists an inactive contact point, so
    # the change can only have come in some other way (an import, the database).
    _set_column(dataset["id"], maintainer="Changed")
    with pytest.raises(cm.MigrationError):
        cm.resolve_change(sysadmin["name"], dataset["id"], "update", name="Changed")
    target = _contact_point(name="Target", email="target@example.org")
    cm.resolve_change(sysadmin["name"], dataset["id"], "existing", contact_point_id=target.id)
    assert helpers.call_action("package_show", id=dataset["id"])["contact_point_ids"] == [target.id]


@_mark
@pytest.mark.parametrize("action, kwargs", [
    ("bogus", {}), ("existing", {"contact_point_id": ""}), ("existing", {"contact_point_id": "missing"}),
    ("create", {"name": ""}),
])
def test_invalid_change_decisions_change_nothing(action, kwargs):
    sysadmin, dataset, contact = _linked()
    _change(sysadmin, dataset, maintainer="Changed")
    count = ckan_model.Session.query(model.ContactPoint).count()
    with pytest.raises(cm.MigrationError):
        cm.resolve_change(sysadmin["name"], dataset["id"], action, **kwargs)
    assert ckan_model.Session.query(model.ContactPoint).count() == count
    assert helpers.call_action("package_show", id=dataset["id"])["contact_point_ids"] == [contact.id]


@_mark
def test_a_dataset_that_is_not_changed_or_not_editable_is_refused():
    sysadmin, dataset, _ = _linked()
    with pytest.raises(cm.MigrationError, match="no longer among the changed"):
        cm.resolve_change(sysadmin["name"], dataset["id"], "keep")
    _change(sysadmin, dataset, maintainer="Changed")
    editor = factories.User()
    _org(users=[(editor, "editor")])
    with pytest.raises(cm.MigrationError, match="no longer among the changed"):
        cm.resolve_change(editor["name"], dataset["id"], "keep")


@_mark
def test_decisions_without_stored_values_still_show_the_change():
    sysadmin, dataset, _ = _linked()
    ckan_model.Session.query(cm.MigrationDecision).update({"source_values": None})
    ckan_model.Session.commit()
    _change(sysadmin, dataset, maintainer="Changed")
    [item] = cm.survey(sysadmin["name"])["changed"]
    assert item["previous"] is None


@_mark
def test_usage_counting_survives_broken_stored_values():
    sysadmin, dataset, contact = _linked()
    broken = _dataset(_org(), maintainer="X")
    _set_column(broken["id"], contact_point_ids="[not json")
    assert cm.contact_point_usage()[contact.id] == 1


@_page_mark
def test_the_page_shows_and_resolves_a_change(app):
    sysadmin = factories.SysadminWithToken()
    org = _org()
    dataset = _dataset(org, title="Bathing sites", maintainer="Desk", maintainer_email="desk@example.org")
    headers = {"Authorization": sysadmin["token"]}
    app.post("/actor-registry/migrate/apply", headers=headers,
             data={"action": "create", "dataset_ids": [dataset["id"]], "name": "Desk", "email": "desk@example.org"})
    helpers.call_action("package_patch", context={"user": sysadmin["name"]}, id=dataset["id"], maintainer="Open Data Desk")
    html = _get(app, sysadmin)
    assert f'data-changed-dataset="{dataset["id"]}"' in html
    assert 'data-changed-field="maintainer"' in html and "<del>Desk</del>" in html
    assert 'data-changed-field="maintainer_email"' not in html
    html = app.post("/actor-registry/migrate/change", headers=headers, follow_redirects=True,
                    data={"dataset_id": dataset["id"], "action": "keep"}).get_data(as_text=True)
    assert "data-migration-changed" not in html


# --- Broken stored values must not break the registry's own queries --------------------------


@_page_mark
@pytest.mark.parametrize("url", ["/actors", "/actors/unlinked-datasets?missing=contact_point",
                                 "/actors/unlinked-datasets?missing=either", "/actor-registry/migrate"])
def test_registry_pages_survive_a_broken_stored_value(app, url):
    sysadmin = factories.SysadminWithToken()
    dataset = _dataset(_org(), maintainer="X")
    _set_column(dataset["id"], contact_point_ids="[not json")
    _get(app, sysadmin, url=url)


@_page_mark
@pytest.mark.parametrize("stored, linked", [
    ("[not json", False), ("", False), ("[]", False), ("  ", False),
    ('["{id}"]', True), ('[ "{id}" , "other" ]', True), ("{id}", True),
])
def test_stored_contact_point_values_are_read_like_the_python_code(stored, linked):
    contact = _contact_point()
    dataset = _dataset(_org(), maintainer="X")
    _set_column(dataset["id"], contact_point_ids=stored.replace("{id}", contact.id))
    assert (dataset["id"] in model.datasets_for_contact_point(contact.id)) is linked
    assert (dataset["id"] in model.datasets_without_actor_link()) is (not linked)
    rows, _total = model.linked_datasets("contact_point", [contact.id], is_sysadmin=True)
    assert (dataset["id"] in [row["id"] for row in rows]) is linked


# --- Feedback for an inactive or missing contact point on a dataset -------------------------


def _deactivate(contact):
    registry_contact(contact.id).active = False
    ckan_model.Session.commit()


@_mark
def test_a_deactivated_contact_point_does_not_lock_the_dataset():
    sysadmin = factories.Sysadmin()
    contact = _contact_point()
    dataset = _dataset(_org(), contact_point_ids=[contact.id])
    _deactivate(contact)
    patched = helpers.call_action("package_patch", context={"user": sysadmin["name"]},
                                  id=dataset["id"], title="Renamed")
    assert patched["contact_point_ids"] == [contact.id]


@_mark
def test_choosing_an_inactive_contact_point_anew_names_it():
    sysadmin = factories.Sysadmin()
    contact = _contact_point(name="Old Desk")
    _deactivate(contact)
    dataset = _dataset(_org())
    with pytest.raises(toolkit.ValidationError) as caught:
        helpers.call_action("package_patch", context={"user": sysadmin["name"]},
                            id=dataset["id"], contact_point_ids=[contact.id])
    [message] = caught.value.error_dict["contact_point_ids"]
    assert message == ("The contact point “Old Desk” is inactive and can no longer be chosen. "
                       "Choose an active contact point.")


@_mark
def test_a_contact_point_that_no_longer_exists_is_explained():
    sysadmin = factories.Sysadmin()
    dataset = _dataset(_org())
    with pytest.raises(toolkit.ValidationError) as caught:
        helpers.call_action("package_patch", context={"user": sysadmin["name"]},
                            id=dataset["id"], contact_point_ids=["gone-123"])
    messages = caught.value.error_dict["contact_point_ids"]
    assert "A selected contact point no longer exists (id gone-123). Remove it from the list." in messages


@_page_mark
def test_the_form_shows_an_inactive_contact_point_instead_of_dropping_it(app):
    sysadmin = factories.SysadminWithToken()
    contact = _contact_point(name="Old Desk")
    dataset = _dataset(_org(), contact_point_ids=[contact.id])
    _deactivate(contact)
    html = _get(app, sysadmin, url=f"/dataset/edit/{dataset['name']}")
    assert f'<option value="{contact.id}" selected data-unavailable="inactive">Old Desk (inactive)</option>' in html
    assert 'data-contactpoint-unavailable="inactive"' in html
    assert "“Old Desk” is inactive. It stays on this dataset" in html


@_page_mark
def test_the_form_shows_a_missing_contact_point(app):
    sysadmin = factories.SysadminWithToken()
    dataset = _dataset(_org())
    _set_column(dataset["id"], contact_point_ids='["gone-123"]')
    html = _get(app, sysadmin, url=f"/dataset/edit/{dataset['name']}")
    assert 'data-unavailable="missing">Unknown contact point (gone-123)</option>' in html
    assert "Remove it from the list before you save." in html


@_page_mark
def test_saving_the_form_with_a_missing_contact_point_gives_the_message(app):
    sysadmin = factories.SysadminWithToken()
    org = _org()
    dataset = _dataset(org)
    html = app.post(f"/dataset/edit/{dataset['name']}", headers={"Authorization": sysadmin["token"]},
                    data={"name": dataset["name"], "title": "Dataset", "notes": "Description.",
                          "owner_org": org["id"], "contact_point_ids": ["gone-123"], "save": ""},
                    ).get_data(as_text=True)
    assert "A selected contact point no longer exists (id gone-123). Remove it from the list." in html
