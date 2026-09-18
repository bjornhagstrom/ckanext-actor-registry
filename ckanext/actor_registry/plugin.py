import os

import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckan import model as ckan_model

from ckanext.actor_registry import actions, auth, helpers, model, views


class ActorRegistryPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.ITranslation)

    def update_config(self, config):
        toolkit.add_template_directory(config, "templates")
        toolkit.add_resource("assets", "actor_registry")

    # ITranslation -- same mechanism ckanext-skelleftea already uses
    # (gettext/.po/.mo catalog compiled via pybabel, see
    # docs/I18N_PLAN.md). Unlike skelleftea's catalog (a small, hand-
    # written override of CKAN core's own English vocabulary),
    # actor_registry's own templates/Python had zero _() markers before
    # this, so its catalog is a real pybabel-extracted one: English is
    # the source language here, Swedish is the compiled translation.
    def i18n_directory(self):
        return os.path.join(os.path.dirname(__file__), "i18n")

    def i18n_locales(self):
        return ["sv"]

    def i18n_domain(self):
        return "ckanext-actor-registry"

    def get_blueprint(self):
        return views.blueprint

    def get_helpers(self):
        return {
            "contactpoints_choices": helpers.contactpoints_choices,
            "contactpoints_resolve": helpers.contactpoints_resolve,
            "contactpoints_tel_uri": helpers.contactpoints_tel_uri,
            "contactpoints_grouped_choices": helpers.contactpoints_grouped_choices,
            "actors_choices": helpers.actors_choices,
            "actors_resolve": helpers.actors_resolve,
            "preferred_publisher_actor_id": helpers.preferred_publisher_actor_id,
        }

    def get_actions(self):
        return {
            "actor_registry_actor_merge": actions.actor_registry_actor_merge,
        }

    def get_auth_functions(self):
        return {
            "actor_registry_actor_merge": auth.actor_registry_actor_merge,
        }

    def _remember_user_choices(self, context, pkg_dict):
        actor_id = pkg_dict.get("publisher_actor_id")
        user = context.get("auth_user_obj")
        if user is None and context.get("user"):
            user = ckan_model.User.get(context["user"])
        user_id = getattr(user, "id", None)
        model.remember_publisher(user_id, actor_id)
        model.remember_contact_points(user_id, pkg_dict.get("contact_point_ids"))

    def after_dataset_create(self, context, pkg_dict):
        self._remember_user_choices(context, pkg_dict)

    def after_dataset_update(self, context, pkg_dict):
        self._remember_user_choices(context, pkg_dict)

    # NOTE: this used to also inject "contact"/"publisher" vcard/foaf-shaped
    # dicts into pkg_dict here, for ckanext-dcat's RDF profile to consume.
    # That was wrong: after_dataset_show runs on *every* package_show call,
    # and CKAN's own dataset views reuse that same pkg_dict as the base data
    # for later actions -- most notably the multi-step "add resource" wizard
    # for a dataset still in draft state, which re-validates the *whole*
    # package (existing pkg_dict + the new resource) against the active
    # scheming schema. Since "contact"/"publisher" aren't declared fields in
    # dcat_ap_se.yaml (we use contact_point_ids/publisher_actor_id instead),
    # every dataset that actually has a contact point or publisher assigned
    # would fail to save a new resource with a spurious
    # "__junk: ... was not expected" validation error.
    # The RDF-shaped dicts are only ever needed at RDF-serialization time, so
    # they're now computed locally in profiles.py's graph_from_dataset
    # instead of being written back into the shared pkg_dict here.
