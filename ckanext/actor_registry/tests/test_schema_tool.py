"""ckan actor-registry schema: a copy of a schema (such as ckanext-dcat's
dcat_ap_full, or Scheming's ckan_dataset for a catalogue without ckanext-dcat)
with the registry's contact points and the free-text contact fields kept as
legacy fields, and that the copy works end to end: form field, page and export."""

import json
import os
import re
import tempfile
import uuid

import pytest
import yaml
from click.testing import CliRunner

from ckan import model as ckan_model
from ckan.tests import factories, helpers

from ckanext.actor_registry import cli, model, schema_tool

DCAT_FULL = "ckanext.dcat.schemas:dcat_ap_full.yaml"
CKAN_DATASET = "ckanext.scheming:ckan_dataset.yaml"


def _schema(*names):
    return {"scheming_version": 2, "dataset_type": "dataset",
            "dataset_fields": [{"field_name": name, "label": name} for name in names]}


def _names(schema):
    return [field["field_name"] for field in schema["dataset_fields"]]


def test_the_registry_field_takes_the_place_of_the_dcat_field_which_is_kept_as_legacy():
    source = _schema("title", "contact", "publisher")
    source["dataset_fields"][1].update(repeating_subfields=[{"field_name": "name"}], repeating_label="Contact point")
    schema, note = schema_tool.with_registry_contact_points(source)
    assert _names(schema) == ["title", "contact_point_ids", "contact", "publisher"]
    field, legacy = schema["dataset_fields"][1:3]
    assert field["form_snippet"] == "contactpoints_multiple_select.html"
    assert "actor_registry_contactpoints_exist" in field["validators"]
    assert legacy["form_snippet"] == legacy["display_snippet"] == "legacy_dcat_contact.html"
    assert legacy["label"]["sv"] == "Kontaktpunkter (fritext)" and "repeating_label" not in legacy
    assert legacy["repeating_subfields"] == [{"field_name": "name"}]
    assert note == "added the field contact_point_ids; kept as legacy fields: contact"
    assert _names(source) == ["title", "contact", "publisher"]  # the source is not changed


def test_without_a_dcat_contact_field_it_goes_after_ckans_contact_fields_or_last():
    schema, note = schema_tool.with_registry_contact_points(_schema("title", "maintainer", "maintainer_email", "notes"))
    assert _names(schema) == ["title", "maintainer", "maintainer_email", "contact_point_ids", "notes"]
    assert note == "added the field contact_point_ids; kept as legacy fields: maintainer, maintainer_email"
    schema, note = schema_tool.with_registry_contact_points(_schema("title", "notes"))
    assert _names(schema)[-1] == "contact_point_ids"
    assert note == "added the field contact_point_ids"


def test_ckans_own_contact_fields_become_legacy_fields_with_their_labels():
    source = _schema("title", "author", "author_email", "maintainer", "maintainer_email", "version")
    source["dataset_fields"][2].update(display_snippet="email.html", display_email_name_field="author",
                                       form_placeholder="joe@example.com")
    source["dataset_fields"][3]["required"] = True  # a hidden field cannot be required
    schema, _ = schema_tool.with_registry_contact_points(source)
    by_name = {field["field_name"]: field for field in schema["dataset_fields"]}
    for name in schema_tool.CKAN_CONTACT_FIELDS:
        assert by_name[name]["form_snippet"] == by_name[name]["display_snippet"] == "legacy_contact.html"
        assert by_name[name]["label"] == name
    assert "display_email_name_field" not in by_name["author_email"]
    assert by_name["author_email"]["form_placeholder"] == "joe@example.com"
    assert "form_snippet" not in by_name["version"]
    assert "required" not in by_name["maintainer"]


def test_with_both_dcats_and_ckans_fields_the_registry_field_goes_before_dcats():
    schema, note = schema_tool.with_registry_contact_points(_schema("title", "maintainer", "contact", "author"))
    assert _names(schema) == ["title", "maintainer", "contact_point_ids", "contact", "author"]
    assert note == "added the field contact_point_ids; kept as legacy fields: contact, maintainer, author"


def test_a_file_url_is_read_as_scheming_reads_it(tmp_path):
    path = tmp_path / "my schema.yaml"
    path.write_text(yaml.safe_dump(_schema("title")))
    assert _names(schema_tool.read_schema("file://" + str(path).replace(" ", "%20"))) == ["title"]


def test_schemings_ckan_dataset_schema_keeps_every_other_field():
    source = schema_tool.read_schema(CKAN_DATASET)
    schema, note = schema_tool.with_registry_contact_points(source)
    names = _names(schema)
    assert [n for n in names if n != "contact_point_ids"] == _names(source)
    assert names.index("contact_point_ids") == names.index("maintainer_email") + 1
    assert {"tag_string", "license_id", "version", "url"} <= set(names)
    assert note.endswith("author, author_email, maintainer, maintainer_email")


def test_a_schema_that_already_has_the_field_is_refused():
    with pytest.raises(schema_tool.SchemaToolError, match="already has"):
        schema_tool.with_registry_contact_points(_schema("title", "contact_point_ids"))


@pytest.mark.parametrize("source, message", [
    ("ckanext.no_such_module:schema.yaml", "No module"),
    ("nosuch_package.schemas:schema.yaml", "No module"),
    ("ckanext.actor_registry.examples:missing.yaml", "Could not read"),
    ("ckanext.actor_registry:config_declaration.yaml", "not a Scheming dataset schema"),
])
def test_unreadable_sources_give_a_message(source, message):
    with pytest.raises(schema_tool.SchemaToolError, match=message):
        schema_tool.read_schema(source)


def test_the_real_dcat_schema_is_converted_and_reads_back():
    pytest.importorskip("ckanext.dcat")
    text, note = schema_tool.convert(DCAT_FULL)
    assert text.startswith("# Made by ckanext-actor-registry")
    schema = yaml.safe_load(text)
    names = _names(schema)
    assert names.index("contact_point_ids") == _names(schema_tool.read_schema(DCAT_FULL)).index("contact")
    assert names.index("contact") == names.index("contact_point_ids") + 1
    assert schema["resource_fields"] == schema_tool.read_schema(DCAT_FULL)["resource_fields"]
    assert note.startswith("added the field contact_point_ids")


def test_credentials_in_a_source_url_are_not_written_to_the_copy():
    text = schema_tool.render(_schema("title"), "https://user:secret@example.org/schema.yaml")
    assert "secret" not in text and "https://***@example.org/schema.yaml" in text


@pytest.mark.parametrize("source", [
    "http://user:secret@127.0.0.1:9/schema.yaml",
    "ftp://user:secret@example.invalid/schema.yaml",
    "file://user:secret@localhost/schema.yaml",
    "https://user:secret@example.invalid/schema.yaml",  # no port: urllib's InvalidURL would quote "secret@example.invalid"
])
def test_credentials_in_a_source_url_are_refused_without_being_quoted(source):
    with pytest.raises(schema_tool.SchemaToolError) as error:
        schema_tool.read_schema(source)
    assert "secret" not in str(error.value) and "***@" in str(error.value) and "not supported" in str(error.value)


def test_the_command_writes_a_file_and_reports_errors(tmp_path):
    runner = CliRunner()
    out = tmp_path / "schema.yaml"
    result = runner.invoke(cli.actor_registry, ["schema", "ckanext.actor_registry.examples:contact_points_only_schema.yaml"])
    assert result.exit_code == 1 and "already has the field contact_point_ids" in result.output
    pytest.importorskip("ckanext.dcat")
    result = runner.invoke(cli.actor_registry, ["schema", DCAT_FULL, "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "contact_point_ids" in _names(yaml.safe_load(out.read_text()))


def test_an_output_in_a_missing_directory_is_a_message(tmp_path, capsys):
    target = str(tmp_path / "missing" / "schema.yaml")
    assert schema_tool.main([CKAN_DATASET, "-o", target]) == 1
    assert "Could not write" in capsys.readouterr().err
    result = CliRunner().invoke(cli.actor_registry, ["schema", CKAN_DATASET, "-o", target])
    assert result.exit_code != 0 and "Could not write" in result.output


def test_python_m_needs_no_ckan_configuration(tmp_path, capsys):
    pytest.importorskip("ckanext.dcat")
    assert schema_tool.main([DCAT_FULL]) == 0
    assert "contact_point_ids" in capsys.readouterr().out
    assert schema_tool.main(["ckanext.actor_registry.examples:missing.yaml"]) == 1


# --- The converted dcat_ap_full in a running CKAN: form, page and export --------------------

def _converted_dcat_schema():
    try:
        text, _ = schema_tool.convert(DCAT_FULL)
    except schema_tool.SchemaToolError:  # ckanext-dcat not installed: the tests below are skipped
        return "file:///nonexistent.yaml"
    path = os.path.join(tempfile.gettempdir(), "actor_registry_dcat_ap_full_test.yaml")
    with open(path, "w", encoding="utf-8") as out:
        out.write(text)
    return "file://" + path


integration = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "dcat actor_registry scheming_datasets"),
    pytest.mark.ckan_config("scheming.dataset_schemas", _converted_dcat_schema()),
    pytest.mark.ckan_config("scheming.presets", "ckanext.scheming:presets.json ckanext.dcat.schemas:presets.yaml"),
    pytest.mark.ckan_config("ckanext.dcat.rdf.profiles", "actor_registry_euro_dcat_ap_3"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db", "restore_option"),
]


def _integration(test):
    for mark in reversed(integration):
        test = mark(test)
    return test


def _contact(name, email):
    item = model.ContactPoint(id=str(uuid.uuid4()), name=name, email=email,
                              uri=f"https://example.org/cp/{uuid.uuid4()}", active=True)
    ckan_model.Session.add(item)
    ckan_model.Session.commit()
    return item


def _dataset(**fields):
    sysadmin = factories.SysadminWithToken()
    org = factories.Organization()
    return sysadmin, helpers.call_action(
        "package_create", context={"user": sysadmin["name"]}, name=f"d-{uuid.uuid4().hex[:10]}",
        title="Bathing sites", notes="Water samples.", owner_org=org["id"], **fields)


OLD = [{"name": "Old Desk", "email": "old@example.org", "uri": "", "url": ""}]


def _edit_form(app, sysadmin, dataset):
    return app.get(f"/dataset/edit/{dataset['name']}", headers={"Authorization": sysadmin["token"]}).get_data(as_text=True)


def _save_form(app, sysadmin, dataset, **fields):
    """Save the dataset as a browser would: only what the form sends."""
    data = dict(name=dataset["name"], title=dataset["title"], notes=dataset["notes"],
                owner_org=dataset["owner_org"], save="", **fields)
    app.post(f"/dataset/edit/{dataset['name']}", headers={"Authorization": sysadmin["token"]}, data=data)
    ckan_model.Session.expire_all()
    return ckan_model.Package.get(dataset["id"])


def _page_and_export(app, dataset):
    return (app.get(f"/dataset/{dataset['name']}").get_data(as_text=True),
            helpers.call_action("dcat_dataset_show", id=dataset["id"], format="ttl"))


@_integration
def test_while_open_the_old_field_is_edited_shown_and_exported_until_a_contact_point_is_chosen(app):
    pytest.importorskip("ckanext.dcat")
    sysadmin, dataset = _dataset(contact=OLD)
    form = _edit_form(app, sysadmin, dataset)
    assert 'name="contact_point_ids"' in form and 'name="contact-0-name"' in form
    page, export = _page_and_export(app, dataset)
    assert "old@example.org" in page and "old@example.org" in export

    desk = _contact("Open Data Desk", "desk@example.org")
    stored = _save_form(app, sysadmin, dataset, contact_point_ids=desk.id,
                        **{"contact-0-name": "Old Desk", "contact-0-email": "old@example.org"})
    assert json.loads(stored.extras["contact"])[0]["email"] == "old@example.org"  # kept
    page, export = _page_and_export(app, dataset)
    assert "desk@example.org" in page and "desk@example.org" in export
    assert "old@example.org" not in page and "old@example.org" not in export
    # 0.6.0: with a contact point the form hides the old field too, as the page does, and keeps its value.
    form = _edit_form(app, sysadmin, dataset)
    assert 'id="field-contact-0-name"' not in form
    hidden = dict(re.findall(r'<input type="hidden" name="(contact-[\w-]+)" value="([^"]*)" data-legacy-contact-hidden>', form))
    assert hidden["contact-0-email"] == "old@example.org"
    stored = _save_form(app, sysadmin, dataset, contact_point_ids=desk.id, **hidden)
    assert json.loads(stored.extras["contact"])[0]["email"] == "old@example.org"


TWO_OLD = OLD + [{"name": "GIS Support", "email": "gis@example.org", "uri": "https://example.org/gis", "url": ""}]


@_integration
def test_once_closed_the_old_field_is_hidden_but_a_form_save_keeps_it(app):
    pytest.importorskip("ckanext.dcat")
    from ckanext.actor_registry import contact_migration as cm
    sysadmin, dataset = _dataset(contact=TWO_OLD)
    cm.set_closed(sysadmin["name"], True, confirmed=True)
    form = _edit_form(app, sysadmin, dataset)
    assert 'id="field-contact-0-name"' not in form  # no visible field, only hidden inputs
    hidden = dict(re.findall(r'<input type="hidden" name="(contact-[\w-]+)" value="([^"]*)" data-legacy-contact-hidden>', form))
    assert hidden["contact-0-email"] == "old@example.org" and hidden["contact-0-name"] == "Old Desk"
    page, export = _page_and_export(app, dataset)
    assert "old@example.org" not in page and "old@example.org" not in export

    assert hidden["contact-1-email"] == "gis@example.org" and hidden["contact-1-uri"] == "https://example.org/gis"

    stored = _save_form(app, sysadmin, dataset, **hidden)
    kept = json.loads(stored.extras["contact"])
    assert [item["email"] for item in kept] == ["old@example.org", "gis@example.org"]
    assert kept[1]["uri"] == "https://example.org/gis"

    # A save that fails validation shows the form again, still carrying the old values.
    response = app.post(f"/dataset/edit/{dataset['name']}", headers={"Authorization": sysadmin["token"]},
                        data=dict(hidden, name="Not a valid URL name!", title=dataset["title"], notes=dataset["notes"],
                                  owner_org=dataset["owner_org"], save=""))
    body = response.get_data(as_text=True)
    assert 'id="field-name"' in body and "error" in body  # the form again, with the error
    again = dict(re.findall(r'<input type="hidden" name="(contact-[\w-]+)" value="([^"]*)" data-legacy-contact-hidden>', body))
    assert again["contact-1-email"] == "gis@example.org" and again["contact-0-name"] == "Old Desk"


@_integration
def test_without_the_field_in_the_schema_a_stored_value_is_not_exported(app, monkeypatch):
    # The profile's own branch; the page side is CKAN's (it never shows a field the schema lacks).
    pytest.importorskip("ckanext.dcat")
    from ckanext.actor_registry import profiles
    _, dataset = _dataset(contact=OLD)
    real = profiles._schema_fields
    monkeypatch.setattr(profiles, "_schema_fields",
                        lambda d: {k: v for k, v in (real(d) or {}).items() if k != "contact"})
    export = helpers.call_action("dcat_dataset_show", id=dataset["id"], format="ttl")
    assert "old@example.org" not in export


@_integration
def test_the_migration_links_the_old_field_and_keeps_it(app):
    pytest.importorskip("ckanext.dcat")
    from ckanext.actor_registry import contact_migration as cm
    sysadmin, dataset = _dataset(contact=OLD)
    with app.flask_app.test_request_context():
        data = cm.survey(sysadmin["name"])
        [candidate] = data["candidates"]
        assert candidate["key"] == "email:old@example.org"
        linked, failures, _ = cm.apply(sysadmin["name"], "create", [dataset["id"]], name="Old Desk",
                                       email="old@example.org")
    assert len(linked) == 1 and not failures
    ckan_model.Session.expire_all()
    assert json.loads(ckan_model.Package.get(dataset["id"]).extras["contact"])[0]["email"] == "old@example.org"
    with app.flask_app.test_request_context():
        counts = cm.survey(sysadmin["name"])["counts"]
    assert (counts["old"], counts["linked"], counts["remaining"]) == (1, 1, 0)


# --- Scheming's ckan_dataset converted, without ckanext-dcat: CKAN's own contact fields ----------

def _converted_multilingual_schema():
    try:
        text, _ = schema_tool.convert("ckanext.dcat.schemas:dcat_ap_multilingual.yaml")
    except schema_tool.SchemaToolError:  # ckanext-dcat not installed: the test below is skipped
        return "file:///nonexistent.yaml"
    path = os.path.join(tempfile.gettempdir(), "actor_registry_dcat_ap_multilingual_test.yaml")
    with open(path, "w", encoding="utf-8") as out:
        out.write(text)
    return "file://" + path


TITLE = {"en": "Bathing sites", "ca": "Zones de bany", "es": "Zonas de baño"}
NOTES = {"en": "Samples.", "ca": "Mostres.", "es": "Muestras."}
TAGS = {"en": ["water"], "ca": ["aigua"], "es": ["agua"]}
NAMES = {"en": "Open Data Desk", "ca": "Oficina de dades obertes", "es": "Oficina de datos abiertos"}


@pytest.fixture
def fluent_on_released_scheming(monkeypatch):
    """ckanext-fluent chains the helper scheming_missing_required_fields, which only
    ckanext-scheming's unreleased master defines; with Scheming 3.1.0 CKAN will not
    start. An empty base for the test, as a portal running both has to provide."""
    import ckan.lib.helpers as h
    if "scheming_missing_required_fields" not in h._builtin_functions:
        monkeypatch.setitem(h._builtin_functions, "scheming_missing_required_fields",
                            lambda pages, data=None, package_id=None: [])


def _installed(module):
    import importlib.util
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


@pytest.mark.skipif(not (_installed("ckanext.fluent") and _installed("ckanext.dcat")),
                    reason="needs ckanext-fluent and ckanext-dcat")  # before with_plugins tries to load them
@pytest.mark.integration
@pytest.mark.ckan_config("ckan.plugins", "dcat actor_registry scheming_datasets fluent")
@pytest.mark.ckan_config("scheming.dataset_schemas", _converted_multilingual_schema())
@pytest.mark.ckan_config("scheming.presets",
                         "ckanext.scheming:presets.json ckanext.dcat.schemas:presets.yaml ckanext.fluent:presets.json")
@pytest.mark.ckan_config("ckan.locales_offered", "en ca es")  # the schema's form_languages
@pytest.mark.usefixtures("fluent_on_released_scheming", "with_plugins", "clean_db", "actor_registry_db", "restore_option")
def test_once_closed_a_form_save_keeps_the_translations_of_the_old_field(app):
    # ckanext-fluent stores a translated subfield as a mapping (language -> text) and
    # its form sends one input per language; found by the 0.5.0 release review.
    from ckanext.actor_registry import contact_migration as cm
    sysadmin = factories.SysadminWithToken()
    org = factories.Organization()
    dataset = helpers.call_action(
        "package_create", context={"user": sysadmin["name"]}, name=f"d-{uuid.uuid4().hex[:10]}", owner_org=org["id"],
        title_translated=TITLE, notes_translated=NOTES, tags_translated=TAGS,
        contact=[{"name_translated": NAMES, "email": "old@example.org"}])
    cm.set_closed(sysadmin["name"], True, confirmed=True)

    form = _edit_form(app, sysadmin, dataset)
    hidden = dict(re.findall(r'<input type="hidden" name="(contact-[\w-]+)" value="([^"]*)" data-legacy-contact-hidden>', form))
    assert hidden["contact-0-name_translated-es"] == "Oficina de datos abiertos" and hidden["contact-0-email"] == "old@example.org"

    app.post(f"/dataset/edit/{dataset['name']}", headers={"Authorization": sysadmin["token"]}, data=dict(
        hidden, name=dataset["name"], owner_org=dataset["owner_org"], save="",
        **{f"title_translated-{lang}": text for lang, text in TITLE.items()},
        **{f"notes_translated-{lang}": text for lang, text in NOTES.items()},
        **{f"tags_translated-{lang}": ",".join(tags) for lang, tags in TAGS.items()}))
    kept = helpers.call_action("package_show", id=dataset["id"])["contact"]
    assert kept[0]["name_translated"] == NAMES
    assert kept[0]["email"] == "old@example.org"


def _converted_ckan_schema():
    text, _ = schema_tool.convert(CKAN_DATASET)
    path = os.path.join(tempfile.gettempdir(), "actor_registry_ckan_dataset_test.yaml")
    with open(path, "w", encoding="utf-8") as out:
        out.write(text)
    return "file://" + path


without_dcat = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry scheming_datasets"),
    pytest.mark.ckan_config("scheming.dataset_schemas", _converted_ckan_schema()),
    pytest.mark.ckan_config("scheming.presets", "ckanext.scheming:presets.json"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db", "restore_option"),
]


def _without_dcat(test):
    for mark in reversed(without_dcat):
        test = mark(test)
    return test


@_without_dcat
def test_without_dcat_the_old_fields_are_edited_while_open_and_kept_once_closed(app):
    from ckanext.actor_registry import contact_migration as cm
    sysadmin, dataset = _dataset(maintainer="Old Desk", maintainer_email="old@example.org",
                                 version="1.0", tags=[{"name": "water"}])
    form = _edit_form(app, sysadmin, dataset)
    assert 'name="contact_point_ids"' in form and 'id="field-maintainer_email"' in form
    page = app.get(f"/dataset/{dataset['name']}").get_data(as_text=True)
    assert "old@example.org" in page

    cm.set_closed(sysadmin["name"], True, confirmed=True)
    form = _edit_form(app, sysadmin, dataset)
    assert 'id="field-maintainer_email"' not in form
    hidden = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)" data-legacy-contact-hidden>', form))
    assert hidden["maintainer_email"] == "old@example.org"
    assert "old@example.org" not in app.get(f"/dataset/{dataset['name']}").get_data(as_text=True)

    desk = _contact("Open Data Desk", "desk@example.org")
    stored = _save_form(app, sysadmin, dataset, contact_point_ids=desk.id, version="1.0", tag_string="water",
                        **hidden)
    assert (stored.maintainer, stored.maintainer_email, stored.version) == ("Old Desk", "old@example.org", "1.0")
    assert [tag.name for tag in stored.get_tags()] == ["water"]
    assert "desk@example.org" in app.get(f"/dataset/{dataset['name']}").get_data(as_text=True)

    # 0.6.0: reopened, a dataset with a contact point still hides the old fields in the form;
    # one without shows them.
    cm.set_closed(sysadmin["name"], False)
    form = _edit_form(app, sysadmin, dataset)
    assert 'id="field-maintainer_email"' not in form and 'value="old@example.org" data-legacy-contact-hidden' in form
    _, other = _dataset(maintainer="Other Desk")
    assert 'id="field-maintainer"' in _edit_form(app, sysadmin, other)


# --- ckanext-dcat's own dcat_ap_full, unconverted: its contact field is not a legacy field ---------

@pytest.mark.integration
@pytest.mark.ckan_config("ckan.plugins", "dcat actor_registry scheming_datasets")
@pytest.mark.ckan_config("scheming.dataset_schemas", DCAT_FULL)
@pytest.mark.ckan_config("scheming.presets", "ckanext.scheming:presets.json ckanext.dcat.schemas:presets.yaml")
@pytest.mark.ckan_config("ckanext.dcat.rdf.profiles", "actor_registry_euro_dcat_ap_3")
@pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db", "restore_option")
def test_dcats_own_contact_field_stays_shown_and_exported_when_the_migration_is_closed(app):
    pytest.importorskip("ckanext.dcat")
    from ckanext.actor_registry import contact_migration as cm
    sysadmin, dataset = _dataset(contact=OLD)
    cm.set_closed(sysadmin["name"], True, confirmed=True)
    page, export = _page_and_export(app, dataset)
    assert "old@example.org" in page and "old@example.org" in export
