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


def actor_registry_actor_exists(value):
    if value in (None, "", toolkit.missing):
        return value
    actor = model.get_actor(value)
    if not actor or not actor.active:
        raise toolkit.Invalid(toolkit._("The selected publisher does not exist or is no longer active."))
    return value


def actor_registry_contactpoints_exist(value):
    if value in (None, "", toolkit.missing):
        return value
    ids = helpers._id_list(value)
    for contact_id in ids:
        item = model.get_contact_point(contact_id)
        if not item or not item.active:
            raise toolkit.Invalid(
                toolkit._("A selected contact point does not exist or is no longer active.")
            )
    return value
