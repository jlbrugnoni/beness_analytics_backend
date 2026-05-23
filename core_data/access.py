from django.db.models import Q

from .models import GroupAccessProfile, UserAccessProfile


ACCESS_CAPABILITIES = [
    "can_view_money",
    "can_upload_data",
    "can_edit_data",
    "can_reset_data",
    "can_manage_users",
    "can_view_admin_logs",
]


DEFAULT_GROUP_CAPABILITIES = {
    "Admin": {
        "can_view_money": True,
        "can_upload_data": True,
        "can_edit_data": True,
        "can_reset_data": True,
        "can_manage_users": True,
        "can_view_admin_logs": True,
    },
    "Manager": {
        "can_view_money": True,
    },
    "Data Operator": {
        "can_upload_data": True,
        "can_edit_data": True,
    },
    "Studio Manager": {},
    "Viewer": {},
}


def capability_payload(**overrides):
    payload = {capability: False for capability in ACCESS_CAPABILITIES}
    payload.update(overrides)
    return payload


def default_capabilities_for_group(group):
    return capability_payload(**DEFAULT_GROUP_CAPABILITIES.get(group.name, {}))


def get_or_create_user_access_profile(user):
    profile, _ = UserAccessProfile.objects.get_or_create(user=user)
    return profile


def group_capabilities(group):
    try:
        profile = group.access_profile
    except GroupAccessProfile.DoesNotExist:
        return default_capabilities_for_group(group)
    return capability_payload(**{
        capability: getattr(profile, capability)
        for capability in ACCESS_CAPABILITIES
    })


def user_has_global_access(user):
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name="Admin").exists()


def resolve_access_payload(user):
    groups = list(user.groups.all().order_by("name"))
    profile = get_or_create_user_access_profile(user)
    capabilities = capability_payload()

    if user_has_global_access(user):
        capabilities = capability_payload(**{capability: True for capability in ACCESS_CAPABILITIES})
    else:
        for group in groups:
            group_payload = group_capabilities(group)
            for capability in ACCESS_CAPABILITIES:
                capabilities[capability] = capabilities[capability] or group_payload[capability]
        for capability in ACCESS_CAPABILITIES:
            capabilities[capability] = capabilities[capability] or getattr(profile, capability)

    allowed_studios = list(profile.allowed_studios.select_related("site").all().order_by("site__name", "name"))
    allowed_site_ids = set(profile.allowed_sites.values_list("id", flat=True))
    allowed_site_ids.update(studio.site_id for studio in allowed_studios if studio.site_id)
    allowed_sites = list(profile.allowed_sites.model.objects.filter(id__in=allowed_site_ids).order_by("name"))

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
        },
        "groups": [{"id": group.id, "name": group.name} for group in groups],
        "capabilities": capabilities,
        "allowed_sites": [{"id": site.id, "name": site.name} for site in allowed_sites],
        "allowed_studios": [
            {
                "id": studio.id,
                "name": studio.name,
                "site": studio.site_id,
                "site_name": studio.site.name if studio.site else None,
            }
            for studio in allowed_studios
        ],
        "has_global_access": user_has_global_access(user),
        "django_permissions": list(user.get_all_permissions()),
    }


def user_has_capability(user, capability):
    if capability not in ACCESS_CAPABILITIES:
        return False
    if user_has_global_access(user):
        return True
    profile = get_or_create_user_access_profile(user)
    if getattr(profile, capability):
        return True
    return any(group_capabilities(group)[capability] for group in user.groups.all())


def scoped_queryset_for_user(queryset, user, site_field="site_id", studio_field=None, include_null_studio=False):
    if user_has_global_access(user):
        return queryset
    profile = get_or_create_user_access_profile(user)
    studio_ids = list(profile.allowed_studios.values_list("id", flat=True))
    site_ids = set(profile.allowed_sites.values_list("id", flat=True))
    site_ids.update(profile.allowed_studios.values_list("site_id", flat=True))

    if studio_field and studio_ids:
        studio_filter = Q(**{f"{studio_field}__in": studio_ids})
        if include_null_studio and site_ids:
            studio_filter |= Q(**{f"{studio_field}__isnull": True, f"{site_field}__in": list(site_ids)})
        return queryset.filter(studio_filter)
    if site_ids:
        return queryset.filter(**{f"{site_field}__in": list(site_ids)})
    return queryset.none()
