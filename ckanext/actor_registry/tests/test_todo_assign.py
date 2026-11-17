"""Setting a publisher and a contact point from the To do list: each row's own choices and the bar's choices on the
ticked rows, all with one Save (0.6.0)."""

import pytest

from ckan.tests import factories, helpers

from ckanext.actor_registry import cleanup
from ckanext.actor_registry.tests.test_cleanup import _actor, _deactivate, _show
from ckanext.actor_registry.tests.test_contact_migration import (
    _contact_point, _dataset, _get, _mark, _org, _page_mark)

TODO = "/actor-registry/todo"


def _post(app, user, status=None, **data):
    return app.post(TODO + "/assign", headers={"Authorization": user["token"]},
                    data=dict({"missing": "either", "page": "1"}, **data), follow_redirects=False,
                    **({"status": status} if status else {}))


@_mark
def test_assign_sets_only_what_is_missing_and_only_where_it_may():
    editor = factories.User()
    own, other = _org(users=[(editor, "editor")]), _org()
    board, existing = _actor("City Board"), _actor("Existing")
    desk, kept = _contact_point("Desk"), _contact_point("Kept")
    bare = _dataset(own, title="Bare")
    has_publisher = _dataset(own, title="Has publisher", publisher_actor_id=existing.id)
    has_contact = _dataset(own, title="Has contact", contact_point_ids=[kept.id])
    theirs = _dataset(other, title="Theirs")
    result = cleanup.assign(editor["name"], [bare["id"], has_publisher["id"], has_contact["id"],
                                             theirs["id"], bare["id"]], board.id, desk.id)
    titles = {kind: sorted(item["title"] for item in items) for kind, items in result["changed"].items()}
    assert titles == {"publisher": ["Bare", "Has contact"], "contact_point": ["Bare", "Has publisher"]}
    assert [item["title"] for item in result["skipped"]["publisher"]] == ["Has publisher"]
    assert [item["title"] for item in result["skipped"]["contact_point"]] == ["Has contact"]
    assert [title for title, _message in result["failures"]] == ["Theirs"]
    assert _show(bare)["publisher_actor_id"] == board.id and _show(bare)["contact_point_ids"] == [desk.id]
    assert _show(has_publisher)["publisher_actor_id"] == existing.id
    assert _show(has_publisher)["contact_point_ids"] == [desk.id]
    assert _show(has_contact)["contact_point_ids"] == [kept.id]
    assert not _show(theirs).get("publisher_actor_id") and not _show(theirs).get("contact_point_ids")


@_mark
@pytest.mark.parametrize("case", ["inactive", "missing", "inactive_contact", "missing_contact", "nothing", "no_datasets"])
def test_invalid_assignments_change_nothing(case):
    sysadmin = factories.Sysadmin()
    board, desk = _actor("City Board"), _contact_point("Desk")
    dataset = _dataset(_org())
    actor_id, contact_id, ids = board.id, desk.id, [dataset["id"]]
    if case == "inactive":
        _deactivate(board)
    elif case == "missing":
        actor_id = "gone"
    elif case == "inactive_contact":
        _deactivate(desk)
    elif case == "missing_contact":
        contact_id = "gone"
    elif case == "nothing":
        actor_id = contact_id = ""
    elif case == "no_datasets":
        ids = ["", ""]
    with pytest.raises(cleanup.CleanupError):
        cleanup.assign(sysadmin["name"], ids, actor_id, contact_id)
    assert not _show(dataset).get("publisher_actor_id") and not _show(dataset).get("contact_point_ids")


@_page_mark
def test_the_bar_is_above_and_below_the_list_and_each_row_has_its_own_choices_and_no_save_of_its_own(app):
    sysadmin = factories.SysadminWithToken()
    board, desk = _actor("City Board"), _contact_point("Desk", email="desk@example.org")
    dataset = _dataset(_org(), title="Bare")
    html = _get(app, sysadmin, TODO)
    for where in ("top", "bottom"):
        assert f'name="publisher_actor_id_{where}"' in html and f'name="contact_point_id_{where}"' in html
    assert html.index('name="publisher_actor_id_top"') < html.index(f'value="{dataset["id"]}"') \
        < html.index('name="publisher_actor_id_bottom"')
    assert html.count("data-assign-all-wrap") == 2
    assert f'name="publisher_for_{dataset["id"]}"' in html and f'name="contact_point_for_{dataset["id"]}"' in html
    assert f'name="assign_from" value="{dataset["id"]}"' not in html
    assert 'name="assign_from" value="top"' in html and 'name="assign_from" value="bottom"' in html
    assert html.count(f'<option value="{board.id}">City Board</option>') == 3
    assert html.count(f'<option value="{desk.id}">Desk (desk@example.org)</option>') == 3
    # Leaving with something unsaved asks (assign-links.js), with the texts from the page; nothing is lost on a save.
    assert "data-i18n-lost" not in html and "{details}" in html and 'data-i18n-chosen-many="{count} rows with a choice"' in html


@_page_mark
def test_one_save_sets_every_rows_own_choices_and_the_bars_on_the_ticked_rows(app):
    sysadmin = factories.SysadminWithToken()
    board, other, desk = _actor("City Board"), _actor("Other"), _contact_point("Desk")
    row, ticked, both, left = (_dataset(_org(), title=title) for title in ("Row", "Ticked", "Both", "Left"))
    response = _post(app, sysadmin, assign_from="top", dataset_ids=[ticked["id"], both["id"]], **{
        f"publisher_for_{row['id']}": board.id, f"contact_point_for_{row['id']}": desk.id,
        f"publisher_for_{both['id']}": board.id,
        "publisher_actor_id_top": other.id, "contact_point_id_top": desk.id})
    assert response.status_code == 302
    assert response.headers["Location"].endswith(TODO + "?missing=either&page=1#todo-list")
    assert _show(row)["publisher_actor_id"] == board.id and _show(row)["contact_point_ids"] == [desk.id]
    assert _show(ticked)["publisher_actor_id"] == other.id and _show(ticked)["contact_point_ids"] == [desk.id]
    # A row's own choice comes first; what it did not choose comes from the bar.
    assert _show(both)["publisher_actor_id"] == board.id and _show(both)["contact_point_ids"] == [desk.id]
    assert not _show(left).get("publisher_actor_id")


@_page_mark
def test_a_ticked_row_with_its_own_choice_is_saved_with_nothing_in_the_bar(app):
    # Björn's test, 2026-11-17: two rows ticked, a contact point chosen on one, Save: nothing was saved.
    sysadmin = factories.SysadminWithToken()
    desk = _contact_point("Desk")
    chosen, plain = _dataset(_org(), title="Chosen"), _dataset(_org(), title="Plain")
    _post(app, sysadmin, assign_from="top", dataset_ids=[chosen["id"], plain["id"]],
          **{f"contact_point_for_{chosen['id']}": desk.id})
    assert _show(chosen)["contact_point_ids"] == [desk.id] and not _show(plain).get("contact_point_ids")


@_page_mark
@pytest.mark.parametrize("where", ["top", "bottom"])
def test_the_pressed_bar_counts_and_the_other_only_when_it_is_empty(app, where):
    sysadmin = factories.SysadminWithToken()
    board, other, desk = _actor("City Board"), _actor("Other"), _contact_point("Desk")
    first, second = (_dataset(_org(), title=title) for title in ("First", "Second"))
    other_bar = "bottom" if where == "top" else "top"
    # Without JavaScript the bars are not kept in step: the pressed one wins, the other fills what it lacks.
    _post(app, sysadmin, assign_from=where, dataset_ids=[first["id"], second["id"]], **{
        f"publisher_actor_id_{where}": board.id, f"publisher_actor_id_{other_bar}": other.id,
        f"contact_point_id_{other_bar}": desk.id})
    for dataset in (first, second):
        assert _show(dataset)["publisher_actor_id"] == board.id and _show(dataset)["contact_point_ids"] == [desk.id]


@_page_mark
def test_only_a_contact_point_can_be_set_too(app):
    sysadmin = factories.SysadminWithToken()
    desk = _contact_point("Desk")
    dataset = _dataset(_org(), title="Bare")
    _post(app, sysadmin, assign_from="top", **{f"contact_point_for_{dataset['id']}": desk.id})
    assert _show(dataset)["contact_point_ids"] == [desk.id] and not _show(dataset).get("publisher_actor_id")


@_page_mark
@pytest.mark.parametrize("ticked", [False, True])
def test_a_save_without_a_choice_changes_nothing_and_says_what_to_do(app, monkeypatch, ticked):
    from ckan.plugins import toolkit
    errors = []
    monkeypatch.setattr(toolkit.h, "flash_error", lambda message, *args, **kwargs: errors.append(message))
    sysadmin = factories.SysadminWithToken()
    _actor("City Board")
    row = _dataset(_org(), title="Row")
    assert _post(app, sysadmin, assign_from="top", **({"dataset_ids": [row["id"]]} if ticked else {})).status_code == 302
    assert not _show(row).get("publisher_actor_id")
    assert errors == ["Choose in the box what the selected datasets should get." if ticked else
                      "Nothing to save. Choose on a row, or select datasets and choose in the box."]


@_page_mark
def test_the_messages_count_per_publisher_and_say_what_got_nothing(app, monkeypatch):
    from ckan.plugins import toolkit
    said = []
    monkeypatch.setattr(toolkit.h, "flash_success", lambda message, *args, **kwargs: said.append(message))
    monkeypatch.setattr(toolkit.h, "flash_notice", lambda message, *args, **kwargs: said.append(message))
    sysadmin = factories.SysadminWithToken()
    board, desk = _actor("City Board"), _contact_point("Desk")
    one, two, three = (_dataset(_org(), title=title) for title in ("One", "Two", "Three"))
    # One gets the board and the desk, Two only the board (saved in two groups): the board is counted once, for both.
    _post(app, sysadmin, assign_from="top", dataset_ids=[three["id"]], **{
        f"publisher_for_{one['id']}": board.id, f"contact_point_for_{one['id']}": desk.id,
        f"publisher_for_{two['id']}": board.id})
    assert said == ["City Board is now the publisher of 2 datasets.", "Desk is now the contact point of 1 dataset.",
                    "A dataset that no longer lacks what this list shows leaves it.",
                    "1 selected dataset got nothing: nothing was chosen in the box."]


@_page_mark
def test_an_editor_can_only_set_on_their_own_datasets(app):
    editor = factories.UserWithToken()
    own = _org(users=[(editor, "editor")])
    _actor("City Board")
    mine, theirs = _dataset(own, title="Mine"), _dataset(_org(), title="Theirs")
    html = _get(app, editor, TODO)
    assert f'name="dataset_ids" value="{mine["id"]}"' in html
    assert "Theirs" in html and f'value="{theirs["id"]}"' not in html


@_page_mark
def test_a_member_who_cannot_edit_gets_no_form_and_cannot_post(app):
    member = factories.UserWithToken()
    org = _org(users=[(member, "member")])
    board = _actor("City Board")
    dataset = _dataset(org)
    assert "data-assign-links" not in _get(app, member, TODO)
    _post(app, member, status=403, assign_from=dataset["id"], **{f"publisher_for_{dataset['id']}": board.id})
    assert not _show(dataset).get("publisher_actor_id")


@_page_mark
def test_the_menu_shows_how_many_wait(app):
    sysadmin = factories.SysadminWithToken()
    for title in ("One", "Two"):
        _dataset(_org(), title=title)
    html = _get(app, sysadmin, "/actors")
    assert TODO in html and 'data-nav-count>2</span>' in html


@_page_mark
def test_an_editors_number_counts_only_what_they_may_edit(app):
    editor = factories.UserWithToken()
    _dataset(_org(users=[(editor, "editor")]), title="Mine")
    other = _org()
    for title in ("Theirs", "Theirs too"):
        _dataset(other, title=title)
    html = _get(app, editor, TODO)
    assert 'data-nav-count>1</span>' in html and "Theirs too" in html  # listed, but not counted


@_mark
def test_a_kind_its_type_lacks_is_reported_and_the_other_still_set(monkeypatch):
    sysadmin = factories.Sysadmin()
    board, desk = _actor("City Board"), _contact_point("Desk")
    dataset = _dataset(_org(), title="Contacts only")
    monkeypatch.setattr(cleanup, "publisher_types", lambda: {"some-other-type"})
    result = cleanup.assign(sysadmin["name"], [dataset["id"]], board.id, desk.id)
    assert [item["title"] for item in result["changed"]["contact_point"]] == ["Contacts only"]
    assert result["failures"] == [("Contacts only", "This kind of dataset has no publisher field.")]
    assert _show(dataset)["contact_point_ids"] == [desk.id] and not _show(dataset).get("publisher_actor_id")


@_mark
def test_a_dataset_type_without_the_field_is_left_alone(monkeypatch):
    sysadmin = factories.Sysadmin()
    board = _actor("City Board")
    dataset = _dataset(_org(), title="Other kind")
    monkeypatch.setattr(cleanup, "publisher_types", lambda: {"some-other-type"})
    result = cleanup.assign(sysadmin["name"], [dataset["id"]], board.id)
    assert result["changed"]["publisher"] == [] and [title for title, _message in result["failures"]] == ["Other kind"]
    assert not _show(dataset).get("publisher_actor_id")


def _with_hook(monkeypatch, action_name, hook):
    """Run ``hook(action, context, data_dict)`` in place of one CKAN action as cleanup.py calls it."""
    real_get_action = cleanup.toolkit.get_action

    def get_action(name):
        action = real_get_action(name)
        if name != action_name:
            return action
        return lambda context, data_dict: hook(action, context, data_dict)
    monkeypatch.setattr(cleanup.toolkit, "get_action", get_action)


@_mark
@pytest.mark.parametrize("kind", ["publisher", "contact_point"])
def test_a_link_saved_by_someone_else_after_the_read_is_not_overwritten(monkeypatch, kind):
    sysadmin = factories.Sysadmin()
    mine, theirs = _actor("Mine"), _actor("Theirs")
    my_desk, their_desk = _contact_point("Mine"), _contact_point("Theirs")
    dataset = _dataset(_org(), title="Raced")
    saved = {"publisher_actor_id": theirs.id} if kind == "publisher" else {"contact_point_ids": [their_desk.id]}

    def show_then_someone_saves(action, context, data_dict):
        result = action(context, data_dict)  # what this page read: nothing set yet
        helpers.call_action("package_patch", context={"user": sysadmin["name"]}, id=dataset["id"], **saved)
        return result
    _with_hook(monkeypatch, "package_show", show_then_someone_saves)
    result = cleanup.assign(sysadmin["name"], [dataset["id"]], mine.id if kind == "publisher" else "",
                            my_desk.id if kind == "contact_point" else "")
    assert result["changed"][kind] == [] and [item["title"] for item in result["skipped"][kind]] == ["Raced"]
    for field, value in saved.items():
        assert _show(dataset)[field] == value


@_mark
def test_the_dataset_row_is_locked_while_the_links_are_saved(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    from ckan import model as ckan_model
    sysadmin = factories.Sysadmin()
    board = _actor("City Board")
    dataset = _dataset(_org(), title="Locked")
    seen = {}

    def patch_while_another_connection_tries(action, context, data_dict):
        with ckan_model.meta.engine.connect() as other:
            try:
                other.execute(text("SELECT id FROM package WHERE id = :id FOR UPDATE NOWAIT"), {"id": dataset["id"]})
                seen["locked"] = False
            except OperationalError:
                seen["locked"] = True
        return action(context, data_dict)
    _with_hook(monkeypatch, "package_patch", patch_while_another_connection_tries)
    result = cleanup.assign(sysadmin["name"], [dataset["id"]], board.id)
    assert seen == {"locked": True}
    assert [item["id"] for item in result["changed"]["publisher"]] == [dataset["id"]] and result["failures"] == []
    assert _show(dataset)["publisher_actor_id"] == board.id


@_page_mark
def test_an_editor_cannot_set_a_rows_choice_on_another_organisations_dataset(app, monkeypatch):
    from ckan.plugins import toolkit
    errors = []
    monkeypatch.setattr(toolkit.h, "flash_error", lambda message, *args, **kwargs: errors.append(message))
    editor = factories.UserWithToken()
    _org(users=[(editor, "editor")])
    board = _actor("City Board")
    theirs = _dataset(_org(), title="Theirs")
    _post(app, editor, assign_from="top", **{f"publisher_for_{theirs['id']}": board.id})
    assert not _show(theirs).get("publisher_actor_id")
    assert errors and all("Theirs" in message for message in errors)


@_page_mark
def test_the_messages_are_shown_at_the_list_not_at_the_top(app, monkeypatch):
    from ckan.lib import helpers as core_helpers
    monkeypatch.setitem(core_helpers.helper_functions, "get_flashed_messages",
                        lambda **kwargs: [("alert-success", "City Board is now the publisher of 1 dataset.")])
    sysadmin = factories.SysadminWithToken()
    _actor("City Board")
    _dataset(_org(), title="Bare")
    html = _get(app, sysadmin, TODO)
    at_list = html.split("data-todo-messages>")[1].split("</div>\n<h2>")[0]
    assert "City Board is now the publisher of 1 dataset." in at_list and 'role="alert"' in at_list
    top = html.split('<div class="flash-messages">')[1].split("</div>")[0]
    assert "City Board is now" not in top
