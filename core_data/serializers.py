from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import serializers

from .models import (
    AttendanceRawRow,
    AttendanceVisit,
    Client,
    LoginLog,
    PaymentMethod,
    PricingOption,
    ReportImport,
    SaleLine,
    SaleRawRow,
    ServiceCategory,
    ServicePurchase,
    ServicePurchaseRawRow,
    Site,
    StaffMember,
    Studio,
)


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    groups = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), many=True, required=False)
    group_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "password",
            "groups",
            "group_name",
            "image",
        ]
        read_only_fields = ["date_joined"]

    def get_group_name(self, obj):
        first_group = obj.groups.first()
        return first_group.name if first_group else None


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_new_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        return value


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["id", "name"]


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site
        fields = "__all__"


class StudioSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)

    class Meta:
        model = Studio
        fields = "__all__"


class ClientSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)

    class Meta:
        model = Client
        fields = "__all__"


class StaffMemberSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)

    class Meta:
        model = StaffMember
        fields = "__all__"


class ServiceCategorySerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)

    class Meta:
        model = ServiceCategory
        fields = "__all__"


class PricingOptionSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    service_category_name = serializers.CharField(source="service_category.name", read_only=True)

    class Meta:
        model = PricingOption
        fields = "__all__"


class PaymentMethodSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)

    class Meta:
        model = PaymentMethod
        fields = "__all__"


class ReportImportSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ReportImport
        fields = "__all__"
        read_only_fields = ["uploaded_by", "uploaded_at", "processed_at"]

    def get_uploaded_by_name(self, obj):
        if not obj.uploaded_by:
            return None
        return f"{obj.uploaded_by.first_name} {obj.uploaded_by.last_name}".strip() or obj.uploaded_by.email


class AttendanceVisitSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    client_mindbody_id = serializers.CharField(source="client.mindbody_id", read_only=True)
    staff_member_name = serializers.CharField(source="staff_member.name", read_only=True)
    visit_studio_name = serializers.CharField(source="visit_studio.name", read_only=True)
    sale_studio_name = serializers.CharField(source="sale_studio.name", read_only=True)
    service_category_name = serializers.CharField(source="service_category.name", read_only=True)
    pricing_option_name = serializers.CharField(source="pricing_option.name", read_only=True)
    payment_method_name = serializers.CharField(source="payment_method.name", read_only=True)

    class Meta:
        model = AttendanceVisit
        fields = "__all__"


class SaleLineSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    client_mindbody_id = serializers.CharField(source="client.mindbody_id", read_only=True)
    studio_name = serializers.CharField(source="studio.name", read_only=True)
    payment_method_name = serializers.CharField(source="payment_method.name", read_only=True)

    class Meta:
        model = SaleLine
        fields = "__all__"


class ServicePurchaseSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    client_mindbody_id = serializers.CharField(source="client.mindbody_id", read_only=True)
    service_category_name = serializers.CharField(source="service_category.name", read_only=True)
    pricing_option_name = serializers.CharField(source="pricing_option.name", read_only=True)

    class Meta:
        model = ServicePurchase
        fields = "__all__"


def payload_summary(payload):
    if not payload:
        return ""
    parts = []
    for key, value in payload.items():
        if key.startswith("_"):
            continue
        if value not in ("", None):
            parts.append(f"{key}: {value}")
        if len(parts) == 4:
            break
    return " | ".join(parts)


class AttendanceRawRowSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    report_type = serializers.CharField(source="report_import.report_type", read_only=True)
    file_name = serializers.CharField(source="report_import.file_name", read_only=True)
    payload_summary = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRawRow
        fields = "__all__"

    def get_payload_summary(self, obj):
        return payload_summary(obj.normalized_payload)


class SaleRawRowSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    report_type = serializers.CharField(source="report_import.report_type", read_only=True)
    file_name = serializers.CharField(source="report_import.file_name", read_only=True)
    payload_summary = serializers.SerializerMethodField()

    class Meta:
        model = SaleRawRow
        fields = "__all__"

    def get_payload_summary(self, obj):
        return payload_summary(obj.normalized_payload)


class ServicePurchaseRawRowSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    report_type = serializers.CharField(source="report_import.report_type", read_only=True)
    file_name = serializers.CharField(source="report_import.file_name", read_only=True)
    payload_summary = serializers.SerializerMethodField()

    class Meta:
        model = ServicePurchaseRawRow
        fields = "__all__"

    def get_payload_summary(self, obj):
        return payload_summary(obj.normalized_payload)


class LoginLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = LoginLog
        fields = "__all__"
