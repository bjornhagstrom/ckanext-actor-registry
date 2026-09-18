from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from ckanext.actor_registry.profiles import (
    ActorRegistryEuropeanDCATAP3Profile,
    VCARD,
)
from ckanext.actor_registry.rdf import telephone_uri
from ckanext.dcat.profiles import DCAT, DCT, FOAF


def _profile():
    return ActorRegistryEuropeanDCATAP3Profile(Graph(), compatibility_mode=False)


def test_telephone_uri_normalizes_common_display_formatting():
    assert telephone_uri("+46 (0)910-12 34 56") == "tel:+460910123456"
    assert telephone_uri("tel:+46 910 12 34 56") == "tel:+46910123456"
    assert telephone_uri("") == ""


def test_contact_is_serialized_as_vcard_with_clickable_phone():
    profile = _profile()
    dataset_ref = URIRef("https://example.org/dataset/1")
    contact_ref = URIRef("https://example.org/contact/data-service")

    profile._add_contact_to_graph(
        dataset_ref,
        DCAT.contactPoint,
        {
            "uri": str(contact_ref),
            "name": "Datakontakt",
            "email": "data@example.org",
            "url": "https://example.org/contact",
            "phone": "+46 910 12 34 56",
        },
    )

    graph = profile.g
    assert (dataset_ref, DCAT.contactPoint, contact_ref) in graph
    assert (contact_ref, RDF.type, VCARD.Kind) in graph
    assert (contact_ref, VCARD.fn, Literal("Datakontakt")) in graph
    assert (contact_ref, VCARD.hasEmail, URIRef("mailto:data@example.org")) in graph
    assert (contact_ref, VCARD.hasURL, URIRef("https://example.org/contact")) in graph

    phone_nodes = list(graph.objects(contact_ref, VCARD.hasTelephone))
    assert len(phone_nodes) == 1
    assert (phone_nodes[0], RDF.type, VCARD.Voice) in graph
    assert (phone_nodes[0], VCARD.hasValue, URIRef("tel:+46910123456")) in graph


def test_contact_without_phone_has_no_telephone_node():
    profile = _profile()
    dataset_ref = URIRef("https://example.org/dataset/1")
    contact_ref = URIRef("https://example.org/contact/data-service")

    profile._add_contact_to_graph(
        dataset_ref,
        DCAT.contactPoint,
        {"uri": str(contact_ref), "name": "Datakontakt", "phone": ""},
    )

    assert list(profile.g.objects(contact_ref, VCARD.hasTelephone)) == []


def test_same_contact_uri_is_reused_across_datasets():
    profile = _profile()
    contact = {
        "uri": "https://example.org/contact/data-service",
        "name": "Datakontakt",
        "email": "data@example.org",
    }
    first = URIRef("https://example.org/dataset/1")
    second = URIRef("https://example.org/dataset/2")

    profile._add_contact_to_graph(first, DCAT.contactPoint, contact)
    profile._add_contact_to_graph(second, DCAT.contactPoint, contact)

    contact_ref = URIRef(contact["uri"])
    assert (first, DCAT.contactPoint, contact_ref) in profile.g
    assert (second, DCAT.contactPoint, contact_ref) in profile.g
    assert len(set(profile.g.objects(None, DCAT.contactPoint))) == 1


def test_publisher_is_a_distinct_foaf_agent():
    profile = _profile()
    dataset_ref = URIRef("https://example.org/dataset/1")
    publisher_ref = URIRef("https://example.org/actor/environment-board")

    profile._add_agents(
        dataset_ref,
        {
            "publisher": [
                {
                    "uri": str(publisher_ref),
                    "name": "Miljönämnden",
                    "identifier": "212000-2643",
                    "url": "https://example.org/environment-board",
                }
            ]
        },
        "publisher",
        DCT.publisher,
    )

    graph = profile.g
    assert (dataset_ref, DCT.publisher, publisher_ref) in graph
    assert (publisher_ref, RDF.type, FOAF.Agent) in graph
    assert (publisher_ref, FOAF.name, Literal("Miljönämnden")) in graph
    assert (publisher_ref, DCT.identifier, Literal("212000-2643")) in graph
    assert not list(graph.objects(dataset_ref, DCAT.contactPoint))


def test_resolve_contact_and_publisher_does_not_mutate_input(monkeypatch):
    """Regression test for the "__junk" resource-save bug.

    An earlier version resolved contact_point_ids/publisher_actor_id into
    "contact"/"publisher" dicts inside IPackageController.after_dataset_show,
    mutating the shared pkg_dict in place. That pkg_dict gets reused as the
    base data for later actions -- notably the multi-step "add resource"
    wizard, which re-validates the whole package against the scheming
    schema. Since "contact"/"publisher" aren't declared schema fields, this
    made saving a resource fail with a spurious "__junk: ... was not
    expected" error for any dataset that actually had a contact point or
    publisher assigned.

    The fix resolves these fields on a *copy*, only at RDF-serialization
    time. This test locks in both: the resolved shape, and that the
    original dict handed in is left untouched.
    """
    contact = {
        "id": "contact-1",
        "name": "Datakontakt",
        "email": "data@example.org",
        "url": "https://example.org/contact",
        "uri": "https://example.org/contact/data",
        "phone": "+46910123456",
    }
    actor = {
        "id": "actor-1",
        "name": "Miljönämnden",
        "identifier": "212000-2643",
        "uri": "https://example.org/actor/environment-board",
        "url": "https://example.org/environment-board",
        "email": "board@example.org",
        "type": "public-body",
    }
    monkeypatch.setattr(
        "ckanext.actor_registry.profiles.helpers.contactpoints_resolve",
        lambda ids: [contact] if ids == ["contact-1"] else [],
    )
    monkeypatch.setattr(
        "ckanext.actor_registry.profiles.helpers.actors_resolve",
        lambda ids: [actor] if ids == "actor-1" else [],
    )
    original = {
        "contact_point_ids": ["contact-1"],
        "publisher_actor_id": "actor-1",
    }

    resolved = ActorRegistryEuropeanDCATAP3Profile._with_resolved_contact_and_publisher(
        original
    )

    # The input dict is untouched -- this is the actual bug fix.
    assert "contact" not in original
    assert "publisher" not in original

    assert resolved["contact"] == [
        {
            "name": "Datakontakt",
            "email": "data@example.org",
            "url": "https://example.org/contact",
            "uri": "https://example.org/contact/data",
            "phone": "+46910123456",
        }
    ]
    assert resolved["publisher"] == [
        {
            "name": "Miljönämnden",
            "identifier": "212000-2643",
            "uri": "https://example.org/actor/environment-board",
            "url": "https://example.org/environment-board",
            "email": "board@example.org",
            "type": "public-body",
        }
    ]


def test_resolve_contact_and_publisher_leaves_missing_references_unexpanded(monkeypatch):
    monkeypatch.setattr(
        "ckanext.actor_registry.profiles.helpers.contactpoints_resolve", lambda ids: []
    )
    monkeypatch.setattr(
        "ckanext.actor_registry.profiles.helpers.actors_resolve", lambda ids: []
    )
    original = {
        "contact_point_ids": ["deleted-contact"],
        "publisher_actor_id": "deleted-actor",
    }

    resolved = ActorRegistryEuropeanDCATAP3Profile._with_resolved_contact_and_publisher(
        original
    )

    assert "contact" not in resolved
    assert "publisher" not in resolved
    # Nothing to resolve means the same object can be returned as-is.
    assert resolved is original
