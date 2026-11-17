"""The registry in Administration (2026-10-16): one tab "Actor registry" among the Administration tabs, and under it a
submenu (To do, Publishers, Contact points; 0.6.0 moved Cleanup and Migration into tabs of the first and the last), To do with a small number when something waits. To do (0.6.0)
comes first, and the ways into the registry lead there."""

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
    assert list(menu) == ["To do", "Publishers", "Contact points"]
    assert menu["To do"].endswith("/actor-registry/todo") and menu["Publishers"].endswith("/actors")
    assert 'href="/actor-registry/cleanup"' in _get(app, editor, "/actor-registry/todo")
    assert _admin_tabs(html) == {} and "/ckan-admin/config" not in html


@_page_mark
def test_a_user_without_a_dataset_to_edit_sees_only_the_two_lists(app):
    user = factories.UserWithToken()
    assert list(_submenu(_get(app, user, "/actors"))) == ["To do", "Publishers", "Contact points"]


@_page_mark
def test_a_sysadmin_sees_the_administration_tabs_with_the_registry_active_and_the_submenu_under_it(app):
    sysadmin = factories.SysadminWithToken()
    html = _get(app, sysadmin, "/contactpoints")
    tabs = _admin_tabs(html)
    assert "Config" in tabs and tabs["Actor registry"].endswith("/actor-registry/todo")
    active = _soup(html).select_one("ul.nav-tabs li.active")
    assert active is not None and "Actor registry" in active.get_text()
    assert list(_submenu(html)) == ["To do", "Publishers", "Contact points"]


@_page_mark
def test_to_do_shows_a_number_when_something_waits_and_the_migration_tab_too(app):
    sysadmin = factories.SysadminWithToken()
    org = _org()
    _dataset(org, maintainer="Desk", maintainer_email="desk@example.org")
    old = _actor(name="Old Board")
    _dataset(org, publisher_actor_id=old.id)
    _deactivate(old)
    # Both datasets also lack a contact point, so both are on To do, plus the one to clean up.
    assert _counts(_get(app, sysadmin, "/actors")) == {"To": "3"}
    # Contact points has no number in the menu (it would count datasets); the tab has it.
    assert 'Create contact points from the datasets <span class="badge text-bg-warning">1</span>' in _get(app, sysadmin, "/contactpoints?list=1")


@_page_mark
def test_no_number_when_nothing_waits(app):
    sysadmin = factories.SysadminWithToken()
    assert _counts(_get(app, sysadmin, "/actors")) == {}


@_page_mark
def test_administration_has_the_registry_tab_and_nothing_of_the_submenu(app):
    sysadmin = factories.SysadminWithToken()
    html = _get(app, sysadmin, "/ckan-admin/config")
    assert _admin_tabs(html)["Actor registry"].endswith("/actor-registry/todo")
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
    assert 'href="/actor-registry/todo"' in html
    assert 'href="/actor-registry/todo"' not in _get(app, nobody, "/dashboard/datasets")


# --- 0.6.0 (Björn's test 2026-11-14): controls only when they can do something ------------------

def _contact_point(name, active=True):
    import uuid
    from ckan import model as ckan_model
    from ckanext.actor_registry import model
    item = model.ContactPoint(id=str(uuid.uuid4()), name=name, uri=f"https://example.org/cp/{uuid.uuid4()}", active=active)
    ckan_model.Session.add(item)
    ckan_model.Session.commit()
    return item


@_page_mark
def test_the_show_merged_box_and_merging_appear_only_when_they_can_do_something(app):
    sysadmin = factories.SysadminWithToken()
    first = _actor("City Board")
    html = _get(app, sysadmin, url="/actors")
    assert 'name="show_merged"' not in html and "data-actor-merge-submit" not in html
    assert "data-actor-merge-checkbox" not in html

    second = _actor("Town Board")
    html = _get(app, sysadmin, url="/actors")
    assert "data-actor-merge-submit" in html and html.count("data-actor-merge-checkbox") == 2
    assert 'name="show_merged"' not in html

    _deactivate(second, merged_into=first)
    html = _get(app, sysadmin, url="/actors")
    assert 'name="show_merged"' in html and "data-actor-merge-submit" not in html  # one active left
    assert "Town Board" not in html and "Town Board" in _get(app, sysadmin, url="/actors?show_merged=1")


@_page_mark
def test_the_show_inactive_box_appears_only_when_there_are_inactive_contact_points(app):
    sysadmin = factories.SysadminWithToken()
    _contact_point("Open Data Desk")
    html = _get(app, sysadmin, url="/contactpoints")
    assert 'name="show_inactive"' not in html
    _contact_point("Old Desk", active=False)
    html = _get(app, sysadmin, url="/contactpoints")
    assert 'name="show_inactive"' in html and "Old Desk" not in html
    assert "Old Desk" in _get(app, sysadmin, url="/contactpoints?show_inactive=1")
