from core_data.capabilities import ALL_CAPABILITIES
from .models import AccessChange


def access_snapshot(profile):
    data = {name: getattr(profile, name) for name in ALL_CAPABILITIES}
    data["revision"] = profile.revision
    if hasattr(profile, "allowed_sites"):
        data["allowed_sites"] = list(profile.allowed_sites.order_by("pk").values_list("pk", flat=True))
        data["allowed_studios"] = list(profile.allowed_studios.order_by("pk").values_list("pk", flat=True))
    return data


def log_access_change(actor, profile, operation, before, after):
    is_group = hasattr(profile, "group_id")
    target = profile.group if is_group else profile.user
    AccessChange.objects.create(actor=actor, target_type="group" if is_group else "user",
                                target_id=target.pk, target_label=str(target)[:180], operation=operation,
                                before=before, after=after)


def user_access_snapshot(user):
    return {"groups": list(user.groups.order_by("pk").values_list("pk", flat=True)),
            "is_active": user.is_active, "is_staff": user.is_staff, "is_superuser": user.is_superuser}


def log_user_access_change(actor, user, operation, before, after):
    if before != after:
        AccessChange.objects.create(actor=actor, target_type="user_membership", target_id=user.pk,
                                    target_label=str(user)[:180], operation=operation, before=before, after=after)
