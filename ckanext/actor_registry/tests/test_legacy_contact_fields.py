"""CKAN's own free-text contact fields (Author, Maintainer) in the DCAT export:
left out when the registry has contact points for the dataset, and always once
ckanext.actor_registry.legacy_contact_fields is false. Stored values are never
changed."""

import uuid

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from ckan import model as ckan_model
from ckan.tests import factories, helpers

from ckanext.actor_registry import model
from ckanext.actor_registry.profiles import VCARD, _without_legacy_contact_fields
from ckanext.dcat.profiles import DCAT

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "dcat actor_registry scheming_datasets"),
    pytest.mark.ckan_config(
        "scheming.dataset_schemas", "ckanext.actor_registry.tests.fixtures:legacy_contact_schema.yaml"
    ),
    pytest.mark.ckan_config("scheming.presets", "ckanext.scheming:presets.json"),
    pytest.mark.ckan_config("ckanext.dcat.rdf.profiles", "actor_registry_euro_dcat_ap_3"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db"),
]

OLD_FIELDS = {"maintainer": "Old Maintainer", "maintainer_email": "old@example.org",
              "author": "Old Author", "author_email": "author@example.org"}


def _contact_point():
    contact_id = str(uuid.uuid4())
    ckan_model.Session.add(model.ContactPoint(
        id=contact_id, name="Open Data Desk", email="opendata@example.org",
        uri=f"https://example.org/contact-points/{contact_id}", active=True))
    ckan_model.Session.commit()
    return contact_id


def _exported_contact_names(**fields):
    sysadmin = factories.Sysadmin()
    context = {"user": sysadmin["name"]}
    org = helpers.call_action("organization_create", context=context,
                              name=f"o-{uuid.uuid4().hex}", title="City of Riverton")
    dataset = helpers.call_action("package_create", context=context, name=f"d-{uuid.uuid4().hex}",
                                  title="Bathing sites", notes="Water samples.",
                                  owner_org=org["id"], **fields)
    turtle = helpers.call_action("dcat_dataset_show", context=context, id=dataset["id"], format="ttl")
    graph = Graph().parse(data=turtle, format="ttl")
    dataset_ref = next(graph.subjects(RDF.type, DCAT.Dataset))
    names = sorted(str(next(graph.objects(contact, VCARD.fn), ""))
                   for contact in graph.objects(dataset_ref, DCAT.contactPoint))
    stored = helpers.call_action("package_show", context=context, id=dataset["id"])
    return names, stored


@pytest.mark.parametrize("in_use", ["true", "false"])
def test_registry_contact_points_replace_the_old_fields(in_use, ckan_config, monkeypatch):
    monkeypatch.setitem(ckan_config, "ckanext.actor_registry.legacy_contact_fields", in_use)
    names, stored = _exported_contact_names(contact_point_ids=[_contact_point()], **OLD_FIELDS)
    assert names == ["Open Data Desk"]
    assert stored["maintainer"] == "Old Maintainer"


def test_without_registry_contact_points_the_maintainer_is_exported():
    names, _ = _exported_contact_names(**OLD_FIELDS)
    assert names == ["Old Maintainer"]


@pytest.mark.ckan_config("ckanext.actor_registry.legacy_contact_fields", "false")
def test_once_switched_the_old_fields_are_never_exported():
    names, stored = _exported_contact_names(**OLD_FIELDS)
    assert names == []
    assert stored["maintainer"] == "Old Maintainer"
    assert stored["author_email"] == "author@example.org"


def test_leaving_out_the_old_fields_does_not_change_the_input():
    original = {"title": "T", "maintainer": "M", "extras": [
        {"key": "contact_email", "value": "x@example.org"}, {"key": "theme", "value": "t"}]}
    exported = _without_legacy_contact_fields(original)
    assert exported == {"title": "T", "extras": [{"key": "theme", "value": "t"}]}
    assert original["maintainer"] == "M" and len(original["extras"]) == 2
    untouched = {"title": "T"}
    assert _without_legacy_contact_fields(untouched) is untouched


# The variants and the faulty data, straight through the profile.

OPEN_DATA_DESK = {"name": "Open Data Desk", "email": "opendata@example.org", "url": "",
                  "uri": "https://example.org/contact-points/desk", "phone": ""}
GIS_SUPPORT = {"name": "GIS Support", "email": "gis@example.org", "url": "",
               "uri": "https://example.org/contact-points/gis", "phone": ""}
REGISTRY = {"desk": OPEN_DATA_DESK, "gis": GIS_SUPPORT}


def _profile_contact_names(monkeypatch, **fields):
    from ckanext.actor_registry import helpers as registry_helpers
    from ckanext.actor_registry.profiles import ActorRegistryEuropeanDCATAP3Profile

    monkeypatch.setattr(
        "ckanext.actor_registry.profiles.helpers.contactpoints_resolve",
        lambda ids: [REGISTRY[i] for i in registry_helpers._id_list(ids) if i in REGISTRY])
    monkeypatch.setattr("ckanext.actor_registry.profiles.helpers.actor_display", lambda actor_id: None)
    profile = ActorRegistryEuropeanDCATAP3Profile(Graph(), compatibility_mode=False)
    dataset_ref = URIRef("https://example.org/dataset/1")
    dataset = {"id": "1", "name": "bathing-sites", "title": "Bathing sites", "notes": "",
               "resources": [], "tags": [], "extras": []}
    dataset.update(fields)
    profile.graph_from_dataset(dataset, dataset_ref)
    return sorted(str(next(profile.g.objects(contact, VCARD.fn), ""))
                  for contact in profile.g.objects(dataset_ref, DCAT.contactPoint))


DCAT_LEGACY_EXTRAS = [{"key": "contact_name", "value": "Harvested Contact"},
                      {"key": "contact_email", "value": "harvested@example.org"}]


def test_several_registry_contact_points_and_both_old_fields(monkeypatch):
    names = _profile_contact_names(monkeypatch, contact_point_ids=["desk", "gis"], **OLD_FIELDS)
    assert names == ["GIS Support", "Open Data Desk"]


def test_registry_contact_points_stored_as_json_text(monkeypatch):
    names = _profile_contact_names(monkeypatch, contact_point_ids='["desk"]', **OLD_FIELDS)
    assert names == ["Open Data Desk"]


def test_only_author_is_exported_when_there_is_no_maintainer(monkeypatch):
    names = _profile_contact_names(monkeypatch, author="Old Author", author_email="a@example.org")
    assert names == ["Old Author"]


def test_dcat_legacy_contact_extras_give_way_to_the_registry(monkeypatch):
    names = _profile_contact_names(monkeypatch, contact_point_ids=["desk"],
                                   extras=list(DCAT_LEGACY_EXTRAS))
    assert names == ["Open Data Desk"]


@pytest.mark.ckan_config("ckanext.actor_registry.legacy_contact_fields", "false")
def test_once_switched_dcat_legacy_extras_and_blank_values_are_not_exported(monkeypatch):
    names = _profile_contact_names(monkeypatch, maintainer="  ", author_email="a@example.org",
                                   extras=list(DCAT_LEGACY_EXTRAS))
    assert names == []


@pytest.mark.parametrize("ids", [["deleted-contact"], "deleted-contact", "[]", "", None, "[not json"])
def test_missing_or_broken_registry_references_fall_back_to_the_maintainer(monkeypatch, ids):
    names = _profile_contact_names(monkeypatch, contact_point_ids=ids, **OLD_FIELDS)
    assert names == ["Old Maintainer"]


@pytest.mark.ckan_config("ckanext.actor_registry.legacy_contact_fields", "false")
@pytest.mark.parametrize("ids", [["deleted-contact"], "[not json"])
def test_once_switched_broken_references_export_no_contact_point(monkeypatch, ids):
    names = _profile_contact_names(monkeypatch, contact_point_ids=ids, **OLD_FIELDS)
    assert names == []


def test_missing_setting_means_the_old_fields_are_in_use(ckan_config, monkeypatch):
    monkeypatch.delitem(ckan_config, "ckanext.actor_registry.legacy_contact_fields", raising=False)
    assert _profile_contact_names(monkeypatch, **OLD_FIELDS) == ["Old Maintainer"]


@pytest.mark.ckan_config("ckanext.actor_registry.legacy_contact_fields", "perhaps")
def test_an_unknown_setting_value_follows_ckans_rule_for_booleans(monkeypatch):
    # CKAN normalises every declared bool option: only true/yes/t/y/1 are
    # true. So an unknown word switches the old fields off, as it would for
    # any other CKAN boolean option.
    assert _profile_contact_names(monkeypatch, **OLD_FIELDS) == []


@pytest.mark.parametrize("value", ["false", "False", "no", "off", "0"])
def test_the_usual_ways_of_writing_false(ckan_config, monkeypatch, value):
    monkeypatch.setitem(ckan_config, "ckanext.actor_registry.legacy_contact_fields", value)
    assert _profile_contact_names(monkeypatch, **OLD_FIELDS) == []



def test_old_fields_the_schema_does_not_show_are_never_exported(monkeypatch):
    # What visitors see is what is exported: without these fields in the
    # schema the page shows none of them, so the export has none either.
    import ckanext.scheming.helpers as scheming_helpers
    real = scheming_helpers.scheming_get_dataset_schema

    def without_old_fields(dataset_type, expanded=True):
        schema = dict(real(dataset_type, expanded))
        schema["dataset_fields"] = [field for field in schema["dataset_fields"]
                                    if field["field_name"] not in ("maintainer", "maintainer_email",
                                                                   "author", "author_email")]
        return schema

    monkeypatch.setattr(scheming_helpers, "scheming_get_dataset_schema", without_old_fields)
    assert _profile_contact_names(monkeypatch, **OLD_FIELDS) == []


def test_without_a_scheming_schema_the_old_fields_are_exported(monkeypatch):
    # CKAN's own dataset page shows Maintainer and Author.
    import ckanext.scheming.helpers as scheming_helpers
    monkeypatch.setattr(scheming_helpers, "scheming_get_dataset_schema", lambda *args, **kwargs: None)
    assert _profile_contact_names(monkeypatch, **OLD_FIELDS) == ["Old Maintainer"]
