"""The second example schema: CKAN organizations plus shared contact points, no
publisher field (examples/contact_points_only_schema.yaml)."""

import uuid

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from ckan import model as ckan_model
from ckan.tests import factories, helpers

from ckanext.actor_registry import model
from ckanext.actor_registry.profiles import VCARD
from ckanext.dcat.profiles import DCAT, DCT, FOAF

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "dcat actor_registry scheming_datasets"),
    pytest.mark.ckan_config(
        "scheming.dataset_schemas", "ckanext.actor_registry.examples:contact_points_only_schema.yaml"
    ),
    pytest.mark.ckan_config("scheming.presets", "ckanext.scheming:presets.json"),
    pytest.mark.ckan_config("ckanext.dcat.rdf.profiles", "actor_registry_euro_dcat_ap_3"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db"),
]


def _contact_point():
    contact_id = str(uuid.uuid4())
    ckan_model.Session.add(model.ContactPoint(
        id=contact_id, name="Open Data Desk", email="opendata@example.org",
        uri=f"https://example.org/contact-points/{contact_id}", active=True))
    ckan_model.Session.commit()
    return contact_id


def _dataset(**fields):
    sysadmin = factories.Sysadmin()
    context = {"user": sysadmin["name"]}
    org = helpers.call_action("organization_create", context=context,
                              name=f"o-{uuid.uuid4().hex}", title="City of Riverton")
    return helpers.call_action("package_create", context=context, name=f"d-{uuid.uuid4().hex}",
                               title="Bathing sites", notes="Water samples.", owner_org=org["id"],
                               **fields), org, sysadmin


def test_a_dataset_needs_no_publisher_and_links_contact_points():
    contact_id = _contact_point()
    dataset, _, _ = _dataset(contact_point_ids=[contact_id])
    assert dataset["contact_point_ids"] == [contact_id]
    assert not dataset.get("publisher_actor_id")


def test_the_form_has_contact_points_but_no_publisher_field(app):
    sysadmin = factories.SysadminWithToken()
    html = app.get("/dataset/new", headers={"Authorization": sysadmin["token"]}).get_data(as_text=True)
    assert 'name="contact_point_ids"' in html
    assert 'name="publisher_actor_id"' not in html


def test_dcat_uses_the_organization_as_publisher_and_the_registry_contact_point():
    contact_id = _contact_point()
    dataset, org, sysadmin = _dataset(contact_point_ids=[contact_id])
    turtle = helpers.call_action("dcat_dataset_show", context={"user": sysadmin["name"]},
                                 id=dataset["id"], format="ttl")
    graph = Graph().parse(data=turtle, format="ttl")
    dataset_ref = next(graph.subjects(RDF.type, DCAT.Dataset))

    publisher = next(graph.objects(dataset_ref, DCT.publisher))
    assert str(next(graph.objects(publisher, FOAF.name))) == "City of Riverton"

    contact = next(graph.objects(dataset_ref, DCAT.contactPoint))
    assert contact == URIRef(f"https://example.org/contact-points/{contact_id}")
    assert str(next(graph.objects(contact, VCARD.fn))) == "Open Data Desk"


def test_the_prompt_never_asks_for_a_publisher_without_a_publisher_field(app):
    dataset, _, _ = _dataset()
    sysadmin = factories.SysadminWithToken()
    html = app.get(f"/dataset/{dataset['name']}",
                   headers={"Authorization": sysadmin["token"]}).get_data(as_text=True)
    assert "Contact point missing." in html
    assert "Publisher" not in html.split("data-dataset-actor-link-prompt", 1)[1].split("</form>", 1)[0]


def test_no_prompt_when_the_contact_point_is_set(app):
    dataset, _, _ = _dataset(contact_point_ids=[_contact_point()])
    sysadmin = factories.SysadminWithToken()
    html = app.get(f"/dataset/{dataset['name']}",
                   headers={"Authorization": sysadmin["token"]}).get_data(as_text=True)
    assert "data-dataset-actor-link-prompt" not in html
