import ckan.plugins.toolkit as toolkit
from ckan import model as ckan_model

from ckanext.actor_registry import model as registry_model
from ckanext.actor_registry import validation

# Fields that a merge can choose a value for. "uri" is deliberately excluded:
# the surviving actor's URI is its RDF identity and is never a merge choice
# (see aktorsregister-sammanslagning-plan.md, "Design: sammanslagning" #4).
MERGEABLE_FIELDS = (
    "name",
    "actor_kind",
    "actor_type",
    "identifier",
    "identifier_scheme",
    "url",
    "email",
    "description",
)


def actor_registry_actor_merge(context, data_dict):
    """Merge two actors: ``merge_id`` is soft-retired into ``keep_id``.

    data_dict:
      - keep_id (str, required): the actor id that survives the merge.
      - merge_id (str, required): the actor id being merged away.
      - fields (dict, optional): final field values to write onto the
        surviving actor, keyed by field name (see MERGEABLE_FIELDS). Any
        field not present keeps the surviving actor's current value.

    Effects (see aktorsregister-sammanslagning-plan.md, "Design:
    sammanslagning" #6, for the full rationale):
      - Chosen field values are written onto the surviving actor.
      - The merged actor's contact points move to the surviving actor
        (ContactPoint.actor_id).
      - Datasets that had the merged actor as publisher_actor_id are
        re-pointed via package_patch (this also re-indexes them).
      - Any UserPreference.publisher_actor_id pointing at the merged
        actor is re-pointed too.
      - The merged actor is soft-retired: active=False,
        merged_into_id=keep_id. It is never deleted.
    """
    toolkit.check_access("actor_registry_actor_merge", context, data_dict)

    keep_id = data_dict.get("keep_id")
    merge_id = data_dict.get("merge_id")
    fields = data_dict.get("fields") or {}

    errors = {}
    if not keep_id:
        errors["keep_id"] = [toolkit._("Required.")]
    if not merge_id:
        errors["merge_id"] = [toolkit._("Required.")]
    if keep_id and merge_id and keep_id == merge_id:
        errors["merge_id"] = [toolkit._("Cannot merge a publisher with itself.")]
    unknown_fields = sorted(set(fields) - set(MERGEABLE_FIELDS))
    if unknown_fields:
        errors["fields"] = [
            toolkit._("Unknown fields: {fields}").format(fields=", ".join(unknown_fields))
        ]
    if fields.get("name") == "":
        errors.setdefault("fields", []).append(toolkit._("Name cannot be empty."))
    if errors:
        raise toolkit.ValidationError(errors)

    keep = registry_model.get_actor(keep_id)
    merge = registry_model.get_actor(merge_id)
    if not keep or not keep.active:
        raise toolkit.ObjectNotFound(
            toolkit._("The publisher to keep was not found, or is already inactive.")
        )
    if not merge or not merge.active:
        raise toolkit.ObjectNotFound(
            toolkit._("The publisher to merge was not found, or is already inactive.")
        )

    # The chosen values are written onto the surviving publisher, so they must pass the same
    # rules as any other edit (format, length, and a unique identifier pair). Before this
    # check they were written unvalidated, and a clash with a third publisher's identifier
    # surfaced as a database error.
    fields = dict(fields)
    field_errors = validation.validate_actor(fields, existing=keep)
    problems = [message for messages in field_errors.values() for message in messages]
    if "identifier" in fields or "identifier_scheme" in fields:
        problem = validation.identifier_error(
            fields.get("identifier_scheme", keep.identifier_scheme or ""),
            fields.get("identifier", keep.identifier or ""),
            exclude_ids=(keep.id, merge.id),  # the merged publisher is retired by this very action
        )
        if problem:
            problems.append(problem)
    if problems:
        raise toolkit.ValidationError({"fields": problems})

    session = ckan_model.Session

    # Retire the merged actor and flush BEFORE writing the chosen field
    # values onto the survivor: the unique (identifier_scheme, identifier)
    # index covers active actors only, so the survivor may adopt the
    # merged actor's identifier only once that actor is no longer active.
    merge.active = False
    merge.merged_into_id = keep_id
    session.flush()

    for field_name in MERGEABLE_FIELDS:
        if field_name in fields:
            setattr(keep, field_name, fields[field_name])

    moved_contact_points = (
        session.query(registry_model.ContactPoint)
        .filter(registry_model.ContactPoint.actor_id == merge_id)
        .update({"actor_id": keep_id}, synchronize_session=False)
    )

    linked = registry_model.datasets_for_actor(merge_id)
    updated_dataset_ids = []
    for dataset_id in linked["publisher"]:
        toolkit.get_action("package_patch")(
            dict(context, ignore_auth=True),
            {"id": dataset_id, "publisher_actor_id": keep_id},
        )
        updated_dataset_ids.append(dataset_id)

    updated_preferences = (
        session.query(registry_model.UserPreference)
        .filter(registry_model.UserPreference.publisher_actor_id == merge_id)
        .update({"publisher_actor_id": keep_id}, synchronize_session=False)
    )

    session.add(keep)
    session.add(merge)
    session.commit()

    return {
        "keep_id": keep_id,
        "merge_id": merge_id,
        "moved_contact_points": moved_contact_points,
        "updated_datasets": updated_dataset_ids,
        "updated_user_preferences": updated_preferences,
    }


def actor_registry_actor_delete(context, data_dict):
    """Permanently delete an actor, active or merged/retired alike.

    data_dict:
      - id (str, required): the actor to delete.

    Unlike a merge, this is a real, irreversible delete -- there is no
    "merged_into_id" to fall back on afterwards. To avoid leaving dangling
    references behind:
      - Datasets that had this actor as ``publisher_actor_id`` are patched
        to clear that field (blank string, the same "no publisher set"
        representation ``datasets_without_actor_link()`` already checks
        for) via ``package_patch``.
      - Contact points owned by this actor (``ContactPoint.actor_id``) are
        NOT deleted -- they are decoupled (``actor_id`` set to ``None``)
        and become standalone contact points. Datasets referencing those
        contact points are unaffected, since the contact point record
        itself still exists.
      - Other actors whose ``merged_into_id`` points at this one are left
        alone here (the FK is ``ondelete=SET NULL``, so the delete itself
        can't fail because of them) -- the view layer surfaces this as an
        explicit warning before the sysadmin confirms, since their "merged
        with X" pointer will go stale once X is gone.

    See aktorsregister-sammanslagning-plan.md, decision 1, for why merges
    soft-retire instead of deleting: a merged actor's URI may already be
    referenced or cached outside this catalogue, and keeping the retired
    record lets that URI keep resolving (to a clear "merged with X"
    pointer) instead of 404ing. Deleting an actor -- especially an already-
    merged one -- gives that up for good, which is exactly why this action
    is sysadmin-only and the view requires an explicit confirmation step
    that spells out what will break.
    """
    toolkit.check_access("actor_registry_actor_delete", context, data_dict)

    actor_id = data_dict.get("id")
    if not actor_id:
        raise toolkit.ValidationError({"id": [toolkit._("Required.")]})

    actor = registry_model.get_actor(actor_id)
    if not actor:
        raise toolkit.ObjectNotFound(toolkit._("The publisher was not found."))

    session = ckan_model.Session
    name = actor.name

    linked = registry_model.datasets_for_actor(actor_id)
    cleared_dataset_ids = []
    for dataset_id in linked["publisher"]:
        toolkit.get_action("package_patch")(
            dict(context, ignore_auth=True),
            {"id": dataset_id, "publisher_actor_id": ""},
        )
        cleared_dataset_ids.append(dataset_id)

    decoupled_contact_points = (
        session.query(registry_model.ContactPoint)
        .filter(registry_model.ContactPoint.actor_id == actor_id)
        .update({"actor_id": None}, synchronize_session=False)
    )

    stale_redirects = len(registry_model.actors_merged_into(actor_id))

    session.delete(actor)
    session.commit()

    return {
        "id": actor_id,
        "name": name,
        "cleared_publisher_datasets": cleared_dataset_ids,
        "decoupled_contact_points": decoupled_contact_points,
        "stale_merge_redirects": stale_redirects,
    }


def actor_registry_contactpoint_delete(context, data_dict):
    """Permanently delete a contact point, active or inactive alike.

    data_dict:
      - id (str, required): the contact point to delete.

    Contact points have no merge/soft-retire concept of their own (that's
    an actors-only feature) -- "inactive" here just means someone
    deactivated it via the edit form. Deleting it is a real, irreversible
    delete either way:
      - Datasets that listed this contact point in ``contact_point_ids``
        are patched to drop just this id from that list (the field is a
        multi-select; other contact points on the same dataset are left
        alone).
      - ``RecentContactPoint`` rows referencing it are removed
        automatically by the database (``ondelete=CASCADE``) -- nothing to
        do here.
      - If it belongs to an actor (``actor_id`` set), that actor is
        unaffected; only this contact point goes away.

    Sysadmin-only, same rationale as actor deletion: a contact point's URI
    may already be referenced or cached outside this catalogue, so giving
    that up is a deliberate, explicit action rather than an automatic
    side effect of deactivating it.
    """
    toolkit.check_access("actor_registry_contactpoint_delete", context, data_dict)

    contact_point_id = data_dict.get("id")
    if not contact_point_id:
        raise toolkit.ValidationError({"id": [toolkit._("Required.")]})

    contact_point = registry_model.get_contact_point(contact_point_id)
    if not contact_point:
        raise toolkit.ObjectNotFound(toolkit._("The contact point was not found."))

    session = ckan_model.Session
    name = contact_point.name

    linked_dataset_ids = registry_model.datasets_for_contact_point(contact_point_id)
    updated_dataset_ids = []
    for dataset_id in linked_dataset_ids:
        pkg = toolkit.get_action("package_show")(dict(context, ignore_auth=True), {"id": dataset_id})
        current_ids = pkg.get("contact_point_ids") or []
        if isinstance(current_ids, str):
            current_ids = [current_ids] if current_ids else []
        remaining_ids = [cid for cid in current_ids if cid != contact_point_id]
        toolkit.get_action("package_patch")(
            dict(context, ignore_auth=True),
            {"id": dataset_id, "contact_point_ids": remaining_ids},
        )
        updated_dataset_ids.append(dataset_id)

    session.delete(contact_point)
    session.commit()

    return {
        "id": contact_point_id,
        "name": name,
        "updated_datasets": updated_dataset_ids,
    }
