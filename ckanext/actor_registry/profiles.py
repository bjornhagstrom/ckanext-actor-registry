from urllib.parse import urlparse

from ckanext.dcat.profiles import DCT, FOAF, EuropeanDCATAP3Profile, SKOS
from rdflib import BNode, Literal, Namespace, RDF, URIRef

from ckanext.actor_registry import helpers
from ckanext.actor_registry.helpers import legacy_contact_fields_in_use
from ckanext.actor_registry.rdf import telephone_uri


VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")

# The free-text fields ckanext-dcat turns into a dcat:contactPoint when they
# have a value: CKAN core's Author/Maintainer, and ckanext-dcat's own legacy
# contact_* extras.
LEGACY_CONTACT_KEYS = (
    "contact_uri", "contact_name", "contact_email",
    "maintainer", "maintainer_email", "author", "author_email",
)


class ActorRegistryEuropeanDCATAP3Profile(EuropeanDCATAP3Profile):
    """DCAT-AP 3 plus vCard telephone serialization (vcard:Voice with a tel: URI)."""

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
        # ckanext-dcat adds a contact point from the free-text fields whenever
        # they have a value, even next to the registry's contact points. Leave
        # them out when the registry has contact points for the dataset, and
        # always once the catalogue has stopped using them.
        # Only the old fields the dataset page shows are exported: none when
        # the dataset has registry contact points or the catalogue has stopped
        # using them, else those in the dataset's schema.
        shown = ()
        if not dataset_dict.get("contact") and legacy_contact_fields_in_use():
            shown = _shown_legacy_fields(dataset_dict)
        author = _author(dataset_dict) if "author" in shown or "author_email" in shown else None
        dataset_dict = _without_legacy_contact_fields(dataset_dict, keep=shown)

        super().graph_from_dataset(dataset_dict, dataset_ref)

        # The dataset page shows Author while the old fields are in use (the
        # legacy_contact.html snippets), so the export says it too: CKAN's
        # author is who created the data, dct:creator (DCAT-AP-SE: producent).
        # What visitors see is what is exported.
        if author and not dataset_dict.get("creator"):
            self._add_author_as_creator(dataset_ref, author)

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
        contacts = helpers.contactpoints_display(dataset_dict.get("contact_point_ids"))
        # The same resolution as the dataset page (helpers.actor_display):
        # what visitors see is what is exported.
        publisher = helpers.actor_display(dataset_dict.get("publisher_actor_id"))
        actors = [publisher] if publisher else []
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

    def _add_author_as_creator(self, dataset_ref, author):
        creator = BNode()
        self.g.add((creator, RDF.type, FOAF.Agent))
        self.g.add((dataset_ref, DCT.creator, creator))
        self.g.add((creator, FOAF.name, Literal(author["name"] or author["email"])))
        if author["email"]:
            self.g.add((creator, FOAF.mbox, URIRef("mailto:" + author["email"])))

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


def _without_legacy_contact_fields(dataset_dict, keep=()):
    """A copy of dataset_dict without the free-text contact fields (except
    those in ``keep``), for the export only: the stored values are never
    changed."""
    drop = [key for key in LEGACY_CONTACT_KEYS if key not in keep]
    extras = dataset_dict.get("extras") or []
    if not any(dataset_dict.get(key) for key in drop) and not any(
            extra.get("key") in drop for extra in extras):
        return dataset_dict
    dataset_dict = {key: value for key, value in dataset_dict.items() if key not in drop}
    if extras:
        dataset_dict["extras"] = [extra for extra in extras if extra.get("key") not in drop]
    return dataset_dict


def _author(dataset_dict):
    """CKAN's Author as ``{"name", "email"}`` (a usable email only), or None."""
    from ckanext.actor_registry.contact_migration import clean, normalise_email
    name = clean(dataset_dict.get("author"))
    email, valid = normalise_email(dataset_dict.get("author_email"))
    email = email if valid else ""
    return {"name": name, "email": email} if name or email else None


def _shown_legacy_fields(dataset_dict):
    """The free-text contact fields the dataset page shows. With a Scheming
    schema, those in it; without one, CKAN's own page shows them all."""
    try:
        from ckanext.scheming.helpers import scheming_get_dataset_schema
        schema = scheming_get_dataset_schema(dataset_dict.get("type") or "dataset")
    except Exception:
        schema = None
    if not schema:
        return LEGACY_CONTACT_KEYS
    names = {field.get("field_name") for field in schema.get("dataset_fields", [])}
    return tuple(key for key in LEGACY_CONTACT_KEYS if key in names)


def _is_uri(value):
    return bool(value and urlparse(value).scheme)
