"""The registry in Administration (2026-10-16): one tab "Actor registry" among the Administration tabs, and under it a
submenu (Publishers, Contact points, Migration, Cleanup) with a small number on the last two when something waits."""

import pytest
from bs4 import BeautifulSoup
from ckan.tests import factories

from ckanext.actor_registry.tests.test_cleanup import _actor, _deactivate
from ckanext.actor_registry.tests.test_contact_migration import _dataset, _get, _org, _page_mark


def _soup(html):
    return BeautifulSoup(html, "html.parser")


def _admin_tabs(html):
    nav = _soup(html).select_one("ul.nav-tabs")
    return {a.get_text(" ", strip=True): a["href"] for a in nav.select("a")} if nav else {}


def _submenu(html):
    """{label: href} of the submenu, with the number left out of the label."""
    nav = _soup(html).select_one("ul.registry-submenu")
    if nav is None:
        return {}
    for badge in nav.select("[data-nav-count]"):
        badge.extract()
    return {a.get_text(" ", strip=True): a["href"] for a in nav.select("a")}


def _counts(html):
    return {a.get_text(" ", strip=True).split(" ")[0]: badge.get_text(strip=True)
            for a in _soup(html).select("ul.registry-submenu a") for badge in a.select("[data-nav-count]")}


@_page_mark
def test_a_visitor_sees_no_navigation_on_a_public_page(app):
    actor = _actor()
    html = app.get(f"/en/actors/{actor.id}").get_data(as_text=True)
    assert _admin_tabs(html) == {} and _submenu(html) == {}


@_page_mark
def test_an_editor_sees_the_submenu_but_no_administration_tabs(app):
    editor = factories.UserWithToken()
    org = _org(users=[(editor, "editor")])
    _dataset(org)
    html = _get(app, editor, "/actors")
    menu = _submenu(html)
    assert list(menu) == ["Publishers", "Contact points", "Migration", "Cleanup"]
    assert menu["Publishers"].endswith("/actors") and menu["Cleanup"].endswith("/actor-registry/cleanup")
    assert _admin_tabs(html) == {} and "/ckan-admin/config" not in html


@_page_mark
def test_a_user_without_a_dataset_to_edit_sees_only_the_two_lists(app):
    user = factories.UserWithToken()
    assert list(_submenu(_get(app, user, "/actors"))) == ["Publishers", "Contact points"]


@_page_mark
def test_a_sysadmin_sees_the_administration_tabs_with_the_registry_active_and_the_submenu_under_it(app):
    sysadmin = factories.SysadminWithToken()
    html = _get(app, sysadmin, "/contactpoints")
    tabs = _admin_tabs(html)
    assert "Config" in tabs and tabs["Actor registry"].endswith("/actors")
    active = _soup(html).select_one("ul.nav-tabs li.active")
    assert active is not None and "Actor registry" in active.get_text()
    assert list(_submenu(html)) == ["Publishers", "Contact points", "Migration", "Cleanup"]


@_page_mark
def test_migration_and_cleanup_show_a_number_when_something_waits(app):
    sysadmin = factories.SysadminWithToken()
    org = _org()
    _dataset(org, maintainer="Desk", maintainer_email="desk@example.org")
    old = _actor(name="Old Board")
    _dataset(org, publisher_actor_id=old.id)
    _deactivate(old)
    assert _counts(_get(app, sysadmin, "/actors")) == {"Migration": "1", "Cleanup": "1"}


@_page_mark
def test_no_number_when_nothing_waits(app):
    sysadmin = factories.SysadminWithToken()
    assert _counts(_get(app, sysadmin, "/actors")) == {}


@_page_mark
def test_administration_has_the_registry_tab_and_nothing_of_the_submenu(app):
    sysadmin = factories.SysadminWithToken()
    html = _get(app, sysadmin, "/ckan-admin/config")
    assert _admin_tabs(html)["Actor registry"].endswith("/actors")
    assert _submenu(html) == {}


@_page_mark
@pytest.mark.ckan_config("ckanext.actor_registry.admin_tab", "false")
def test_the_administration_tab_can_be_turned_off(app):
    sysadmin = factories.SysadminWithToken()
    assert "Actor registry" not in _admin_tabs(_get(app, sysadmin, "/ckan-admin/config"))


@_page_mark
def test_the_dashboard_has_a_tab_to_the_registry_for_those_who_may_edit(app):
    editor = factories.UserWithToken()
    _dataset(_org(users=[(editor, "editor")]))
    nobody = factories.UserWithToken()
    html = _get(app, editor, "/dashboard/datasets")
    assert 'href="/actors"' in html
    assert 'href="/actors"' not in _get(app, nobody, "/dashboard/datasets")
