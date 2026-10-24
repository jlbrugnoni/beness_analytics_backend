from django.db import IntegrityError, transaction
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .access import can_use_finance
from .models import ConfigurationChange
from .permissions import FinancePermission


class ConfigurationConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Configuration changed. Reload and review before saving."


class ConfigurationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, FinancePermission]
    # Archive through active=False; financial configuration is never hard-deleted.
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def check_write_access(self):
        if not can_use_finance(self.request.user, "can_manage_finance_settings"):
            raise PermissionDenied("Financial configuration permission is required.")

    def authorize_values(self, serializer):
        pass

    def get_write_instance(self):
        return self.get_queryset().select_for_update().get(pk=self.get_object().pk)

    def write(self, request, partial=False, creating=False):
        self.check_write_access()
        try:
            with transaction.atomic():
                instance = None if creating else self.get_write_instance()
                before = {} if creating else dict(self.get_serializer(instance).data)
                serializer = self.get_serializer(instance, data=request.data, partial=partial)
                serializer.is_valid(raise_exception=True)
                expected = serializer.validated_data.pop("expected_revision", None)
                if not creating and expected != instance.revision:
                    raise ConfigurationConflict()
                self.authorize_values(serializer)
                instance = serializer.save(**({} if creating else {"revision": instance.revision + 1}))
                after = dict(self.get_serializer(instance).data)
                ConfigurationChange.objects.create(actor=request.user, target_type=instance._meta.model_name,
                    target_id=instance.pk, target_label=str(instance), before=before, after=after)
                return Response(after, status=status.HTTP_201_CREATED if creating else status.HTTP_200_OK)
        except IntegrityError:
            raise serializers.ValidationError({"non_field_errors": ["A configuration record with these identifiers already exists."]})

    def create(self, request, *args, **kwargs):
        return self.write(request, creating=True)

    def update(self, request, *args, **kwargs):
        return self.write(request, partial=kwargs.pop("partial", False))
