"""Migrate to Actor Registry, step 3: closing hides CKAN's own contact fields
(at runtime, no restart) and stops exporting them; reopening undoes it.
Nothing is ever deleted."""

import re
import uuid

import pytest

from ckan.tests import factories, helpers

from ckanext.actor_registry import contact_migration as cm
from ckanext.actor_registry import helpers as registry_helpers
from ckanext.actor_registry import model

OPTION = registry_helpers.LEGACY_CONTACT_FIELDS_OPTION

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "dcat actor_registry scheming_datasets"),
    pytest.mark.ckan_config("ckanext.dcat.rdf.profiles", "actor_registry_euro_dcat_ap_3"),
    pytest.mark.ckan_config(
        "scheming.dataset_schemas", "ckanext.actor_registry.tests.fixtures:legacy_contact_schema.yaml"),
    pytest.mark.ckan_config("scheming.presets", "ckanext.scheming:presets.json"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db", "restore_option"),
]

OLD = {"maintainer": "Desk", "maintainer_email": "desk@example.org",
       "author": "Ann", "author_email": "ann@example.org"}


@pytest.fixture
def restore_option():
    """config_option_update changes the running config, and CKAN keeps the
    first value it saw in a process-wide cache; reset both around each test."""
    from ckan.common import config
    from ckan.lib import app_globals

    def reset():
        app_globals._CONFIG_CACHE.pop(OPTION, None)
        config.pop(OPTION, None)

    reset()
    yield
    reset()


def _dataset(**fields):
    sysadmin = factories.Sysadmin()
    org = factories.Organization()
    return helpers.call_action("package_create", context={"user": sysadmin["name"]},
                               name=f"d-{uuid.uuid4().hex[:12]}", title="Bathing sites",
                               notes="Description.", owner_org=org["id"], **fields), org


def _contact_point():
    item = model.ContactPoint(id=str(uuid.uuid4()), name="Open Data Desk", email="desk@example.org",
                              uri=f"https://example.org/cp/{uuid.uuid4()}", active=True)
    from ckan import model as ckan_model
    ckan_model.Session.add(item)
    ckan_model.Session.commit()
    return item


def _get(app, user, url):
    return app.get(url, headers={"Authorization": user["token"]}).get_data(as_text=True)


def test_closing_needs_confirmation_while_work_remains():
    sysadmin = factories.Sysadmin()
    _dataset(**OLD)
    check = cm.close_check(sysadmin["name"])
    assert check["remaining"] == 1 and check["no_contact_point"] == 1 and check["needs_confirmation"]
    with pytest.raises(cm.MigrationError, match="Confirm"):
        cm.set_closed(sysadmin["name"], True)
    assert not cm.is_closed()
    cm.set_closed(sysadmin["name"], True, confirmed=True)
    assert cm.is_closed() and not registry_helpers.legacy_contact_fields_in_use()


def test_closing_without_work_left_needs_no_confirmation_and_can_be_reopened():
    sysadmin = factories.Sysadmin()
    _dataset(contact_point_ids=[_contact_point().id], **OLD)
    assert not cm.close_check(sysadmin["name"])["needs_confirmation"]
    cm.set_closed(sysadmin["name"], True)
    assert cm.is_closed()
    cm.set_closed(sysadmin["name"], False)
    assert not cm.is_closed()


def test_only_sysadmins_may_close_or_reopen(app):
    editor, member = factories.UserWithToken(), factories.UserWithToken()
    factories.Organization(users=[{"name": editor["name"], "capacity": "editor"},
                                  {"name": member["name"], "capacity": "member"}])
    for user in (editor, member):
        for url in ("/actor-registry/migrate/close", "/actor-registry/migrate/reopen"):
            app.post(url, headers={"Authorization": user["token"]}, data={"confirm": "1"}, status=403)
    assert not cm.is_closed()
    html = _get(app, editor, "/actor-registry/migrate")
    assert 'data-migration-status="open"' in html and "data-migration-close" not in html


def test_the_page_closes_and_reopens(app):
    sysadmin = factories.SysadminWithToken()
    _dataset(**OLD)
    headers = {"Authorization": sysadmin["token"]}
    html = _get(app, sysadmin, "/actor-registry/migrate")
    assert "data-close-warning" in html and "1 dataset will have no contact point" in html
    app.post("/actor-registry/migrate/close", headers=headers, data={})
    assert not cm.is_closed()
    html = app.post("/actor-registry/migrate/close", headers=headers, data={"confirm": "1"},
                    follow_redirects=True).get_data(as_text=True)
    assert cm.is_closed() and 'data-migration-status="closed"' in html
    app.post("/actor-registry/migrate/reopen", headers=headers, data={})
    assert not cm.is_closed()


def test_open_shows_the_old_fields_in_the_form_and_on_the_page(app):
    sysadmin = factories.SysadminWithToken()
    dataset, _ = _dataset(**OLD)
    form = _get(app, sysadmin, f"/dataset/edit/{dataset['name']}")
    assert 'id="field-maintainer"' in form and "data-legacy-contact-hidden" not in form
    page = _get(app, sysadmin, f"/dataset/{dataset['name']}")
    assert page.count("data-legacy-contact-row") == 4
    assert '<a href="mailto:desk@example.org">desk@example.org</a>' in page


def test_closed_hides_the_old_fields_everywhere_but_keeps_the_values(app):
    sysadmin = factories.SysadminWithToken()
    dataset, org = _dataset(**OLD)
    cm.set_closed(sysadmin["name"], True, confirmed=True)
    form = _get(app, sysadmin, f"/dataset/edit/{dataset['name']}")
    assert 'id="field-maintainer"' not in form
    hidden = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)" data-legacy-contact-hidden>', form))
    assert hidden == OLD
    page = _get(app, sysadmin, f"/dataset/{dataset['name']}")
    assert "data-legacy-contact-row" not in page and "desk@example.org" not in page

    # Saving the form, as a browser would send it, keeps the values.
    data = dict(hidden, name=dataset["name"], title="Renamed", notes="Description.",
                owner_org=org["id"], save="")
    app.post(f"/dataset/edit/{dataset['name']}", headers={"Authorization": sysadmin["token"]}, data=data)
    stored = helpers.call_action("package_show", id=dataset["id"])
    assert stored["title"] == "Renamed"
    assert {key: stored[key] for key in OLD} == OLD


def test_closing_stops_the_export_of_the_old_fields():
    sysadmin = factories.Sysadmin()
    dataset, _ = _dataset(**OLD)

    def exported():
        return helpers.call_action("dcat_dataset_show", context={"user": sysadmin["name"]},
                                   id=dataset["id"], format="ttl")

    assert "Desk" in exported()
    cm.set_closed(sysadmin["name"], True, confirmed=True)
    assert "Desk" not in exported() and "desk@example.org" not in exported()
    cm.set_closed(sysadmin["name"], False)
    assert "Desk" in exported()


@pytest.mark.parametrize("value, in_use", [
    (True, True), (False, False), (None, True), ("", False), ("True", True), ("False", False),
    ("true", True), ("no", False), (" 1 ", True), ("perhaps", False),
])
def test_every_form_the_setting_can_take(value, in_use, monkeypatch):
    from ckan.common import config
    monkeypatch.setitem(config, OPTION, value)
    assert registry_helpers.legacy_contact_fields_in_use() is in_use



# --- What visitors see is what is exported (CKAN's own contact fields) ----------------------


def _page_and_export(app, dataset):
    sysadmin = factories.Sysadmin()
    page = app.get(f"/dataset/{dataset['name']}").get_data(as_text=True)
    export = helpers.call_action("dcat_dataset_show", context={"user": sysadmin["name"]},
                                 id=dataset["id"], format="ttl")
    return page, export


def test_open_without_contact_points_the_maintainer_is_on_both(app):
    dataset, _ = _dataset(**OLD)
    page, export = _page_and_export(app, dataset)
    assert "data-legacy-contact-row" in page and "Desk" in export


def test_open_with_contact_points_the_old_fields_are_on_neither(app):
    dataset, _ = _dataset(contact_point_ids=[_contact_point().id], **OLD)
    page, export = _page_and_export(app, dataset)
    assert "data-legacy-contact-row" not in page
    assert "ann@example.org" not in page and "ann@example.org" not in export
    assert "Open Data Desk" in page and "Open Data Desk" in export


def test_closed_the_old_fields_are_on_neither(app):
    sysadmin = factories.Sysadmin()
    dataset, _ = _dataset(**OLD)
    cm.set_closed(sysadmin["name"], True, confirmed=True)
    page, export = _page_and_export(app, dataset)
    assert "data-legacy-contact-row" not in page
    assert "Desk" not in export and "ann@example.org" not in page


def _creators(export):
    from rdflib import Graph
    from rdflib.namespace import RDF
    from ckanext.dcat.profiles import DCAT, DCT, FOAF
    graph = Graph().parse(data=export, format="ttl")
    dataset_ref = next(graph.subjects(RDF.type, DCAT.Dataset))
    return [(str(next(graph.objects(node, FOAF.name), "")), str(next(graph.objects(node, FOAF.mbox), "")))
            for node in graph.objects(dataset_ref, DCT.creator)]


def test_open_without_contact_points_the_author_is_shown_and_exported_as_creator(app):
    dataset, _ = _dataset(**OLD)
    page, export = _page_and_export(app, dataset)
    assert "Ann" in page and "ann@example.org" in page
    assert _creators(export) == [("Ann", "mailto:ann@example.org")]


def test_an_author_with_an_invalid_email_is_exported_without_it(app):
    dataset, _ = _dataset(author="Ann")
    package_id = dataset["id"]
    from ckan import model as ckan_model
    from ckan.lib.search import rebuild
    ckan_model.Package.get(package_id).author_email = "n/a"
    ckan_model.Session.commit()
    rebuild(package_id)
    _page, export = _page_and_export(app, dataset)
    assert _creators(export) == [("Ann", "")]


@pytest.mark.parametrize("state", ["contact_points", "closed"])
def test_no_creator_when_the_author_is_not_shown(app, state):
    sysadmin = factories.Sysadmin()
    extra = {"contact_point_ids": [_contact_point().id]} if state == "contact_points" else {}
    dataset, _ = _dataset(**OLD, **extra)
    if state == "closed":
        cm.set_closed(sysadmin["name"], True, confirmed=True)
    page, export = _page_and_export(app, dataset)
    assert "ann@example.org" not in page and _creators(export) == []
