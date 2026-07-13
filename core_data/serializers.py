from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import serializers

from .access import user_has_capability
from .models import (
    AttendanceRawRow,
    AttendanceClassMatch,
    AttendanceVisit,
    Client,
    ExpectedClassSlot,
    GroupAccessProfile,
    LoginLog,
    PaymentMethod,
    PricingOption,
    ReportImport,
    Room,
    SaleLine,
    SaleRawRow,
    ScheduledClass,
    ServiceCategory,
    ServicePurchase,
    ServicePurchaseRawRow,
    Site,
    StaffMember,
    StudioClosure,
    Studio,
    TrainerAvailabilityRawRow,
    UserAccessProfile,
    WeeklyRoomTemplate,
)


User = get_user_model()


class MoneyProtectedSerializerMixin:
    money_fields = ()
    payload_money_keys = ()

    def can_view_money(self):
        request = self.context.get("request")
        return user_has_capability(request.user, "can_view_money") if request else True

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self.can_view_money():
            return data
        for field in self.money_fields:
            if field in data:
                data[field] = None
        for payload_field in ("raw_payload", "normalized_payload"):
            if payload_field not in data or not isinstance(data[payload_field], dict):
                continue
            data[payload_field] = {
                key: (None if key in self.payload_money_keys else value)
                for key, value in data[payload_field].items()
            }
        return data

    def money_safe_payload(self, payload):
        if self.can_view_money() or not isinstance(payload, dict):
            return payload
        return {
            key: (None if key in self.payload_money_keys else value)
            for key, value in payload.items()
        }


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    groups = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), many=True, required=False)
    group_name = serializers.SerializerMethodField()
    group_names = serializers.SerializerMethodField()

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
            "group_names",
            "image",
        ]
        read_only_fields = ["date_joined"]

    def get_group_name(self, obj):
        first_group = obj.groups.first()
        return first_group.name if first_group else None

    def get_group_names(self, obj):
        return list(obj.groups.order_by("name").values_list("name", flat=True))


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


class GroupAccessProfileSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)

    class Meta:
        model = GroupAccessProfile
        fields = [
            "id",
            "group",
            "group_name",
            "can_view_money",
            "can_upload_data",
            "can_edit_data",
            "can_reset_data",
            "can_manage_users",
            "can_view_admin_logs",
        ]


class UserAccessProfileSerializer(serializers.ModelSerializer):
    allowed_site_names = serializers.SerializerMethodField()
    allowed_studio_names = serializers.SerializerMethodField()

    class Meta:
        model = UserAccessProfile
        fields = [
            "id",
            "user",
            "language",
            "allowed_sites",
            "allowed_site_names",
            "allowed_studios",
            "allowed_studio_names",
            "can_view_money",
            "can_upload_data",
            "can_edit_data",
            "can_reset_data",
            "can_manage_users",
            "can_view_admin_logs",
        ]

    def get_allowed_site_names(self, obj):
        return [site.name for site in obj.allowed_sites.all()]

    def get_allowed_studio_names(self, obj):
        return [studio.name for studio in obj.allowed_studios.all()]


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site
        fields = "__all__"


class StudioSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)

    class Meta:
        model = Studio
        fields = "__all__"


class RoomSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    studio_name = serializers.CharField(source="studio.name", read_only=True)

    class Meta:
        model = Room
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


class StudioClosureSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    studio_name = serializers.CharField(source="studio.name", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)

    class Meta:
        model = StudioClosure
        fields = "__all__"


class ReportImportSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    studio_name = serializers.CharField(source="studio.name", read_only=True)

    class Meta:
        model = ReportImport
        fields = "__all__"
        read_only_fields = ["uploaded_by", "uploaded_at", "processed_at"]

    def get_uploaded_by_name(self, obj):
        if not obj.uploaded_by:
            return None
        return f"{obj.uploaded_by.first_name} {obj.uploaded_by.last_name}".strip() or obj.uploaded_by.email


class ScheduledClassSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    studio_name = serializers.CharField(source="studio.name", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)
    staff_member_name = serializers.CharField(source="staff_member.name", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    schedule_status_label = serializers.CharField(source="get_schedule_status_display", read_only=True)
    attendance_count = serializers.IntegerField(read_only=True)
    attended_count = serializers.IntegerField(read_only=True)
    no_show_count = serializers.IntegerField(read_only=True)
    late_cancel_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ScheduledClass
        fields = "__all__"
        read_only_fields = ["natural_key", "current_row_hash", "created_at", "updated_at"]


class WeeklyRoomTemplateSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    studio_name = serializers.CharField(source="studio.name", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)
    staff_member_name = serializers.CharField(source="staff_member.name", read_only=True)
    weekday_name = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = WeeklyRoomTemplate
        fields = "__all__"


class ExpectedClassSlotSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    studio_name = serializers.CharField(source="studio.name", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)
    staff_member_name = serializers.CharField(source="staff_member.name", read_only=True)
    scheduled_class_name = serializers.CharField(source="scheduled_class.name", read_only=True)
    scheduled_class_status = serializers.CharField(source="scheduled_class.status", read_only=True)
    scheduled_class_staff_member_name = serializers.CharField(source="scheduled_class.staff_member.name", read_only=True)
    scheduled_class_capacity = serializers.IntegerField(source="scheduled_class.capacity", read_only=True)
    scheduled_class_attendance_count = serializers.SerializerMethodField()
    scheduled_class_attended_count = serializers.SerializerMethodField()
    scheduled_class_no_show_count = serializers.SerializerMethodField()
    scheduled_class_late_cancel_count = serializers.SerializerMethodField()

    class Meta:
        model = ExpectedClassSlot
        fields = "__all__"

    def get_scheduled_class_attendance_count(self, obj):
        if not obj.scheduled_class_id:
            return 0
        return obj.scheduled_class.attendance_matches.filter(attendance_visit__is_active=True).count()

    def get_scheduled_class_attended_count(self, obj):
        if not obj.scheduled_class_id:
            return 0
        return obj.scheduled_class.attendance_matches.filter(
            attendance_visit__is_active=True,
            attendance_visit__no_show=False,
            attendance_visit__late_cancel=False,
        ).count()

    def get_scheduled_class_no_show_count(self, obj):
        if not obj.scheduled_class_id:
            return 0
        return obj.scheduled_class.attendance_matches.filter(
            attendance_visit__is_active=True,
            attendance_visit__no_show=True,
        ).count()

    def get_scheduled_class_late_cancel_count(self, obj):
        if not obj.scheduled_class_id:
            return 0
        return obj.scheduled_class.attendance_matches.filter(
            attendance_visit__is_active=True,
            attendance_visit__late_cancel=True,
        ).count()


class AttendanceVisitSerializer(MoneyProtectedSerializerMixin, serializers.ModelSerializer):
    money_fields = ("revenue",)
    payload_money_keys = ("_revenue", "Ingresos por visita")
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


class SaleLineSerializer(MoneyProtectedSerializerMixin, serializers.ModelSerializer):
    money_fields = ("item_total", "discount_amount", "tax", "paid_total")
    payload_money_keys = (
        "_item_total",
        "_discount_amount",
        "_tax",
        "_paid_total",
        "Total del Item",
        "Desc.",
        "Impuesto",
        "Total Pagado con Método de Pago",
    )
    site_name = serializers.CharField(source="site.name", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    client_mindbody_id = serializers.CharField(source="client.mindbody_id", read_only=True)
    studio_name = serializers.CharField(source="studio.name", read_only=True)
    payment_method_name = serializers.CharField(source="payment_method.name", read_only=True)

    class Meta:
        model = SaleLine
        fields = "__all__"


class ServicePurchaseSerializer(MoneyProtectedSerializerMixin, serializers.ModelSerializer):
    money_fields = ("total_amount", "cash_equivalent", "non_cash_equivalent")
    payload_money_keys = (
        "_total_amount",
        "_cash_equivalent",
        "_non_cash_equivalent",
        "Cantidad total",
        "Equivalente en efectivo",
        "No equivalente de efectivo",
    )
    site_name = serializers.CharField(source="site.name", read_only=True)
    studio_name = serializers.CharField(source="studio.name", read_only=True)
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


class AttendanceRawRowSerializer(MoneyProtectedSerializerMixin, serializers.ModelSerializer):
    payload_money_keys = ("_revenue", "Ingresos por visita")
    site_name = serializers.CharField(source="site.name", read_only=True)
    report_type = serializers.CharField(source="report_import.report_type", read_only=True)
    file_name = serializers.CharField(source="report_import.file_name", read_only=True)
    payload_summary = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRawRow
        fields = "__all__"

    def get_payload_summary(self, obj):
        return payload_summary(self.money_safe_payload(obj.normalized_payload))


class TrainerAvailabilityRawRowSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    report_type = serializers.CharField(source="report_import.report_type", read_only=True)
    file_name = serializers.CharField(source="report_import.file_name", read_only=True)
    payload_summary = serializers.SerializerMethodField()

    class Meta:
        model = TrainerAvailabilityRawRow
        fields = "__all__"

    def get_payload_summary(self, obj):
        return payload_summary(obj.normalized_payload)


class AttendanceClassMatchSerializer(serializers.ModelSerializer):
    attendance_date = serializers.DateField(source="attendance_visit.visit_date", read_only=True)
    attendance_time = serializers.CharField(source="attendance_visit.visit_time_raw", read_only=True)
    client_name = serializers.CharField(source="attendance_visit.client.name", read_only=True)
    client_mindbody_id = serializers.CharField(source="attendance_visit.client.mindbody_id", read_only=True)
    staff_member_name = serializers.CharField(source="attendance_visit.staff_member.name", read_only=True)
    pricing_option_name = serializers.CharField(source="attendance_visit.pricing_option.name", read_only=True)
    visit_type = serializers.CharField(source="attendance_visit.visit_type", read_only=True)
    source_import_id = serializers.IntegerField(source="attendance_visit.last_seen_import_id", read_only=True)
    source_file_name = serializers.CharField(source="attendance_visit.last_seen_import.file_name", read_only=True)
    scheduled_class_name = serializers.CharField(source="scheduled_class.name", read_only=True)

    class Meta:
        model = AttendanceClassMatch
        fields = "__all__"


class SaleRawRowSerializer(MoneyProtectedSerializerMixin, serializers.ModelSerializer):
    payload_money_keys = (
        "_item_total",
        "_discount_amount",
        "_tax",
        "_paid_total",
        "Total del Item",
        "Desc.",
        "Impuesto",
        "Total Pagado con Método de Pago",
    )
    site_name = serializers.CharField(source="site.name", read_only=True)
    report_type = serializers.CharField(source="report_import.report_type", read_only=True)
    file_name = serializers.CharField(source="report_import.file_name", read_only=True)
    payload_summary = serializers.SerializerMethodField()

    class Meta:
        model = SaleRawRow
        fields = "__all__"

    def get_payload_summary(self, obj):
        return payload_summary(self.money_safe_payload(obj.normalized_payload))


class ServicePurchaseRawRowSerializer(MoneyProtectedSerializerMixin, serializers.ModelSerializer):
    payload_money_keys = (
        "_total_amount",
        "_cash_equivalent",
        "_non_cash_equivalent",
        "Cantidad total",
        "Equivalente en efectivo",
        "No equivalente de efectivo",
    )
    site_name = serializers.CharField(source="site.name", read_only=True)
    studio_name = serializers.CharField(source="studio.name", read_only=True)
    report_type = serializers.CharField(source="report_import.report_type", read_only=True)
    file_name = serializers.CharField(source="report_import.file_name", read_only=True)
    payload_summary = serializers.SerializerMethodField()

    class Meta:
        model = ServicePurchaseRawRow
        fields = "__all__"

    def get_payload_summary(self, obj):
        return payload_summary(self.money_safe_payload(obj.normalized_payload))


class LoginLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = LoginLog
        fields = "__all__"
