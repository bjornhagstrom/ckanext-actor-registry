import os
import uuid

import pytest
from pyshacl import validate
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from ckan import model as ckan_model
from ckan.tests import factories, helpers
from ckanext.actor_registry import model
from ckanext.actor_registry.profiles import VCARD
from ckanext.dcat.profiles import DCAT, DCT, FOAF, SKOS


pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config(
        "ckan.plugins", "dcat scheming_datasets actor_registry"
    ),
    pytest.mark.ckan_config(
        "scheming.dataset_schemas",
        "ckanext.actor_registry.tests.fixtures:dcat_test_schema.yaml",
    ),
    pytest.mark.ckan_config(
        "scheming.presets",
        "ckanext.scheming:presets.json ckanext.dcat.schemas:presets.yaml",
    ),
    pytest.mark.ckan_config(
        "ckanext.dcat.rdf.profiles", "actor_registry_euro_dcat_ap_3"
    ),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db"),
]


def _create_registry_records():
    actor_id = str(uuid.uuid4())
    contact_id = str(uuid.uuid4())
    actor = model.Actor(
        id=actor_id,
        name="Skellefteå kommun",
        actor_kind="organization",
        actor_type="https://example.org/concepts/public-body",
        identifier="212000-2643",
        uri="https://example.org/actors/skelleftea-kommun",
        url="https://www.skelleftea.se",
        active=True,
    )
    contact = model.ContactPoint(
        id=contact_id,
        actor_id=actor_id,
        name="Kontaktcenter",
        email="kontakt@example.org",
        phone="+46 910 73 50 00",
        uri="https://example.org/contact-points/kontaktcenter",
        url="https://www.skelleftea.se/kontakt",
        active=True,
    )
    ckan_model.Session.add_all([actor, contact])
    ckan_model.Session.flush()
    return actor, contact


def _parse(serialized, rdf_format):
    graph = Graph()
    graph.parse(data=serialized, format=rdf_format)
    return graph


@pytest.fixture
def exported_registry_dataset():
    actor, contact = _create_registry_records()
    sysadmin = factories.Sysadmin()
    context = {"user": sysadmin["name"]}
    organization = helpers.call_action(
        "organization_create",
        context=context,
        name=f"rdf-test-{uuid.uuid4().hex}",
        title="RDF testorganisation",
    )
    dataset = helpers.call_action(
        "package_create",
        context=context,
        name=f"rdf-test-{uuid.uuid4().hex}",
        title="Test av aktörsregistrets RDF-export",
        notes="En isolerad testpost för DCAT-AP 3-export.",
        owner_org=organization["id"],
        publisher_actor_id=actor.id,
        contact_point_ids=[contact.id],
        theme=[
            "http://publications.europa.eu/resource/authority/data-theme/GOVE"
        ],
    )

    outputs = {
        "turtle": helpers.call_action(
            "dcat_dataset_show", context=context, id=dataset["id"], format="ttl"
        ),
        "xml": helpers.call_action(
            "dcat_dataset_show", context=context, id=dataset["id"], format="rdf"
        ),
        "json-ld": helpers.call_action(
            "dcat_dataset_show", context=context, id=dataset["id"], format="jsonld"
        ),
    }
    return actor, contact, {
        name: _parse(data, name) for name, data in outputs.items()
    }


def test_dcat_action_exports_registry_metadata_in_all_public_formats(
    exported_registry_dataset,
):
    actor, contact, graphs = exported_registry_dataset

    actor_ref = URIRef(actor.uri)
    contact_ref = URIRef(contact.uri)
    for graph in graphs.values():
        datasets = list(graph.subjects(RDF.type, DCAT.Dataset))
        assert len(datasets) == 1
        dataset_ref = datasets[0]
        assert (dataset_ref, DCT.publisher, actor_ref) in graph
        assert (actor_ref, RDF.type, FOAF.Agent) in graph
        assert (actor_ref, FOAF.name, Literal(actor.name)) in graph
        assert (URIRef(actor.actor_type), RDF.type, SKOS.Concept) in graph
        assert (
            URIRef(
                "http://publications.europa.eu/resource/authority/data-theme/GOVE"
            ),
            RDF.type,
            SKOS.Concept,
        ) in graph
        assert (dataset_ref, DCAT.contactPoint, contact_ref) in graph
        assert (contact_ref, RDF.type, VCARD.Kind) in graph
        assert (contact_ref, VCARD.fn, Literal(contact.name)) in graph
        telephone_nodes = list(graph.objects(contact_ref, VCARD.hasTelephone))
        assert len(telephone_nodes) == 1
        assert (
            telephone_nodes[0],
            VCARD.hasValue,
            URIRef("tel:+46910735000"),
        ) in graph

    assert len(graphs["turtle"]) == len(graphs["xml"]) == len(graphs["json-ld"])


def test_export_conforms_to_official_dcat_ap_3_shapes(
    exported_registry_dataset,
):
    """Run official shapes when CI or a maintainer supplies their local path."""
    shapes_path = os.environ.get("DCAT_AP_3_SHACL_PATH")
    if not shapes_path:
        pytest.skip("Set DCAT_AP_3_SHACL_PATH to run official DCAT-AP 3 SHACL")

    actor, _, graphs = exported_registry_dataset
    # SHACL validates the range of controlled-vocabulary links too. Supply the
    # small vocabulary graph a production validator normally obtains from the
    # authoritative vocabularies; these labels are not dataset metadata.
    validation_graph = Graph()
    for triple in graphs["turtle"]:
        validation_graph.add(triple)
    theme_ref = URIRef(
        "http://publications.europa.eu/resource/authority/data-theme/GOVE"
    )
    actor_type_ref = URIRef(actor.actor_type)
    validation_graph.add((theme_ref, RDF.type, SKOS.Concept))
    validation_graph.add(
        (
            theme_ref,
            SKOS.prefLabel,
            Literal("Government and public sector", lang="en"),
        )
    )
    validation_graph.add((actor_type_ref, RDF.type, SKOS.Concept))
    validation_graph.add(
        (actor_type_ref, SKOS.prefLabel, Literal("Public body", lang="en"))
    )
    conforms, _, report = validate(
        validation_graph,
        shacl_graph=shapes_path,
        inference="rdfs",
        abort_on_first=False,
    )
    assert conforms, report
