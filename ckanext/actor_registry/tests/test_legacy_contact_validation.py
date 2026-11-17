"""A hidden old contact field whose stored value fails validation is shown again, with its
error, so the editor can correct it (0.6.0). None of the shipped or dcat schemas validate the
old email fields, so this uses a schema that does, as a catalogue's own schema may."""

import re

import pytest

from ckan.tests import factories, helpers

from ckanext.actor_registry import contact_migration as cm
from ckanext.actor_registry.tests.test_contact_migration import _set_column
from ckanext.actor_registry.tests.test_migration_close import OLD, _contact_point, _dataset, _get

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "dcat actor_registry scheming_datasets"),
    pytest.mark.ckan_config("ckanext.dcat.rdf.profiles", "actor_registry_euro_dcat_ap_3"),
    pytest.mark.ckan_config(
        "scheming.dataset_schemas", "ckanext.actor_registry.tests.fixtures:legacy_contact_validated_schema.yaml"),
    pytest.mark.ckan_config("scheming.presets", "ckanext.scheming:presets.json"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db", "restore_option"),
]


@pytest.mark.parametrize("state", ["closed", "open_linked"])
def test_a_hidden_old_value_that_fails_validation_is_shown_so_it_can_be_corrected(app, state):
    sysadmin = factories.SysadminWithToken()
    if state == "closed":
        dataset, org = _dataset(**OLD)
        cm.set_closed(sysadmin["name"], True, confirmed=True)
    else:
        dataset, org = _dataset(contact_point_ids=[_contact_point().id], **OLD)
    _set_column(dataset["id"], maintainer_email="n/a")  # an old import; CKAN rejects it today
    form = _get(app, sysadmin, f"/dataset/edit/{dataset['name']}")
    hidden = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)" data-legacy-contact-hidden>', form))
    assert hidden["maintainer_email"] == "n/a"
    data = dict(hidden, name=dataset["name"], title="Renamed", notes="Description.", owner_org=org["id"], save="")
    if state == "open_linked":
        data["contact_point_ids"] = dataset["contact_point_ids"]
    headers = {"Authorization": sysadmin["token"]}
    response = app.post(f"/dataset/edit/{dataset['name']}", headers=headers, data=data)
    body = response.get_data(as_text=True)
    # The save fails on the hidden value: the field is shown with its error, the others stay hidden.
    assert 'id="field-maintainer_email"' in body and 'value="n/a"' in body
    assert 'id="field-maintainer"' not in body
    assert helpers.call_action("package_show", id=dataset["id"])["title"] == "Bathing sites"
    # The editor clears it, and the save goes through; nothing else is lost.
    app.post(f"/dataset/edit/{dataset['name']}", headers=headers, data=dict(data, maintainer_email=""))
    stored = helpers.call_action("package_show", id=dataset["id"])
    assert stored["title"] == "Renamed" and not stored.get("maintainer_email")
    assert {key: stored[key] for key in ("maintainer", "author", "author_email")} == {
        key: OLD[key] for key in ("maintainer", "author", "author_email")}
