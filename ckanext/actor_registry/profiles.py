from urllib.parse import urlparse

from ckanext.dcat.profiles import EuropeanDCATAP3Profile, SKOS
from rdflib import BNode, Namespace, RDF, URIRef

from ckanext.actor_registry import helpers
from ckanext.actor_registry.rdf import telephone_uri


VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")


class ActorRegistryEuropeanDCATAP3Profile(EuropeanDCATAP3Profile):
    """DCAT-AP 3 plus DCAT-AP-SE-compatible telephone serialization."""

    def graph_from_dataset(self, dataset_dict, dataset_ref):
        # ckanext-dcat's scheming profile (which we inherit) expects
        # "contact"/"publisher" vcard/foaf-shaped dicts directly on
        # dataset_dict. The registry only stores contact_point_ids/
        # publisher_actor_id on the dataset itself, so resolve those to full
        # dicts here, on a *copy* of dataset_dict, rather than mutating the
        # shared dict (see plugin.py for why: an earlier version injected
        # these in after_dataset_show, which leaked back into resource-form
        # validation and caused a "__junk" error for any dataset with a
        # contact point or publisher assigned).
        dataset_dict = self._with_resolved_contact_and_publisher(dataset_dict)

        super().graph_from_dataset(dataset_dict, dataset_ref)

        # DCAT-AP 3 requires controlled vocabulary values such as themes and
        # agent types to be SKOS concepts. ckanext-dcat emits their links but
        # deliberately does not dereference vocabularies, so provide the local
        # type assertions required for standalone SHACL validation.
        for theme in dataset_dict.get("theme") or []:
            if _is_uri(theme):
                self.g.add((URIRef(theme), RDF.type, SKOS.Concept))

        for publisher in dataset_dict.get("publisher") or []:
            actor_type = publisher.get("type")
            if _is_uri(actor_type):
                self.g.add((URIRef(actor_type), RDF.type, SKOS.Concept))

    @staticmethod
    def _with_resolved_contact_and_publisher(dataset_dict):
        contacts = helpers.contactpoints_resolve(dataset_dict.get("contact_point_ids"))
        actors = helpers.actors_resolve(dataset_dict.get("publisher_actor_id"))
        if not contacts and not actors:
            return dataset_dict

        dataset_dict = dict(dataset_dict)

        if contacts:
            dataset_dict["contact"] = [
                {
                    "name": item["name"],
                    "email": item["email"],
                    "url": item["url"],
                    "uri": item["uri"],
                    "phone": item["phone"],
                }
                for item in contacts
            ]

        if actors:
            item = actors[0]
            dataset_dict["publisher"] = [{
                "name": item["name"], "identifier": item["identifier"],
                "uri": item["uri"], "url": item["url"],
                "email": item["email"], "type": item["type"],
            }]

        return dataset_dict

    def _add_contact_to_graph(self, subject, predicate, contact):
        super()._add_contact_to_graph(subject, predicate, contact)
        phone = contact.get("phone")
        if not phone:
            return

        contact_ref = URIRef(contact["uri"]) if contact.get("uri") else None
        if contact_ref is None:
            return

        phone_uri = telephone_uri(phone)
        if not phone_uri:
            return
        telephone = BNode()
        self.g.add((contact_ref, VCARD.hasTelephone, telephone))
        self.g.add((telephone, RDF.type, VCARD.Voice))
        self.g.add((telephone, VCARD.hasValue, URIRef(phone_uri)))


def _is_uri(value):
    return bool(value and urlparse(value).scheme)
