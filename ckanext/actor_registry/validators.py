"""CKAN validators for dataset fields that reference registry records.

Schemas opt in per field, e.g. in a scheming schema::

    - field_name: publisher_actor_id
      validators: not_empty actor_registry_actor_exists
    - field_name: contact_point_ids
      validators: ignore_missing scheming_multiple_text actor_registry_contactpoints_exist

They guarantee a dataset can only point at records that exist and are
active, whatever form or API call the value came from.
"""

import ckan.plugins.toolkit as toolkit

from ckanext.actor_registry import helpers, model


def actor_registry_actor_exists(value, context):
    """The publisher must exist; a new one must also be active.

    A publisher that is already on the dataset may stay when it has been
    deactivated, as for contact points below. Messages name the publisher.
    """
    if value in (None, "", toolkit.missing):
        return value
    package = context.get("package") if context else None
    stored = package.extras.get("publisher_actor_id") if package is not None else None
    actor = model.get_actor(value)
    if not actor:
        raise toolkit.Invalid(toolkit._(
            "The selected publisher no longer exists (id {id}). Choose another publisher."
        ).format(id=value))
    if not actor.active and value != stored:
        raise toolkit.Invalid(toolkit._(
            "The publisher “{name}” is inactive and can no longer be chosen. "
            "Choose an active publisher."
        ).format(name=actor.name))
    return value


def actor_registry_contactpoints_exist(value, context):
    """Every contact point must exist; a new one must also be active.

    A contact point that is already on the dataset may stay when it has been
    deactivated: deactivating is meant to stop new use, not to lock the
    datasets that use it. Messages name the contact point so an editor can
    find it in the form.
    """
    if value in (None, "", toolkit.missing):
        return value
    package = context.get("package") if context else None
    stored = set(helpers._id_list(package.extras.get("contact_point_ids"))) if package is not None else set()
    for contact_id in helpers._id_list(value):
        item = model.get_contact_point(contact_id)
        if not item:
            raise toolkit.Invalid(toolkit._(
                "A selected contact point no longer exists (id {id}). Remove it from the list."
            ).format(id=contact_id))
        if not item.active and contact_id not in stored:
            raise toolkit.Invalid(toolkit._(
                "The contact point “{name}” is inactive and can no longer be chosen. "
                "Choose an active contact point."
            ).format(name=item.name))
    return value
    return value
