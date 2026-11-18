"""Names in more languages than the default one (0.7.0)."""

import uuid

import pytest
from bs4 import BeautifulSoup

from ckan import model as ckan_model
from ckan.plugins import toolkit
from ckan.tests import factories

from ckanext.actor_registry import model


pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry"),
    pytest.mark.ckan_config("ckan.locale_default", "en"),
    pytest.mark.ckan_config("ckan.locales_offered", "en sv"),
    pytest.mark.usefixtures("with_plugins", "actor_registry_db"),
]


def _actor(name, translations=None, **extra):
    item = model.Actor(id=str(uuid.uuid4()), name=name, actor_kind="organization",
                       uri=f"https://example.org/actors/{uuid.uuid4()}", active=True, **extra)
    item.set_translations(translations or {})
    ckan_model.Session.add(item)
    ckan_model.Session.commit()
    return item


def _contact(name, translations=None):
    item = model.ContactPoint(id=str(uuid.uuid4()), name=name,
                              uri=f"https://example.org/contactpoints/{uuid.uuid4()}", active=True)
    item.set_translations(translations or {})
    ckan_model.Session.add(item)
    ckan_model.Session.commit()
    return item


def _headers(user):
    return {"Authorization": user["token"]}


def _csrf(response):
    return BeautifulSoup(response.data, "html.parser").select_one('input[name="_csrf_token"]')["value"]


def test_a_record_without_translations_is_as_before():
    actor = _actor("City Board")
    data = actor.as_dict()
    assert data["name"] == data["display_name"] == "City Board"
    assert data["name_translated"] == {} and data["translations"] == {}


def test_the_names_by_language():
    actor = _actor("City Board", {"sv": {"name": "Stadsnämnden", "description": "Beskrivning"}}, description="About")
    assert actor.name_translated() == {"en": "City Board", "sv": "Stadsnämnden"}
    assert actor.as_dict()["translations"] == {"sv": {"name": "Stadsnämnden", "description": "Beskrivning"}}
    # A language without a name is removed; the others stay.
    actor.set_translations({"sv": {"name": ""}, "de": {"name": "Stadtrat"}})
    ckan_model.Session.commit()
    assert model.get_actor(actor.id).translations_dict() == {"de": {"name": "Stadtrat", "description": ""}}


def test_pages_show_the_visitors_language_and_the_default_name_otherwise(app):
    actor = _actor("City Board", {"sv": {"name": "Stadsnämnden", "description": "På svenska"}}, description="In English")
    plain = _actor("Harbour")
    contact = _contact("Front desk", {"sv": {"name": "Kundtjänst"}})
    sysadmin = factories.SysadminWithToken()
    swedish = app.get(f"/sv/actors/{actor.id}", headers=_headers(sysadmin)).body
    assert "<h1>Stadsnämnden</h1>" in swedish and "På svenska" in swedish and "In English" not in swedish
    english = app.get(f"/actors/{actor.id}", headers=_headers(sysadmin)).body
    assert "<h1>City Board</h1>" in english and "In English" in english
    assert "Harbour" in app.get(f"/sv/actors/{plain.id}", headers=_headers(sysadmin)).body
    assert "Kundtjänst" in app.get(f"/sv/contactpoints/{contact.id}", headers=_headers(sysadmin)).body
    # The lists too, sorted by the names shown.
    listing = app.get("/sv/actors", headers=_headers(sysadmin)).body
    assert listing.index("Harbour") < listing.index("Stadsnämnden")


def test_the_form_saves_translations_and_shows_a_language_no_longer_offered(app):
    sysadmin = factories.SysadminWithToken()
    actor = _actor("City Board", {"fi": {"name": "Kaupunginhallitus"}})
    form = app.get(f"/actors/{actor.id}/edit", headers=_headers(sysadmin))
    page = BeautifulSoup(form.data, "html.parser")
    assert page.select_one('input[name="translation_name-sv"]') is not None
    assert page.select_one('input[name="translation_name-en"]') is None  # the default language is the name itself
    # A language no longer offered is shown, so that it can be seen and removed.
    assert page.select_one('input[name="translation_name-fi"]')["value"] == "Kaupunginhallitus"
    assert page.select_one('input[name="translation_name-sv"]')["lang"] == "sv"
    app.post(f"/actors/{actor.id}/edit", headers=_headers(sysadmin), data={
        "_csrf_token": _csrf(form), "name": "City Board", "actor_kind": "organization", "uri": actor.uri,
        "active": "on", "translations_form": "1",
        "translation_name-sv": "Stadsnämnden", "translation_description-sv": "Om nämnden",
        "translation_name-fi": "Kaupunginhallitus"})
    saved = model.get_actor(actor.id).translations_dict()
    assert saved == {"fi": {"name": "Kaupunginhallitus", "description": ""},
                     "sv": {"name": "Stadsnämnden", "description": "Om nämnden"}}
    # Emptied, it is removed.
    form = app.get(f"/actors/{actor.id}/edit", headers=_headers(sysadmin))
    app.post(f"/actors/{actor.id}/edit", headers=_headers(sysadmin), data={
        "_csrf_token": _csrf(form), "name": "City Board", "actor_kind": "organization", "uri": actor.uri,
        "active": "on", "translations_form": "1", "translation_name-sv": "Stadsnämnden", "translation_name-fi": ""})
    assert set(model.get_actor(actor.id).translations_dict()) == {"sv"}


def test_a_description_needs_a_name_in_the_same_language(app):
    sysadmin = factories.SysadminWithToken()
    actor = _actor("City Board")
    form = app.get(f"/actors/{actor.id}/edit", headers=_headers(sysadmin))
    response = app.post(f"/actors/{actor.id}/edit", headers=_headers(sysadmin), data={
        "_csrf_token": _csrf(form), "name": "City Board", "actor_kind": "organization", "uri": actor.uri,
        "active": "on", "translations_form": "1", "translation_name-sv": "",
        "translation_description-sv": "Utan namn"})
    assert "needs a name in" in response.body
    # The field the message is about keeps what was written.
    assert BeautifulSoup(response.data, "html.parser").select_one(
        'textarea[name="translation_description-sv"]').get_text() == "Utan namn"
    assert model.get_actor(actor.id).translations == []


def test_a_contact_point_is_created_with_a_translation(app):
    sysadmin = factories.SysadminWithToken()
    form = app.get("/contactpoints/new", headers=_headers(sysadmin))
    app.post("/contactpoints/new", headers=_headers(sysadmin), data={
        "_csrf_token": _csrf(form), "name": "Front desk", "active": "on", "translations_form": "1",
        "translation_name-sv": "Kundtjänst"})
    item = ckan_model.Session.query(model.ContactPoint).filter_by(name="Front desk").one()
    assert item.translations_dict() == {"sv": {"name": "Kundtjänst"}}


def test_the_quick_edit_leaves_translations_as_they_are(app):
    sysadmin = factories.SysadminWithToken()
    actor = _actor("City Board", {"sv": {"name": "Stadsnämnden"}})
    form = app.get(f"/actors/{actor.id}", headers=_headers(sysadmin))
    app.post(f"/actors/{actor.id}/quick-edit", headers=_headers(sysadmin), data={
        "_csrf_token": _csrf(form), "name": "City Board 2", "actor_kind": "organization", "uri": actor.uri})
    item = model.get_actor(actor.id)
    assert item.name == "City Board 2" and item.translations_dict()["sv"]["name"] == "Stadsnämnden"


def test_the_choices_follow_the_page_language(app):
    _actor("City Board", {"sv": {"name": "Stadsnämnden"}})
    from ckanext.actor_registry import helpers
    with app.flask_app.test_request_context("/sv/"):
        toolkit.h.lang = lambda: "sv"
        try:
            assert "Stadsnämnden" in [choice["label"] for choice in helpers.actors_choices()]
        finally:
            del toolkit.h.lang


def test_a_merge_keeps_the_survivors_languages_and_adds_the_others():
    keep = _actor("City Board", {"sv": {"name": "Stadsnämnden"}})
    merge = _actor("Town Board", {"sv": {"name": "Kommunstyrelsen"}, "fi": {"name": "Kunnanhallitus"}})
    sysadmin = factories.Sysadmin()
    toolkit.get_action("actor_registry_actor_merge")({"user": sysadmin["name"]},
                                                     {"keep_id": keep.id, "merge_id": merge.id})
    names = {lang: entry["name"] for lang, entry in model.get_actor(keep.id).translations_dict().items()}
    assert names == {"sv": "Stadsnämnden", "fi": "Kunnanhallitus"}


def test_the_merge_page_offers_a_choice_per_language(app):
    keep = _actor("City Board", {"sv": {"name": "Stadsnämnden"}})
    merge = _actor("Town Board", {"sv": {"name": "Kommunstyrelsen"}})
    sysadmin = factories.SysadminWithToken()
    form = app.get(f"/actors/merge?ids={keep.id},{merge.id}", headers=_headers(sysadmin))
    assert 'name="field_name@sv"' in form.body
    # The kind by its label, not its stored value.
    page = BeautifulSoup(form.body, "html.parser")
    assert page.find("label", attrs={"for": "field-actor_kind-a"}).get_text(strip=True) == "Organization"
    app.post("/actors/merge", headers=_headers(sysadmin), follow_redirects=False, data={
        "_csrf_token": _csrf(form), "actor_a_id": keep.id, "actor_b_id": merge.id, "keep_id": keep.id,
        "field_name@sv": "b"})
    assert model.get_actor(keep.id).translations_dict()["sv"]["name"] == "Kommunstyrelsen"


def test_deleting_a_record_deletes_its_translations():
    actor = _actor("City Board", {"sv": {"name": "Stadsnämnden"}})
    ckan_model.Session.delete(actor)
    ckan_model.Session.commit()
    assert ckan_model.Session.query(model.ActorTranslation).filter_by(actor_id=actor.id).count() == 0


def test_a_variant_of_the_default_language_needs_no_translation_and_a_variant_falls_back_to_its_language(monkeypatch):
    from ckanext.actor_registry import language
    monkeypatch.setitem(toolkit.config, "ckan.locale_default", "sv")
    monkeypatch.setitem(toolkit.config, "ckan.locales_offered", ["en", "sv", "sv_SE", "pt_BR", "de"])
    monkeypatch.setitem(toolkit.config, "ckan.locales_filtered_out", "de")
    assert language.offered_languages() == ["en", "pt_BR"]
    # Beside a regional default, a sibling is a language of its own.
    monkeypatch.setitem(toolkit.config, "ckan.locale_default", "pt_BR")
    assert language.offered_languages() == ["en", "sv", "sv_SE"] and "pt_PT" not in language.offered_languages()
    monkeypatch.setitem(toolkit.config, "ckan.locales_offered", ["pt_BR", "pt_PT"])
    assert language.offered_languages() == ["pt_PT"]
    assert language.shows_default("pt_BR") and not language.shows_default("pt_PT")
    # Beside a regional default sv_SE, sv is a language of its own, and a page in sv_SE shows the default name.
    monkeypatch.setitem(toolkit.config, "ckan.locale_default", "sv_SE")
    assert language.shows_default("sv_SE") and not language.shows_default("sv")
    assert language.candidates("pt_BR") == ["pt_BR", "pt"] and language.candidates("en") == ["en"]


@pytest.mark.parametrize("translations", [{"en": "City of Malmö"}, {"en": None}, {"x" * 21: {"name": "Long"}},
                                          {"en": {"name": 5}}])
def test_the_merge_refuses_translations_in_the_wrong_shape(translations):
    keep, merge = _actor("City Board"), _actor("Town Board")
    with pytest.raises(toolkit.ValidationError):
        toolkit.get_action("actor_registry_actor_merge")({"user": factories.Sysadmin()["name"]},
                                                         {"keep_id": keep.id, "merge_id": merge.id,
                                                          "translations": translations})
    assert model.get_actor(merge.id).active


def test_an_inactive_choice_carries_its_default_name_for_the_quick_edit(app):
    from ckanext.actor_registry import helpers
    actor = _actor("City Board", {"sv": {"name": "Stadsnämnden"}}, )
    actor.active = False
    ckan_model.Session.commit()
    with app.flask_app.test_request_context("/sv/"):
        toolkit.h.lang = lambda: "sv"
        try:
            unavailable = helpers.actor_unavailable(actor.id)
            record = unavailable.pop("record")
            assert unavailable == {"id": actor.id, "name": "Stadsnämnden", "default_name": "City Board",
                                   "state": "inactive"}
            # The record's details, so that a quick edit of an inactive choice keeps them.
            assert record["translations"]["sv"]["name"] == "Stadsnämnden" and record["kind"] == "organization"
        finally:
            del toolkit.h.lang


def test_the_quick_panels_save_names_and_keep_what_they_do_not_show(app):
    """The dataset form's quick panels send the name per offered language; a publisher's description in that
    language, and a language no longer offered, stay as they were."""
    sysadmin = factories.SysadminWithToken()
    actor = _actor("City Board", {"sv": {"name": "Stadsnämnden", "description": "Beskrivning"},
                                  "de": {"name": "Stadtrat"}})
    form = app.get(f"/actors/{actor.id}", headers=_headers(sysadmin))
    response = app.post(f"/actors/{actor.id}/quick-edit", headers=_headers(sysadmin), data={
        "_csrf_token": _csrf(form), "name": "City Board", "actor_kind": "organization", "uri": actor.uri,
        "translations_form": "1", "translation_name-sv": "Stadsstyrelsen"})
    assert response.json["actor"]["translations"]["sv"] == {"name": "Stadsstyrelsen", "description": "Beskrivning"}
    assert model.get_actor(actor.id).translations_dict()["de"] == {"name": "Stadtrat", "description": ""}

    response = app.post("/contactpoints/quick-create", headers=_headers(sysadmin), data={
        "_csrf_token": _csrf(form), "name": "Front desk", "translations_form": "1", "translation_name-sv": "Kundtjänst"})
    assert response.json["contact_point"]["translations"] == {"sv": {"name": "Kundtjänst"}}

    response = app.post(f"/actors/{actor.id}/quick-edit", headers=_headers(sysadmin), data={
        "_csrf_token": _csrf(form), "name": "City Board", "actor_kind": "organization", "uri": actor.uri,
        "translations_form": "1", "translation_name-sv": ""}, status=400)
    assert "needs a name" in response.json["error"]


def test_the_other_quick_panels_save_names_too(app):
    sysadmin = factories.SysadminWithToken()
    contact = _contact("Front desk", {"sv": {"name": "Kundtjänst"}})
    form = app.get(f"/contactpoints/{contact.id}", headers=_headers(sysadmin))
    app.post(f"/contactpoints/{contact.id}/quick-edit", headers=_headers(sysadmin), data={
        "_csrf_token": _csrf(form), "name": "Front desk", "uri": contact.uri,
        "translations_form": "1", "translation_name-sv": "Receptionen"})
    assert model.get_contact_point(contact.id).translations_dict() == {"sv": {"name": "Receptionen"}}

    response = app.post("/actors/quick-create", headers=_headers(sysadmin), data={
        "_csrf_token": _csrf(form), "name": "Parks Board", "actor_kind": "organization",
        "translations_form": "1", "translation_name-sv": "Parknämnden"})
    assert model.get_actor(response.json["actor"]["id"]).translations_dict() == {
        "sv": {"name": "Parknämnden", "description": ""}}


def test_the_forms_show_the_languages_as_the_dataset_form_does(app):
    """One field per language, labelled with its code, the default language first (as ckanext-fluent)."""
    sysadmin = factories.SysadminWithToken()
    actor = _actor("City Board", {"sv": {"name": "Stadsnämnden", "description": "Om nämnden"}})
    page = BeautifulSoup(app.get(f"/actors/{actor.id}/edit", headers=_headers(sysadmin)).body, "html.parser")
    labels = [" ".join(label.get_text().split()) for label in page.select("label.form-label")]
    assert labels.index("EN Name *") + 1 == labels.index("SV Name")
    assert labels.index("EN Description") + 1 == labels.index("SV Description")
    assert page.select_one('input[name="translation_name-sv"]')["value"] == "Stadsnämnden"
    assert page.select_one("details") is None


def test_one_language_however_its_code_is_written_and_never_the_default_language(app):
    """pt-BR and pt_BR are one language, and a translation in the default language is not kept: the default name is
    the name in that language, also in the export."""
    actor = _actor("City Board", {"pt-BR": {"name": "Conselho"}, "en": {"name": "Another name"}})
    assert actor.translations_dict() == {"pt_BR": {"name": "Conselho", "description": ""}}
    assert actor.name_translated() == {"en": "City Board", "pt_BR": "Conselho"}
    # A row stored in the default language (before the portal changed it) does not replace the default name.
    actor.translations.append(model.ActorTranslation(lang="en", name="Old translation"))
    ckan_model.Session.commit()
    assert actor.name_translated()["en"] == "City Board"
    with app.flask_app.test_request_context("/"):
        toolkit.h.lang = lambda: "pt_BR"
        try:
            assert actor.display_name == "Conselho"
        finally:
            del toolkit.h.lang
