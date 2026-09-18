import ckan.plugins.toolkit as toolkit


def actor_registry_actor_merge(context, data_dict):
    """Sysadmin-only. CKAN's check_access() lets sysadmins bypass auth
    functions entirely, so unconditionally denying here (the standard CKAN
    idiom for sysadmin-only actions) is sufficient -- a sysadmin never
    actually reaches this function."""
    return {
        "success": False,
        "msg": toolkit._("Only sysadmins can merge actors."),
    }
