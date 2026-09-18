import ckan.plugins.toolkit as toolkit
from ckan import model as ckan_model

from ckanext.actor_registry import model as registry_model

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
        errors["merge_id"] = [toolkit._("Cannot merge an actor with itself.")]
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
            toolkit._("The actor to keep was not found, or is already inactive.")
        )
    if not merge or not merge.active:
        raise toolkit.ObjectNotFound(
            toolkit._("The actor to merge was not found, or is already inactive.")
        )

    session = ckan_model.Session

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

    merge.active = False
    merge.merged_into_id = keep_id

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
