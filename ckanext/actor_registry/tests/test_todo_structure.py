"""The registry's structure after the second round of 0.6.0: To do with search, filters, names, tabs
and "Create new…"; Contact points with the migration as a tab; the table of contents."""

from ckan.tests import factories, helpers

from ckanext.actor_registry import contact_migration
from ckanext.actor_registry.tests.test_cleanup import _actor, _deactivate
from ckanext.actor_registry.tests.test_contact_migration import (
    _contact_point, _dataset, _get, _org, _page_mark)

TODO = "/actor-registry/todo"


@_page_mark
def test_search_tag_and_organisation_narrow_the_list_and_offer_their_choices(app):
    sysadmin = factories.SysadminWithToken()
    north, south = _org(), _org()
    _dataset(north, title="Noise map 2017", tags=[{"name": "noise"}])
    _dataset(south, title="Noise map 2022", tags=[{"name": "noise"}, {"name": "maps"}])
    bus = _dataset(south, title="Bus stops", tags=[{"name": "maps"}])
    helpers.call_action("package_patch", context={"user": factories.Sysadmin()["name"]}, id=bus["id"],
                        notes="Where buses stop, 100% of them.")

    def titles(query):
        html = _get(app, sysadmin, TODO + query)
        return sorted(title for title in ("Noise map 2017", "Noise map 2022", "Bus stops") if f">{title}</a>" in html)

    assert titles("") == ["Bus stops", "Noise map 2017", "Noise map 2022"]
    assert titles("?q=noise") == ["Noise map 2017", "Noise map 2022"]
    assert titles("?q=buses") == ["Bus stops"]          # the description
    assert titles("?q=%25") == ["Bus stops"]            # % is a character, not a wildcard
    assert titles("?q=_") == []                          # and so is _
    assert titles("?q=%5C") == []                        # a backslash neither breaks the query nor matches
    assert titles("?tag=maps") == ["Bus stops", "Noise map 2022"]
    assert titles(f"?org={north['id']}") == ["Noise map 2017"]
    assert titles(f"?tag=noise&org={south['id']}") == ["Noise map 2022"]
    # Several tags: a dataset has them all; several organisations: it belongs to one of them.
    assert titles("?tag=maps&tag=noise") == ["Noise map 2022"]
    assert titles(f"?org={north['id']}&org={south['id']}") == ["Bus stops", "Noise map 2017", "Noise map 2022"]
    html = _get(app, sysadmin, TODO + "?tag=maps")
    # Another tag counts with the chosen one, which is no longer offered but shown with a link that removes it;
    # the filters ride along on the other links and the form, which all lead back to the filters.
    assert '<option value="noise">noise (1)</option>' in html and '<option value="maps"' not in html
    chosen = html.split("data-todo-chosen>")[1].split("</ul>")[0]
    assert "Tag: maps" in chosen and 'href="/actor-registry/todo?missing=either#todo-filters"' in chosen
    assert 'name="tag" value="maps"' in html and 'action="/actor-registry/todo#todo-filters"' in html
    pills = html.split('aria-label="Show datasets that lack"')[1].split("</ul>")[0]
    assert "tag=maps" in pills and "#todo-filters" in pills
    assert "With several tags, the list shows the datasets that have all of them." in html
    assert "No datasets match the filters." in _get(app, sysadmin, TODO + "?q=nothing-like-this")


@_page_mark
def test_a_save_keeps_the_page_and_the_filters(app):
    sysadmin = factories.SysadminWithToken()
    board = _actor("City Board")
    dataset = _dataset(_org(), title="Bare", tags=[{"name": "noise"}])
    response = app.post(TODO + "/assign", headers={"Authorization": sysadmin["token"]}, follow_redirects=False, data={
        "missing": "publisher", "page": "3", "q": "Bare", "tag": ["noise", "maps"], "assign_from": "top",
        f"publisher_for_{dataset['id']}": board.id})
    location = response.headers["Location"]
    for part in ("missing=publisher", "page=3", "q=Bare", "tag=noise", "tag=maps"):
        assert part in location
    # Back at the list, not at the top of the page.
    assert location.endswith("#todo-list")


@_page_mark
def test_rows_name_what_is_set_and_the_page_has_the_whole_width(app):
    sysadmin = factories.SysadminWithToken()
    board, desk, other = _actor("City Board"), _contact_point("Desk"), _contact_point("Second desk")
    half = _dataset(_org(), title="Half", publisher_actor_id=board.id)
    _dataset(_org(), title="Other half", contact_point_ids=[desk.id, other.id])
    html = _get(app, sysadmin, TODO)
    assert "<span data-assign-current>City Board</span>" in html
    assert "<span data-assign-current>Desk, Second desk</span>" in html
    # What is set is changed on the dataset's form, at the field itself; what is missing stands out.
    assert (f'href="/dataset/edit/{half["name"]}#field-publisher_actor_id" data-todo-edit>Edit'
            '<span class="visually-hidden"> Half</span>') in html
    assert '#field-contact_point_ids" data-todo-edit>' in html
    assert html.count("data-todo-edit") == 2 and html.count("data-todo-missing") == 2
    assert '<aside class="secondary' not in html
    assert "wrapper registry-wide" in html and "_todo.css" in html
    # The bar: a line that explains it, no colons, one Save for everything, and "Create new…" for the script.
    assert "Select datasets in the list and choose here what they should get." in html
    assert "For the selected datasets:" not in html and "Missing:" not in html
    assert html.count("data-assign-save") == 2 and "Save on selected" not in html
    assert 'data-i18n-create-new="Create new…"' in html
    assert 'data-create-dialog="publisher"' in html and 'data-create-dialog="contact_point"' in html
    assert 'data-i18n-leave=' in html and "data-unsaved-badge" in html
    assert 'data-assign-all aria-label="Select all"' in html


@_page_mark
def test_to_do_has_the_cleanup_as_a_tab_and_the_menu_has_three_entries(app):
    sysadmin = factories.SysadminWithToken()
    retired = _actor("Retired")
    _dataset(_org(), title="Uses retired", publisher_actor_id=retired.id)
    _deactivate(retired)
    html = _get(app, sysadmin, TODO)
    submenu = html.split('class="nav nav-pills registry-submenu"')[1].split("</ul>")[0]
    assert "To do" in submenu and "Publishers" in submenu and "Contact points" in submenu
    assert "Migration" not in submenu and "Cleanup" not in submenu
    assert 'href="/actor-registry/cleanup">Inactive or removed <span class="badge' in html
    cleanup_page = _get(app, sysadmin, "/actor-registry/cleanup")
    assert '<h1 class="page-heading">To do</h1>' in cleanup_page
    assert 'aria-current="page">Inactive or removed' in cleanup_page
    # To do is the active menu entry on the clean-up tab too.
    submenu = cleanup_page.split('class="nav nav-pills registry-submenu"')[1].split("</ul>")[0]
    assert submenu.index('aria-current="page"') < submenu.index("Publishers")


@_page_mark
def test_an_editor_without_cleanup_rights_sees_no_tabs(app):
    member = factories.UserWithToken()
    _org(users=[(member, "member")])
    html = _get(app, member, TODO)
    assert "Inactive or removed" not in html and "nav-tabs" not in html.split("registry-submenu")[-1]


@_page_mark
def test_contact_points_open_on_the_migration_while_datasets_wait_and_have_it_as_a_tab(app):
    sysadmin = factories.SysadminWithToken()
    _contact_point("Desk")
    old = _dataset(_org(), title="Old contact", maintainer="Desk", maintainer_email="desk@example.org")

    def opens(user):
        response = app.get("/contactpoints", headers={"Authorization": user["token"]}, follow_redirects=False)
        return response.headers["Location"] if response.status_code == 302 else response.get_data(as_text=True)
    # Datasets wait: the migration comes first, also with contact points in the register.
    assert opens(sysadmin).endswith("/actor-registry/migrate")
    listing = _get(app, sysadmin, "/contactpoints?list=1")
    assert "Create contact points from the datasets" in listing and "data-migration-hint" not in listing
    migrate = _get(app, sysadmin, "/actor-registry/migrate")
    assert '<h1 class="page-heading">Contact points</h1>' in migrate
    assert 'aria-current="page">Create contact points from the datasets' in migrate
    # Only skipped ones left: the list comes first, the tab stays without a number and opens on the skipped ones.
    contact_migration.apply(sysadmin["name"], "skip", [old["id"]])
    listing = opens(sysadmin)
    assert 'href="/actor-registry/migrate">Create contact points from the datasets</a>' in listing
    migrate = _get(app, sysadmin, "/actor-registry/migrate")
    assert "/actor-registry/migrate/unskip" in migrate and "Show 1 skipped dataset" not in migrate


@_page_mark
def test_the_migration_tab_shows_for_editors_only_while_something_is_left(app):
    sysadmin, editor = factories.SysadminWithToken(), factories.UserWithToken()
    _contact_point("Desk")
    _org(users=[(editor, "editor")])
    # Nothing to migrate anywhere: the sysadmin keeps the tab (datasets may come later), the editor does not see it.
    assert "Create contact points from the datasets" in _get(app, sysadmin, "/contactpoints?list=1")
    assert "Create contact points from the datasets" not in _get(app, editor, "/contactpoints?list=1")


@_page_mark
def test_a_closed_migration_has_no_tab_but_a_link_for_sysadmins(app):
    sysadmin = factories.SysadminWithToken()
    _contact_point("Desk")
    contact_migration.set_closed(sysadmin["name"], True, confirmed=True)
    html = _get(app, sysadmin, "/contactpoints")
    assert "Create contact points from the datasets" not in html and "data-migration-hint" not in html
    assert "data-migration-closed-link" in html and 'href="/actor-registry/migrate#close"' in html
    editor = factories.UserWithToken()
    _org(users=[(editor, "editor")])
    assert "data-migration-closed-link" not in _get(app, editor, "/contactpoints")


@_page_mark
def test_publishers_say_they_are_not_taken_from_the_datasets(app):
    sysadmin = factories.SysadminWithToken()
    html = _get(app, sysadmin, "/actors")
    assert "data-publishers-not-migrated" in html
    # Why a publisher besides the organisation, in the left column, where the dataset form links.
    aside = html.split('<aside class="secondary')[1].split("</aside>")[0]
    assert 'id="publisher-or-organization"' in aside and "Publisher or organization?" in aside


@_page_mark
def test_pages_with_a_left_column_get_the_table_of_contents(app):
    sysadmin = factories.SysadminWithToken()
    html = _get(app, sysadmin, "/actor-registry/migrate")
    aside = html.split('<aside class="secondary')[1].split("</aside>")[0]
    assert "data-page-toc" in aside and "On this page" in aside
    assert aside.index("data-page-toc") < aside.index("How it works")
    assert "_page-toc.js" in html and "_page-toc.css" in html


@_page_mark
def test_the_filters_offer_only_what_the_viewer_may_see(app):
    outsider = factories.UserWithToken()
    secret_org, open_org = _org(), _org()
    _dataset(secret_org, title="Secret", private=True, tags=[{"name": "secret-tag"}])
    _dataset(open_org, title="Open", tags=[{"name": "open-tag"}])
    _dataset(_org(), title="Another open")
    html = _get(app, outsider, TODO)
    assert "open-tag" in html and "secret-tag" not in html
    assert f'value="{open_org["id"]}"' in html and f'value="{secret_org["id"]}"' not in html
    # A chosen organisation with nothing left stays chosen, with its name and a link that removes it.
    empty = _get(app, outsider, f"{TODO}?org={secret_org['id']}")
    chosen = empty.split("data-todo-chosen>")[1].split("</ul>")[0]
    assert "No datasets match the filters." in empty and f"Organization: {secret_org['title']}" in chosen


@_page_mark
def test_the_organisation_filter_is_offered_with_a_single_organisation(app):
    sysadmin = factories.SysadminWithToken()
    only = _org()
    _dataset(only, title="Alone")
    html = _get(app, sysadmin, TODO)
    assert 'id="todo-org"' in html and f'value="{only["id"]}"' in html
    # The title cell, not the n-th one, keeps its width: without a selection column it is the first.
    assert '<td class="todo-title">' in html


@_page_mark
def test_a_save_says_that_saved_datasets_may_leave_the_list(app, monkeypatch):
    # The API token used here keeps no session, so the message is caught where it is given.
    from ckan.plugins import toolkit
    notices = []
    monkeypatch.setattr(toolkit.h, "flash_notice", lambda message, *args, **kwargs: notices.append(message))
    sysadmin = factories.SysadminWithToken()
    board = _actor("City Board")
    dataset, other = _dataset(_org(), title="Bare"), _dataset(_org(), title="Other")
    leaves = "A dataset that no longer lacks what this list shows leaves it."
    for data in ({f"publisher_for_{dataset['id']}": board.id},
                 {"dataset_ids": [other["id"]], "publisher_actor_id_top": board.id}):
        notices.clear()
        app.post(TODO + "/assign", headers={"Authorization": sysadmin["token"]}, follow_redirects=False,
                 data=dict({"missing": "either", "page": "1", "assign_from": "top"}, **data))
        assert notices == [leaves]


@_page_mark
def test_the_registrys_own_links_show_the_contact_point_list_while_datasets_wait(app):
    sysadmin = factories.SysadminWithToken()
    desk = _contact_point("Desk")
    _deactivate(_contact_point("Old desk"))
    _dataset(_org(), title="Old contact", maintainer="Desk", maintainer_email="desk@example.org")
    headers = {"Authorization": sysadmin["token"]}
    # The box for inactive ones keeps the list (it sends list=1 along).
    listing = _get(app, sysadmin, "/contactpoints?list=1")
    assert '<input type="hidden" name="list" value="1"><label class="checkbox"><input type="checkbox" name="show_inactive"' in listing
    for query in ("?show_inactive=1", "?list=1&show_inactive=1"):
        assert app.get("/contactpoints" + query, headers=headers, follow_redirects=False).status_code == 200
    # After an edit, back to the list, not to the migration.
    response = app.post(f"/contactpoints/{desk.id}/edit", headers=headers, follow_redirects=False,
                        data={"name": "Desk", "email": "desk@example.org", "uri": desk.uri})
    assert response.status_code == 302 and response.headers["Location"].endswith("/contactpoints?list=1")
