from django.db import transaction
from rest_framework.exceptions import APIException, PermissionDenied

from .access import default_capabilities_for_group


def save_access_profile(serializer, actor):
    """Serialize permission edits and their audit record in one transaction."""
    from finance.audit import access_snapshot, log_access_change
    with transaction.atomic():
        expected = serializer.validated_data.pop("expected_revision", None)
        if serializer.instance:
            profile = type(serializer.instance).objects.select_for_update().get(pk=serializer.instance.pk)
            if hasattr(profile, "user") and profile.user.is_superuser and not actor.is_superuser:
                raise PermissionDenied("Only a superuser can edit a superuser's access profile.")
            if expected is not None and expected != profile.revision:
                error = APIException("Access changed since this form was loaded. Reload before saving.")
                error.status_code = 409
                raise error
            before = access_snapshot(profile)
            serializer.instance = profile
            profile = serializer.save(revision=profile.revision + 1)
            operation = "update"
        else:
            if "group" in serializer.validated_data:
                for key, value in default_capabilities_for_group(serializer.validated_data["group"]).items():
                    serializer.validated_data.setdefault(key, value)
            profile = serializer.save()
            before, operation = {}, "create"
        log_access_change(actor, profile, operation, before, access_snapshot(profile))
        return profile


def save_user_profile(user, data, request):
    from .models import UserAccessProfile
    from .serializers import UserAccessProfileSerializer
    profile = UserAccessProfile.objects.filter(user=user).first()
    if not isinstance(data, dict):
        from rest_framework.exceptions import ValidationError
        raise ValidationError({"access_profile": "Expected an object."})
    serializer = UserAccessProfileSerializer(profile, data={**data, "user": user.pk},
                                             partial=profile is not None, context={"request": request})
    serializer.is_valid(raise_exception=True)
    return save_access_profile(serializer, request.user)
