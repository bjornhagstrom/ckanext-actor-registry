import ckan.plugins.toolkit as toolkit


def actor_registry_actor_merge(context, data_dict):
    """Sysadmin-only. CKAN's check_access() lets sysadmins bypass auth
    functions entirely, so unconditionally denying here (the standard CKAN
    idiom for sysadmin-only actions) is sufficient -- a sysadmin never
    actually reaches this function."""
    return {
        "success": False,
        "msg": toolkit._("Only sysadmins can merge publishers."),
    }


def actor_registry_actor_delete(context, data_dict):
    """Sysadmin-only, same idiom as actor_registry_actor_merge above --
    deleting an actor is at least as destructive (irreversible, unlike a
    merge) and can affect datasets across the whole catalogue."""
    return {
        "success": False,
        "msg": toolkit._("Only sysadmins can delete publishers."),
    }


def actor_registry_contactpoint_delete(context, data_dict):
    """Sysadmin-only, same idiom and same rationale as
    actor_registry_actor_delete above."""
    return {
        "success": False,
        "msg": toolkit._("Only sysadmins can delete contact points."),
    }
