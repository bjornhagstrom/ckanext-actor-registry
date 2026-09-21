import uuid

import pytest

from ckan import model as ckan_model
from ckan.tests import factories

from ckanext.actor_registry import model

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry"),
    # A site must offer sv_SE itself (CKAN core ships only "sv"); the
    # extension supplies the matching catalogue so its texts stay Swedish.
    pytest.mark.ckan_config("ckan.locales_offered", "en sv sv_SE"),
    pytest.mark.usefixtures("with_plugins", "actor_registry_db"),
]

EN_IDENTIFIER = "A unique value for this organization or person"
SV_IDENTIFIER = "Ett unikt värde för organisationen eller personen"
EN_SCHEME = "Specifies how the identifier should be interpreted"
SV_SCHEME = "Anger hur identifieraren ska tolkas"
EN_INTRO = "A publisher is the organization or person responsible"
SV_INTRO = "En utgivare är den organisation eller person som ansvarar"


def _headers(user):
    return {"Authorization": user["token"]}


def _page(app, path):
    response = app.get(path, headers=_headers(factories.SysadminWithToken()))
    assert response.status_code == 200, path
    return response.get_data(as_text=True)


# "en" is the source language; "sv" and "sv_SE" both resolve to the Swedish
# catalogue. Every locale must render the texts, never a raw msgid key.
@pytest.mark.parametrize(
    "prefix, identifier, scheme, intro",
    [
        ("", EN_IDENTIFIER, EN_SCHEME, EN_INTRO),
        ("/en", EN_IDENTIFIER, EN_SCHEME, EN_INTRO),
        ("/sv", SV_IDENTIFIER, SV_SCHEME, SV_INTRO),
        ("/sv_SE", SV_IDENTIFIER, SV_SCHEME, SV_INTRO),
    ],
    ids=["default", "en", "sv", "sv_SE"],
)
def test_actor_form_help_texts_are_localised(app, prefix, identifier, scheme, intro):
    html = _page(app, f"{prefix}/actors/new")

    assert identifier in html
    assert scheme in html
    assert intro in html


@pytest.mark.parametrize("prefix, text", [("/en", "Include the country code"), ("/sv", "Ange landskod")])
def test_contactpoint_form_help_texts_are_localised(app, prefix, text):
    html = _page(app, f"{prefix}/contactpoints/new")

    assert text in html
    assert "questions about a dataset" in html or "frågor om en datamängd" in html


@pytest.mark.parametrize(
    "prefix, expected",
    [
        ("/en", 'is already used by the publisher "Skellefteå kommun"'),
        ("/sv", 'används redan av utgivaren "Skellefteå kommun"'),
        ("/sv_SE", 'används redan av utgivaren "Skellefteå kommun"'),
    ],
)
def test_identifier_conflict_message_is_localised(app, prefix, expected):
    actor_id = str(uuid.uuid4())
    ckan_model.Session.add(
        model.Actor(
            id=actor_id, name="Skellefteå kommun", actor_kind="organization",
            identifier="212000-2643", identifier_scheme="SE:ORGNR",
            uri=f"https://example.org/actor/{actor_id}", active=True,
        )
    )
    ckan_model.Session.commit()
    headers = _headers(factories.SysadminWithToken())

    response = app.post(
        f"{prefix}/actors/quick-create",
        data={"name": "Dubblett", "identifier": "212000-2643", "identifier_scheme": "SE:ORGNR"},
        headers=headers,
    )

    assert response.status_code == 409
    assert expected in response.json["error"]


def test_sv_and_sv_SE_catalogues_have_identical_translations():
    # sv_SE is a plain copy of sv (see plugin.i18n_locales). If someone edits
    # one and forgets the other, this fails instead of one locale silently
    # falling back to English.
    import os

    from babel.messages.pofile import read_po

    base = os.path.join(os.path.dirname(__file__), "..", "i18n")

    def catalogue(locale):
        with open(os.path.join(base, locale, "LC_MESSAGES", "ckanext-actor-registry.po"), "rb") as handle:
            return {m.id: m.string for m in read_po(handle) if m.id}

    assert catalogue("sv") == catalogue("sv_SE")
