import json
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .importers import (
    ATTENDANCE_REPORT_TYPE,
    SUPPORTED_REPORT_TYPES,
    TRAINER_AVAILABILITY_REPORT_TYPE,
    import_report,
    preview_report,
)
from .schedule_reconciliation import reconcile_scheduled_classes_from_templates
from .access import get_or_create_user_access_profile, resolve_access_payload, scoped_queryset_for_user, user_has_capability
from .permissions import CapabilityPermission
from .models import (
    AttendanceRawRow,
    AttendanceClassMatch,
    AttendanceVisit,
    AttendanceVisitVersion,
    Client,
    ExpectedClassSlot,
    GroupAccessProfile,
    LoginLog,
    PaymentMethod,
    PricingOption,
    ReportImport,
    Room,
    SaleLine,
    SaleLineVersion,
    SaleRawRow,
    ScheduledClass,
    ServiceCategory,
    ServicePurchase,
    ServicePurchaseRawRow,
    ServicePurchaseVersion,
    Site,
    StaffMember,
    StudioClosure,
    Studio,
    TrainerAvailabilityRawRow,
    UserAccessProfile,
    WeeklyRoomTemplate,
)
from .serializers import (
    AttendanceClassMatchSerializer,
    AttendanceRawRowSerializer,
    AttendanceVisitSerializer,
    ChangePasswordSerializer,
    ClientSerializer,
    ExpectedClassSlotSerializer,
    GroupAccessProfileSerializer,
    GroupSerializer,
    LoginLogSerializer,
    PaymentMethodSerializer,
    PricingOptionSerializer,
    ReportImportSerializer,
    RoomSerializer,
    SaleLineSerializer,
    SaleRawRowSerializer,
    ScheduledClassSerializer,
    ServiceCategorySerializer,
    ServicePurchaseRawRowSerializer,
    ServicePurchaseSerializer,
    SiteSerializer,
    StaffMemberSerializer,
    StudioClosureSerializer,
    StudioSerializer,
    TrainerAvailabilityRawRowSerializer,
    UserAccessProfileSerializer,
    UserSerializer,
    WeeklyRoomTemplateSerializer,
)


User = get_user_model()


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def mask_preview_money(request, payload):
    if user_has_capability(request.user, "can_view_money"):
        return payload
    if not isinstance(payload, dict):
        return payload
    preview = dict(payload)
    if isinstance(preview.get("revenue"), dict):
        preview["revenue"] = {
            **preview["revenue"],
            "total": None,
            "zero_revenue_rows": None,
        }
    if isinstance(preview.get("sales"), dict):
        preview["sales"] = {
            **preview["sales"],
            "paid_total": None,
            "gross_item_total": None,
            "discount_total": None,
            "tax_total": None,
        }
    if isinstance(preview.get("services"), dict):
        preview["services"] = {
            **preview["services"],
            "total_amount": None,
            "cash_equivalent": None,
            "non_cash_equivalent": None,
        }
    return preview


class UserViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, CapabilityPermission]
    required_capability = "can_manage_users"

    def list(self, request):
        users = User.objects.all().order_by("first_name", "last_name", "email")
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(UserSerializer(user).data)

    def create(self, request):
        serializer = UserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        password = request.data.get("password")
        if not password:
            return Response({"error": "Password is required"}, status=status.HTTP_400_BAD_REQUEST)

        groups = serializer.validated_data.pop("groups", [])
        user = serializer.save()
        user.set_password(password)
        user.save()
        if groups:
            user.groups.set(groups)

        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        if user.is_superuser and not request.user.is_superuser:
            return Response({"error": "Only a superuser can edit another superuser."}, status=status.HTTP_403_FORBIDDEN)
        if user.is_superuser:
            protected_fields = {"is_superuser", "is_staff", "is_active", "groups"}
            if protected_fields.intersection(request.data.keys()):
                return Response({"error": "Superuser role fields are protected in the app."}, status=status.HTTP_403_FORBIDDEN)

        serializer = UserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        if request.data.get("password"):
            user.set_password(request.data["password"])
            user.save()

        return Response(UserSerializer(user).data)

    def destroy(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        if user.is_superuser:
            return Response({"error": "Superusers cannot be deleted from the app."}, status=status.HTTP_403_FORBIDDEN)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"])
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response({"error": "Old password is incorrect"}, status=status.HTTP_400_BAD_REQUEST)

        new_password = serializer.validated_data["new_password"]
        try:
            validate_password(new_password, user)
        except ValidationError as exc:
            return Response({"error": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        return Response({"message": "Password updated successfully"})


class GroupAccessProfileViewSet(viewsets.ModelViewSet):
    queryset = GroupAccessProfile.objects.select_related("group").all()
    serializer_class = GroupAccessProfileSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    required_capability = "can_manage_users"


class UserAccessProfileViewSet(viewsets.ModelViewSet):
    serializer_class = UserAccessProfileSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    required_capability = "can_manage_users"

    def get_queryset(self):
        queryset = (
            UserAccessProfile.objects.select_related("user")
            .prefetch_related("allowed_sites", "allowed_studios")
            .order_by("user__email")
        )
        user_id = self.request.query_params.get("user")
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        return queryset


class SiteViewSet(viewsets.ModelViewSet):
    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    write_capability = "can_edit_data"

    def get_queryset(self):
        return scoped_queryset_for_user(Site.objects.all(), self.request.user, site_field="id")


class StudioViewSet(viewsets.ModelViewSet):
    serializer_class = StudioSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    write_capability = "can_edit_data"

    def get_queryset(self):
        return scoped_queryset_for_user(
            Studio.objects.select_related("site").all(),
            self.request.user,
            studio_field="id",
        )


class RoomViewSet(viewsets.ModelViewSet):
    serializer_class = RoomSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    write_capability = "can_edit_data"

    def get_queryset(self):
        queryset = Room.objects.select_related("site", "studio").all()
        queryset = scoped_queryset_for_user(queryset, self.request.user, studio_field="studio_id")
        site = self.request.query_params.get("site")
        studio = self.request.query_params.get("studio")
        search = self.request.query_params.get("search")
        if site:
            queryset = queryset.filter(site_id=site)
        if studio:
            queryset = queryset.filter(studio_id=studio)
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(studio__name__icontains=search))
        return queryset


class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    write_capability = "can_edit_data"

    def get_queryset(self):
        return scoped_queryset_for_user(Client.objects.select_related("site").all(), self.request.user)


class StaffMemberViewSet(viewsets.ModelViewSet):
    serializer_class = StaffMemberSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    write_capability = "can_edit_data"

    def get_queryset(self):
        return scoped_queryset_for_user(StaffMember.objects.select_related("site").all(), self.request.user)


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    write_capability = "can_edit_data"

    def get_queryset(self):
        return scoped_queryset_for_user(ServiceCategory.objects.select_related("site").all(), self.request.user)


class PricingOptionViewSet(viewsets.ModelViewSet):
    serializer_class = PricingOptionSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    write_capability = "can_edit_data"

    def get_queryset(self):
        return scoped_queryset_for_user(
            PricingOption.objects.select_related("site", "service_category").all(),
            self.request.user,
        )


class PaymentMethodViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentMethodSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    write_capability = "can_edit_data"

    def get_queryset(self):
        return scoped_queryset_for_user(PaymentMethod.objects.select_related("site").all(), self.request.user)


def parse_iso_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def generated_slot_status(expected_slot):
    if expected_slot.scheduled_class_id:
        return ExpectedClassSlot.STATUS_MATCHED
    return ExpectedClassSlot.STATUS_MISSING


def minutes_since_midnight(value):
    return value.hour * 60 + value.minute


def duration_difference_minutes(start_a, end_a, start_b, end_b):
    duration_a = minutes_since_midnight(end_a) - minutes_since_midnight(start_a)
    duration_b = minutes_since_midnight(end_b) - minutes_since_midnight(start_b)
    return abs(duration_a - duration_b)


def find_matching_scheduled_class(template, slot_date):
    candidates = ScheduledClass.objects.filter(
        site=template.site,
        studio=template.studio,
        room=template.room,
        class_date=slot_date,
        start_time=template.start_time,
    ).exclude(status=ScheduledClass.STATUS_CANCELLED)
    candidates = [
        candidate for candidate in candidates
        if duration_difference_minutes(
            template.start_time,
            template.end_time,
            candidate.start_time,
            candidate.end_time,
        ) <= 15
    ]
    candidates.sort(key=lambda candidate: 0 if candidate.source == ScheduledClass.SOURCE_TRAINER_AVAILABILITY else 1)
    if template.staff_member_id:
        exact = next((candidate for candidate in candidates if candidate.staff_member_id == template.staff_member_id), None)
        if exact:
            return exact
    detected_candidates = [
        candidate for candidate in candidates
        if candidate.source == ScheduledClass.SOURCE_TRAINER_AVAILABILITY
    ]
    if len(detected_candidates) == 1:
        return detected_candidates[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def generate_expected_slots(site_id=None, studio_id=None, room_id=None, date_from=None, date_to=None):
    templates = WeeklyRoomTemplate.objects.select_related("site", "studio", "room", "staff_member").filter(active=True)
    if site_id:
        templates = templates.filter(site_id=site_id)
    if studio_id:
        templates = templates.filter(studio_id=studio_id)
    if room_id:
        templates = templates.filter(room_id=room_id)

    protected_statuses = {
        ExpectedClassSlot.STATUS_CANCELLED,
        ExpectedClassSlot.STATUS_UNAVAILABLE,
        ExpectedClassSlot.STATUS_MANUALLY_CREATED,
        ExpectedClassSlot.STATUS_IGNORED,
    }
    stats = {"created": 0, "updated": 0, "matched": 0, "missing": 0, "preserved": 0}
    current_date = date_from
    while current_date <= date_to:
        for template in templates:
            if template.weekday != current_date.weekday():
                continue
            if template.active_from > current_date:
                continue
            if template.active_until and template.active_until < current_date:
                continue

            scheduled_class = find_matching_scheduled_class(template, current_date)
            status_value = ExpectedClassSlot.STATUS_MATCHED if scheduled_class else ExpectedClassSlot.STATUS_MISSING
            expected_slot = ExpectedClassSlot.objects.filter(
                site=template.site,
                room=template.room,
                slot_date=current_date,
                start_time=template.start_time,
                end_time=template.end_time,
            ).first()

            if expected_slot and expected_slot.status in protected_statuses:
                stats["preserved"] += 1
                stats["matched" if expected_slot.scheduled_class_id else "missing"] += 1
                continue

            defaults = {
                "studio": template.studio,
                "template": template,
                "scheduled_class": scheduled_class,
                "staff_member": template.staff_member,
                "name": template.name,
                "capacity": template.capacity,
                "status": status_value,
            }

            if expected_slot:
                for field, value in defaults.items():
                    setattr(expected_slot, field, value)
                expected_slot.save()
                created = False
            else:
                expected_slot = ExpectedClassSlot.objects.create(
                    site=template.site,
                    room=template.room,
                    slot_date=current_date,
                    start_time=template.start_time,
                    end_time=template.end_time,
                    **defaults,
                )
                created = True
            stats["created" if created else "updated"] += 1
            stats["matched" if expected_slot.scheduled_class_id else "missing"] += 1
        current_date += timedelta(days=1)
    return stats


def rematch_expected_slots_to_detected_classes(site_id=None, studio_id=None, room_id=None, date_from=None, date_to=None):
    expected_slots = ExpectedClassSlot.objects.select_related(
        "template",
        "scheduled_class",
    ).filter(
        template__isnull=False,
        slot_date__range=(date_from, date_to),
    ).exclude(
        status__in=[
            ExpectedClassSlot.STATUS_CANCELLED,
            ExpectedClassSlot.STATUS_UNAVAILABLE,
            ExpectedClassSlot.STATUS_IGNORED,
        ],
    )
    if site_id:
        expected_slots = expected_slots.filter(site_id=site_id)
    if studio_id:
        expected_slots = expected_slots.filter(studio_id=studio_id)
    if room_id:
        expected_slots = expected_slots.filter(room_id=room_id)

    stats = {
        "expected_slots_checked": 0,
        "expected_slots_relinked": 0,
        "manual_classes_removed": 0,
        "attendance_matches_transferred": 0,
    }
    auto_created_reasons = {
        "Automatically created from expected schedule after report import.",
        "Created from expected schedule slot",
    }
    for expected_slot in expected_slots:
        stats["expected_slots_checked"] += 1
        detected_class = find_matching_scheduled_class(expected_slot.template, expected_slot.slot_date)
        if not detected_class or detected_class.source != ScheduledClass.SOURCE_TRAINER_AVAILABILITY:
            continue
        if expected_slot.scheduled_class_id == detected_class.id:
            expected_slot.status = ExpectedClassSlot.STATUS_MATCHED
            expected_slot.save(update_fields=["status", "updated_at"])
            continue

        previous_class = expected_slot.scheduled_class
        if previous_class and previous_class.source == ScheduledClass.SOURCE_MANUAL:
            transferred = AttendanceClassMatch.objects.filter(scheduled_class=previous_class).update(scheduled_class=detected_class)
            stats["attendance_matches_transferred"] += transferred

        expected_slot.scheduled_class = detected_class
        expected_slot.status = ExpectedClassSlot.STATUS_MATCHED
        expected_slot.resolution_notes = "Relinked to detected class during schedule rematch."
        expected_slot.save(update_fields=["scheduled_class", "status", "resolution_notes", "updated_at"])
        stats["expected_slots_relinked"] += 1

        if (
            previous_class
            and previous_class.source == ScheduledClass.SOURCE_MANUAL
            and previous_class.reason in auto_created_reasons
            and not previous_class.expected_slots.exists()
        ):
            previous_class.delete()
            stats["manual_classes_removed"] += 1

    return stats


def create_scheduled_classes_from_missing_expected_slots(site_id=None, studio_id=None, room_id=None, date_from=None, date_to=None):
    expected_slots = ExpectedClassSlot.objects.select_related("site", "studio", "room", "staff_member").filter(
        status=ExpectedClassSlot.STATUS_MISSING,
        scheduled_class__isnull=True,
        slot_date__range=(date_from, date_to),
    )
    if site_id:
        expected_slots = expected_slots.filter(site_id=site_id)
    if studio_id:
        expected_slots = expected_slots.filter(studio_id=studio_id)
    if room_id:
        expected_slots = expected_slots.filter(room_id=room_id)

    stats = {"manual_classes_created": 0}
    for expected_slot in expected_slots:
        scheduled_class = ScheduledClass.objects.create(
            site=expected_slot.site,
            studio=expected_slot.studio,
            room=expected_slot.room,
            staff_member=expected_slot.staff_member,
            name=expected_slot.name,
            class_date=expected_slot.slot_date,
            start_time=expected_slot.start_time,
            end_time=expected_slot.end_time,
            session_type=ScheduledClass.SESSION_TYPE_GROUP,
            capacity=expected_slot.capacity,
            status=ScheduledClass.STATUS_SCHEDULED,
            reason="Automatically created from expected schedule after report import.",
            source=ScheduledClass.SOURCE_MANUAL,
            manually_modified=True,
        )
        expected_slot.scheduled_class = scheduled_class
        expected_slot.status = ExpectedClassSlot.STATUS_MANUALLY_CREATED
        expected_slot.resolution_notes = "Automatically created from expected schedule after report import."
        expected_slot.save(update_fields=["scheduled_class", "status", "resolution_notes", "updated_at"])
        stats["manual_classes_created"] += 1
    return stats


def automate_schedule_after_import(site, import_result, report_type):
    if report_type not in {ATTENDANCE_REPORT_TYPE, TRAINER_AVAILABILITY_REPORT_TYPE}:
        return None

    date_range = (import_result.get("preview") or {}).get("date_range") or {}
    start = parse_iso_date(date_range.get("from"))
    end = parse_iso_date(date_range.get("to"))
    if not start or not end:
        return {
            "skipped": True,
            "reason": "Report did not provide a valid date range.",
        }

    with transaction.atomic():
        expected_stats = generate_expected_slots(
            site_id=site.id,
            date_from=start,
            date_to=end,
        )
        rematch_stats = rematch_expected_slots_to_detected_classes(
            site_id=site.id,
            date_from=start,
            date_to=end,
        )
        manual_class_stats = create_scheduled_classes_from_missing_expected_slots(
            site_id=site.id,
            date_from=start,
            date_to=end,
        )
        scheduled_class_reconciliation = reconcile_scheduled_classes_from_templates(
            site_id=site.id,
            date_from=start,
            date_to=end,
        )
        from analytics.views import rebuild_attendance_class_matches

        match_stats = rebuild_attendance_class_matches(site_id=site.id, start=start, end=end)

    return {
        "skipped": False,
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "expected_slots": expected_stats,
        "expected_slot_rematch": rematch_stats,
        "manual_classes": manual_class_stats,
        "scheduled_class_reconciliation": scheduled_class_reconciliation,
        "attendance_matches": match_stats,
    }


class WeeklyRoomTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = WeeklyRoomTemplateSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    write_capability = "can_edit_data"
    capability_by_action = {
        "sync_capacity_from_rooms": "can_edit_data",
    }

    def get_queryset(self):
        queryset = WeeklyRoomTemplate.objects.select_related("site", "studio", "room", "staff_member").all()
        queryset = scoped_queryset_for_user(queryset, self.request.user, studio_field="studio_id")
        site = self.request.query_params.get("site")
        studio = self.request.query_params.get("studio")
        room = self.request.query_params.get("room")
        active = self.request.query_params.get("active")
        if site:
            queryset = queryset.filter(site_id=site)
        if studio:
            queryset = queryset.filter(studio_id=studio)
        if room:
            queryset = queryset.filter(room_id=room)
        if active in ("true", "false"):
            queryset = queryset.filter(active=active == "true")
        return queryset

    @action(detail=False, methods=["post"], url_path="sync-capacity-from-rooms")
    def sync_capacity_from_rooms(self, request):
        if not settings.ENABLE_ANALYTICS_RESET:
            return Response(
                {"error": "Schedule maintenance actions are disabled for this environment."},
                status=status.HTTP_403_FORBIDDEN,
            )
        site_id = request.data.get("site") or request.query_params.get("site")
        if not site_id:
            return Response({"error": "site is required."}, status=status.HTTP_400_BAD_REQUEST)

        queryset = WeeklyRoomTemplate.objects.select_related("room").filter(site_id=site_id)
        studio_id = request.data.get("studio") or request.query_params.get("studio")
        room_id = request.data.get("room") or request.query_params.get("room")
        active_only = request.data.get("active_only", True)
        if studio_id:
            queryset = queryset.filter(studio_id=studio_id)
        if room_id:
            queryset = queryset.filter(room_id=room_id)
        if active_only in (True, "true", "True", "1", 1):
            queryset = queryset.filter(active=True)

        updated = 0
        skipped = 0
        samples = []
        with transaction.atomic():
            for template in queryset:
                room_capacity = template.room.group_capacity or template.room.private_capacity or 0
                if room_capacity <= 0:
                    skipped += 1
                    continue
                if template.capacity == room_capacity:
                    continue
                previous_capacity = template.capacity
                template.capacity = room_capacity
                template.save(update_fields=["capacity", "updated_at"])
                updated += 1
                if len(samples) < 10:
                    samples.append({
                        "id": template.id,
                        "room": template.room.name,
                        "weekday": template.weekday,
                        "start_time": template.start_time.strftime("%H:%M"),
                        "previous_capacity": previous_capacity,
                        "new_capacity": room_capacity,
                    })

        return Response({
            "updated": updated,
            "skipped_without_capacity": skipped,
            "samples": samples,
        })


class ExpectedClassSlotViewSet(viewsets.ModelViewSet):
    serializer_class = ExpectedClassSlotSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    write_capability = "can_edit_data"
    capability_by_action = {
        "generate": "can_edit_data",
        "rematch": "can_edit_data",
        "reset_scoped": "can_reset_data",
        "create_scheduled_class": "can_edit_data",
        "resolve": "can_edit_data",
    }

    def get_queryset(self):
        queryset = ExpectedClassSlot.objects.select_related(
            "site",
            "studio",
            "room",
            "template",
            "scheduled_class",
            "staff_member",
        ).all()
        queryset = scoped_queryset_for_user(queryset, self.request.user, studio_field="studio_id")
        site = self.request.query_params.get("site")
        studio = self.request.query_params.get("studio")
        room = self.request.query_params.get("room")
        status_value = self.request.query_params.get("status")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        if site:
            queryset = queryset.filter(site_id=site)
        if studio:
            queryset = queryset.filter(studio_id=studio)
        if room:
            queryset = queryset.filter(room_id=room)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if date_from:
            queryset = queryset.filter(slot_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(slot_date__lte=date_to)
        return queryset

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request):
        start = parse_iso_date(request.data.get("date_from") or request.query_params.get("date_from"))
        end = parse_iso_date(request.data.get("date_to") or request.query_params.get("date_to"))
        if not start or not end:
            return Response({"error": "date_from and date_to are required."}, status=status.HTTP_400_BAD_REQUEST)
        if end < start:
            return Response({"error": "date_to must be after date_from."}, status=status.HTTP_400_BAD_REQUEST)
        if (end - start).days > 120:
            return Response({"error": "Generate at most 120 days at a time."}, status=status.HTTP_400_BAD_REQUEST)

        stats = generate_expected_slots(
            site_id=request.data.get("site") or request.query_params.get("site"),
            studio_id=request.data.get("studio") or request.query_params.get("studio"),
            room_id=request.data.get("room") or request.query_params.get("room"),
            date_from=start,
            date_to=end,
        )
        manual_class_stats = create_scheduled_classes_from_missing_expected_slots(
            site_id=request.data.get("site") or request.query_params.get("site"),
            studio_id=request.data.get("studio") or request.query_params.get("studio"),
            room_id=request.data.get("room") or request.query_params.get("room"),
            date_from=start,
            date_to=end,
        )
        return Response({
            "date_range": {"from": start.isoformat(), "to": end.isoformat()},
            **stats,
            **manual_class_stats,
        })

    @action(detail=False, methods=["post"], url_path="rematch")
    def rematch(self, request):
        start = parse_iso_date(request.data.get("date_from") or request.query_params.get("date_from"))
        end = parse_iso_date(request.data.get("date_to") or request.query_params.get("date_to"))
        if not start or not end:
            return Response({"error": "date_from and date_to are required."}, status=status.HTTP_400_BAD_REQUEST)
        if end < start:
            return Response({"error": "date_to must be after date_from."}, status=status.HTTP_400_BAD_REQUEST)
        if (end - start).days > 120:
            return Response({"error": "Rematch at most 120 days at a time."}, status=status.HTTP_400_BAD_REQUEST)

        site_id = request.data.get("site") or request.query_params.get("site")
        studio_id = request.data.get("studio") or request.query_params.get("studio")
        room_id = request.data.get("room") or request.query_params.get("room")
        with transaction.atomic():
            rematch_stats = rematch_expected_slots_to_detected_classes(
                site_id=site_id,
                studio_id=studio_id,
                room_id=room_id,
                date_from=start,
                date_to=end,
            )
            from analytics.views import rebuild_attendance_class_matches

            match_stats = rebuild_attendance_class_matches(site_id=site_id, start=start, end=end)

        return Response({
            "date_range": {"from": start.isoformat(), "to": end.isoformat()},
            **rematch_stats,
            "attendance_matches": match_stats,
        })

    @action(detail=False, methods=["post"], url_path="reset-scoped")
    def reset_scoped(self, request):
        if not settings.ENABLE_ANALYTICS_RESET:
            return Response(
                {"error": "Schedule reset is disabled for this environment."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.data.get("confirmation") != "RESET SCHEDULE DATA":
            return Response({"error": "Invalid confirmation phrase."}, status=status.HTTP_400_BAD_REQUEST)

        site_id = request.data.get("site") or request.query_params.get("site")
        start = parse_iso_date(request.data.get("date_from") or request.query_params.get("date_from"))
        end = parse_iso_date(request.data.get("date_to") or request.query_params.get("date_to"))
        if not site_id:
            return Response({"error": "site is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not start or not end:
            return Response({"error": "date_from and date_to are required."}, status=status.HTTP_400_BAD_REQUEST)
        if end < start:
            return Response({"error": "date_to must be after date_from."}, status=status.HTTP_400_BAD_REQUEST)
        if (end - start).days > 120:
            return Response({"error": "Reset at most 120 days at a time."}, status=status.HTTP_400_BAD_REQUEST)

        expected_slots = ExpectedClassSlot.objects.filter(
            site_id=site_id,
            slot_date__range=(start, end),
        )
        studio_id = request.data.get("studio") or request.query_params.get("studio")
        room_id = request.data.get("room") or request.query_params.get("room")
        if studio_id:
            expected_slots = expected_slots.filter(studio_id=studio_id)
        if room_id:
            expected_slots = expected_slots.filter(room_id=room_id)

        include_manual_classes = request.data.get("include_manual_classes", True)
        include_manual_classes = include_manual_classes in (True, "true", "True", "1", 1)

        manual_class_ids = []
        if include_manual_classes:
            manual_class_ids = list(
                expected_slots.filter(
                    scheduled_class__source=ScheduledClass.SOURCE_MANUAL,
                ).values_list("scheduled_class_id", flat=True)
            )

        with transaction.atomic():
            expected_count = expected_slots.count()
            expected_slots.delete()
            manual_class_count = 0
            if manual_class_ids:
                manual_class_count, _ = ScheduledClass.objects.filter(
                    id__in=manual_class_ids,
                    source=ScheduledClass.SOURCE_MANUAL,
                ).delete()

        return Response({
            "date_range": {"from": start.isoformat(), "to": end.isoformat()},
            "expected_slots_deleted": expected_count,
            "manual_classes_deleted": manual_class_count,
            "imported_classes_preserved": True,
        })

    @action(detail=True, methods=["post"], url_path="create-scheduled-class")
    def create_scheduled_class(self, request, pk=None):
        expected_slot = self.get_object()
        if expected_slot.scheduled_class_id:
            return Response({"error": "This expected slot already has a scheduled class."}, status=status.HTTP_400_BAD_REQUEST)

        scheduled_class = ScheduledClass.objects.create(
            site=expected_slot.site,
            studio=expected_slot.studio,
            room=expected_slot.room,
            staff_member=expected_slot.staff_member,
            name=expected_slot.name,
            class_date=expected_slot.slot_date,
            start_time=expected_slot.start_time,
            end_time=expected_slot.end_time,
            session_type=ScheduledClass.SESSION_TYPE_GROUP,
            capacity=expected_slot.capacity,
            status=ScheduledClass.STATUS_SCHEDULED,
            reason="Created from expected schedule slot",
            source=ScheduledClass.SOURCE_MANUAL,
            manually_modified=True,
        )
        expected_slot.scheduled_class = scheduled_class
        expected_slot.status = ExpectedClassSlot.STATUS_MANUALLY_CREATED
        expected_slot.resolution_notes = request.data.get("notes") or "Scheduled class created manually from expected slot."
        expected_slot.save(update_fields=["scheduled_class", "status", "resolution_notes", "updated_at"])
        return Response({
            "expected_slot": ExpectedClassSlotSerializer(expected_slot).data,
            "scheduled_class": ScheduledClassSerializer(scheduled_class).data,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        expected_slot = self.get_object()
        status_value = request.data.get("status")
        allowed_statuses = {
            ExpectedClassSlot.STATUS_CANCELLED,
            ExpectedClassSlot.STATUS_UNAVAILABLE,
            ExpectedClassSlot.STATUS_IGNORED,
            ExpectedClassSlot.STATUS_MISSING,
        }
        if status_value not in allowed_statuses:
            return Response({"error": "Invalid resolution status."}, status=status.HTTP_400_BAD_REQUEST)

        if status_value == ExpectedClassSlot.STATUS_CANCELLED and expected_slot.scheduled_class_id:
            expected_slot.scheduled_class.status = ScheduledClass.STATUS_CANCELLED
            expected_slot.scheduled_class.reason = request.data.get("notes") or "Cancelled from expected schedule slot."
            expected_slot.scheduled_class.manually_modified = True
            expected_slot.scheduled_class.save(update_fields=["status", "reason", "manually_modified", "updated_at"])
        elif status_value == ExpectedClassSlot.STATUS_UNAVAILABLE and expected_slot.scheduled_class_id:
            expected_slot.scheduled_class.status = ScheduledClass.STATUS_UNAVAILABLE
            expected_slot.scheduled_class.reason = request.data.get("notes") or "Marked unavailable from expected schedule slot."
            expected_slot.scheduled_class.manually_modified = True
            expected_slot.scheduled_class.save(update_fields=["status", "reason", "manually_modified", "updated_at"])
        elif status_value == ExpectedClassSlot.STATUS_MISSING and expected_slot.scheduled_class_id:
            expected_slot.scheduled_class.status = ScheduledClass.STATUS_SCHEDULED
            expected_slot.scheduled_class.reason = request.data.get("notes") or "Restored from expected schedule slot."
            expected_slot.scheduled_class.manually_modified = True
            expected_slot.scheduled_class.save(update_fields=["status", "reason", "manually_modified", "updated_at"])

        if status_value == ExpectedClassSlot.STATUS_MISSING and expected_slot.scheduled_class_id:
            expected_slot.status = (
                ExpectedClassSlot.STATUS_MANUALLY_CREATED
                if expected_slot.scheduled_class.source == ScheduledClass.SOURCE_MANUAL
                else ExpectedClassSlot.STATUS_MATCHED
            )
        else:
            expected_slot.status = status_value
        expected_slot.resolution_notes = request.data.get("notes") or expected_slot.resolution_notes
        expected_slot.save(update_fields=["status", "resolution_notes", "updated_at"])
        return Response(ExpectedClassSlotSerializer(expected_slot).data)


class StudioClosureViewSet(viewsets.ModelViewSet):
    serializer_class = StudioClosureSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    write_capability = "can_edit_data"

    def get_queryset(self):
        queryset = StudioClosure.objects.select_related("site", "studio", "room").all()
        queryset = scoped_queryset_for_user(
            queryset,
            self.request.user,
            studio_field="studio_id",
            include_null_studio=True,
        )
        site = self.request.query_params.get("site")
        studio = self.request.query_params.get("studio")
        room = self.request.query_params.get("room")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        if site:
            queryset = queryset.filter(site_id=site)
        if studio:
            queryset = queryset.filter(studio_id=studio)
        if room:
            queryset = queryset.filter(room_id=room)
        if date_from:
            queryset = queryset.filter(closure_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(closure_date__lte=date_to)
        return queryset


class ReportImportViewSet(viewsets.ModelViewSet):
    queryset = ReportImport.objects.select_related("uploaded_by").all()
    serializer_class = ReportImportSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    read_capability = "can_upload_data"
    write_capability = "can_upload_data"
    capability_by_action = {
        "create": "can_upload_data",
        "preview": "can_upload_data",
        "import_file": "can_upload_data",
        "rollback": "can_reset_data",
        "reset_analytics_data": "can_reset_data",
        "repair_sales_by_service_purchases": "can_reset_data",
        "destroy": "can_reset_data",
    }

    def get_queryset(self):
        queryset = ReportImport.objects.select_related("uploaded_by", "studio").all()
        queryset = scoped_queryset_for_user(
            queryset,
            self.request.user,
            site_field="studio__site_id",
            studio_field="studio_id",
        )
        report_type = self.request.query_params.get("report_type")
        status_value = self.request.query_params.get("status")
        studio = self.request.query_params.get("studio")
        search = self.request.query_params.get("search")
        if report_type:
            queryset = queryset.filter(report_type=report_type)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if studio:
            queryset = queryset.filter(studio_id=studio)
        if search:
            queryset = queryset.filter(file_name__icontains=search)
        return queryset

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    def report_date_range(self, raw_queryset):
        dates = []
        for payload in raw_queryset.values_list("normalized_payload", flat=True):
            date_value = payload.get("_class_date") or payload.get("visit_date") or payload.get("sale_date")
            parsed = parse_iso_date(date_value)
            if parsed:
                dates.append(parsed)
        if not dates:
            return None, None
        return min(dates), max(dates)

    def import_models(self, report_import):
        if report_import.report_type == "attendance_with_revenue":
            return {
                "raw_model": AttendanceRawRow,
                "current_model": AttendanceVisit,
                "version_model": AttendanceVisitVersion,
                "raw_relation": "raw_row",
                "created_label": "attendance_created",
                "changed_label": "attendance_changed",
                "identical_label": "attendance_identical",
            }
        if report_import.report_type == "sales":
            return {
                "raw_model": SaleRawRow,
                "current_model": SaleLine,
                "version_model": SaleLineVersion,
                "raw_relation": "raw_row",
                "created_label": "sale_lines_created",
                "changed_label": "sale_lines_changed",
                "identical_label": "sale_lines_identical",
            }
        if report_import.report_type == "sales_by_service":
            return {
                "raw_model": ServicePurchaseRawRow,
                "current_model": ServicePurchase,
                "version_model": ServicePurchaseVersion,
                "raw_relation": "raw_row",
                "created_label": "service_purchases_created",
                "changed_label": "service_purchases_changed",
                "identical_label": "service_purchases_identical",
            }
        return None

    @action(detail=True, methods=["get"], url_path="detail-summary")
    def detail_summary(self, request, pk=None):
        report_import = self.get_object()
        model_config = self.import_models(report_import)
        if not model_config:
            return Response({"error": "Unsupported report type."}, status=status.HTTP_400_BAD_REQUEST)

        raw_queryset = model_config["raw_model"].objects.filter(report_import=report_import)
        current_queryset = model_config["current_model"].objects.filter(last_seen_import=report_import)
        created_count = current_queryset.filter(first_seen_import=report_import).count()
        versions = model_config["version_model"].objects.filter(report_import=report_import)
        changed_count = max(versions.count() - created_count, 0)
        identical_count = max(current_queryset.count() - versions.count(), 0)
        invalid_rows = raw_queryset.filter(is_valid=False)

        changed_samples = []
        for version in versions.exclude(changed_fields=[]).select_related(model_config["raw_relation"])[:15]:
            raw_row = getattr(version, model_config["raw_relation"])
            changed_samples.append({
                "row_number": raw_row.row_number if raw_row else None,
                "changed_fields": version.changed_fields,
            })

        invalid_samples = [
            {
                "row_number": raw.row_number,
                "errors": raw.validation_errors,
                "summary": " | ".join(
                    f"{key}: {value}"
                    for key, value in raw.normalized_payload.items()
                    if not key.startswith("_") and value not in ("", None)
                )[:500],
            }
            for raw in invalid_rows.order_by("row_number")[:15]
        ]

        return Response({
            "id": report_import.id,
            "file_name": report_import.file_name,
            "report_type": report_import.report_type,
            "status": report_import.status,
            "uploaded_at": report_import.uploaded_at,
            "processed_at": report_import.processed_at,
            "total_rows": report_import.total_rows,
            "valid_rows": report_import.valid_rows,
            "error_rows": report_import.error_rows,
            "counts": {
                "raw_rows": raw_queryset.count(),
                "valid_raw_rows": raw_queryset.filter(is_valid=True).count(),
                "invalid_raw_rows": invalid_rows.count(),
                "current_records_seen": current_queryset.count(),
                model_config["created_label"]: created_count,
                model_config["changed_label"]: changed_count,
                model_config["identical_label"]: identical_count,
                "versions_created": versions.count(),
            },
            "changed_samples": changed_samples,
            "invalid_samples": invalid_samples,
        })

    @action(detail=True, methods=["post"], url_path="rollback")
    def rollback(self, request, pk=None):
        if not settings.ENABLE_ANALYTICS_RESET:
            return Response(
                {"error": "Report rollback is disabled for this environment."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.data.get("confirmation") != "DELETE REPORT DATA":
            return Response({"error": "Invalid confirmation phrase."}, status=status.HTTP_400_BAD_REQUEST)

        report_import = self.get_object()
        report_payload = {
            "id": report_import.id,
            "file_name": report_import.file_name,
            "report_type": report_import.report_type,
        }
        dry_run = request.data.get("dry_run", False) in (True, "true", "True", "1", 1)
        include_schedule_data = request.data.get("include_schedule_data", True) in (True, "true", "True", "1", 1)
        deleted_counts = {}
        notes = []

        with transaction.atomic():
            if report_import.report_type == TRAINER_AVAILABILITY_REPORT_TYPE:
                raw_queryset = TrainerAvailabilityRawRow.objects.filter(report_import=report_import)
                site_ids = list(raw_queryset.values_list("site_id", flat=True).distinct())
                start, end = self.report_date_range(raw_queryset)

                imported_classes = ScheduledClass.objects.filter(source_import=report_import)
                deleted_counts["imported_scheduled_classes"] = imported_classes.count()

                expected_slots = ExpectedClassSlot.objects.none()
                generated_class_ids = []
                if include_schedule_data and start and end and site_ids:
                    expected_slots = ExpectedClassSlot.objects.filter(
                        site_id__in=site_ids,
                        slot_date__range=(start, end),
                        created_at__gte=report_import.uploaded_at,
                    )
                    generated_class_ids = list(
                        expected_slots.filter(
                            scheduled_class__source__in=[
                                ScheduledClass.SOURCE_MANUAL,
                                ScheduledClass.SOURCE_EXPECTED_TEMPLATE,
                            ],
                            scheduled_class__created_at__gte=report_import.uploaded_at,
                        ).values_list("scheduled_class_id", flat=True)
                    )

                deleted_counts["generated_expected_slots"] = expected_slots.count()
                generated_classes = ScheduledClass.objects.filter(id__in=generated_class_ids)
                deleted_counts["generated_scheduled_classes"] = generated_classes.count()
                deleted_counts["trainer_raw_rows"] = raw_queryset.count()

                if not dry_run:
                    AttendanceClassMatch.objects.filter(scheduled_class__in=imported_classes).delete()
                    generated_classes.delete()
                    expected_slots.delete()
                    imported_classes.delete()

            else:
                model_config = self.import_models(report_import)
                if not model_config:
                    return Response({"error": "Unsupported report type for rollback."}, status=status.HTTP_400_BAD_REQUEST)

                raw_queryset = model_config["raw_model"].objects.filter(report_import=report_import)
                version_queryset = model_config["version_model"].objects.filter(report_import=report_import)
                current_model = model_config["current_model"]
                created_queryset = current_model.objects.filter(first_seen_import=report_import)
                updated_queryset = current_model.objects.filter(last_seen_import=report_import).exclude(first_seen_import=report_import)

                deleted_counts["raw_rows"] = raw_queryset.count()
                deleted_counts["versions"] = version_queryset.count()
                deleted_counts["current_records_created_by_report"] = created_queryset.count()
                deleted_counts["current_records_updated_by_report"] = updated_queryset.count()

                if updated_queryset.exists():
                    notes.append(
                        "Records updated by this report but created by earlier imports are not reverted yet; "
                        "their import links will be cleared when the report is deleted."
                    )

                if report_import.report_type == ATTENDANCE_REPORT_TYPE:
                    deleted_counts["attendance_matches"] = AttendanceClassMatch.objects.filter(
                        attendance_visit__in=created_queryset,
                    ).count()
                    if not dry_run:
                        AttendanceClassMatch.objects.filter(attendance_visit__in=created_queryset).delete()

                if not dry_run:
                    created_queryset.delete()

            deleted_counts["report_import"] = 1
            if not dry_run:
                report_import.delete()
            else:
                transaction.set_rollback(True)

        return Response({
            "dry_run": dry_run,
            "report_import": report_payload,
            "deleted_counts": deleted_counts,
            "notes": notes,
        })

    @action(detail=False, methods=["post"], url_path="reset-analytics-data")
    def reset_analytics_data(self, request):
        if not settings.ENABLE_ANALYTICS_RESET:
            return Response(
                {"error": "Analytics reset is disabled for this environment."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.data.get("confirmation") != "RESET ANALYTICS DATA":
            return Response(
                {"error": "Invalid confirmation phrase."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        models_to_clear = [
            AttendanceVisitVersion,
            SaleLineVersion,
            ServicePurchaseVersion,
            AttendanceClassMatch,
            ExpectedClassSlot,
            ScheduledClass,
            TrainerAvailabilityRawRow,
            AttendanceVisit,
            SaleLine,
            ServicePurchase,
            AttendanceRawRow,
            SaleRawRow,
            ServicePurchaseRawRow,
            ReportImport,
            PricingOption,
            PaymentMethod,
            ServiceCategory,
            Client,
        ]

        deleted_counts = {}
        with transaction.atomic():
            for model in models_to_clear:
                deleted_counts[model.__name__] = model.objects.count()
                model.objects.all().delete()

        return Response({
            "message": "Analytics data reset completed.",
            "deleted_counts": deleted_counts,
            "preserved": [
                "users",
                "groups",
                "permissions",
                "sites",
                "studios",
                "rooms",
                "staff_members",
                "weekly_room_templates",
                "studio_closures",
            ],
        })

    @action(detail=False, methods=["post"], url_path="repair-sales-by-service-purchases")
    def repair_sales_by_service_purchases(self, request):
        if not settings.ENABLE_PURCHASE_REPAIR:
            return Response(
                {"error": "Analytics maintenance actions are disabled for this environment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        apply_changes = request.data.get("apply") in (True, "true", "True", "1", 1)
        if apply_changes and request.data.get("confirmation") != "REPAIR PURCHASES":
            return Response(
                {"error": "Invalid confirmation phrase."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from analytics.views import add_months, month_start, months_between, rebuild_membership_month
        from core_data.purchase_repair import apply_purchase_repairs, audit_purchase_repairs

        site_id = request.data.get("site") or request.query_params.get("site")
        if not site_id:
            return Response(
                {"error": "Site is required for purchase maintenance."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        scoped_sites = scoped_queryset_for_user(Site.objects.all(), request.user, site_field="id")
        if not scoped_sites.filter(id=site_id).exists():
            return Response({"error": "Site not found."}, status=status.HTTP_404_NOT_FOUND)

        result = (
            apply_purchase_repairs(site_id=site_id)
            if apply_changes
            else audit_purchase_repairs(site_id=site_id)
        )
        result["dry_run"] = not apply_changes
        result["confirmation_required"] = "REPAIR PURCHASES"

        rebuilt = []
        if apply_changes:
            for affected_site_id, range_values in result.get("affected_ranges", {}).items():
                start_month = month_start(parse_iso_date(range_values["from"]))
                end_month = add_months(month_start(parse_iso_date(range_values["to"])), 1)
                for target_month in months_between(start_month, end_month):
                    rebuilt.append({
                        "site_id": int(affected_site_id),
                        "month": target_month.isoformat(),
                        "rows": rebuild_membership_month(int(affected_site_id), target_month),
                    })
        result["rebuilt_snapshots"] = rebuilt
        return Response(result)

    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request):
        uploaded_file = request.FILES.get("file")
        site_id = request.data.get("site")
        studio_id = request.data.get("studio")
        report_type = request.data.get("report_type")

        if not uploaded_file:
            return Response({"error": "File is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not site_id:
            return Response({"error": "Site is required."}, status=status.HTTP_400_BAD_REQUEST)
        if report_type not in SUPPORTED_REPORT_TYPES:
            return Response(
                {"error": f"Unsupported report_type. Supported: {', '.join(SUPPORTED_REPORT_TYPES)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            site = scoped_queryset_for_user(Site.objects.all(), request.user, site_field="id").get(pk=site_id)
        except Site.DoesNotExist:
            return Response({"error": "Site not found."}, status=status.HTTP_404_NOT_FOUND)

        options = {}
        if report_type == "sales_by_service":
            if not studio_id:
                return Response(
                    {"error": "Studio is required for Sales by Service reports."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                studio = scoped_queryset_for_user(
                    Studio.objects.filter(site=site),
                    request.user,
                    studio_field="id",
                ).get(pk=studio_id)
            except Studio.DoesNotExist:
                return Response(
                    {"error": "Studio not found for selected site."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            options["studio"] = studio

        try:
            preview = preview_report(uploaded_file, site, report_type, options=options)
        except Exception as exc:
            return Response({"error": f"Could not parse file: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(mask_preview_money(request, preview))

    @action(detail=False, methods=["post"], url_path="import-file")
    def import_file(self, request):
        uploaded_file = request.FILES.get("file")
        site_id = request.data.get("site")
        studio_id = request.data.get("studio")
        report_type = request.data.get("report_type")

        if not uploaded_file:
            return Response({"error": "File is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not site_id:
            return Response({"error": "Site is required."}, status=status.HTTP_400_BAD_REQUEST)
        if report_type not in SUPPORTED_REPORT_TYPES:
            return Response(
                {"error": f"Unsupported report_type. Supported: {', '.join(SUPPORTED_REPORT_TYPES)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            site = scoped_queryset_for_user(Site.objects.all(), request.user, site_field="id").get(pk=site_id)
        except Site.DoesNotExist:
            return Response({"error": "Site not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            options = {}
            if report_type == "sales_by_service":
                if not studio_id:
                    return Response(
                        {"error": "Studio is required for Sales by Service reports."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    studio = scoped_queryset_for_user(
                        Studio.objects.filter(site=site),
                        request.user,
                        studio_field="id",
                    ).get(pk=studio_id)
                except Studio.DoesNotExist:
                    return Response(
                        {"error": "Studio not found for selected site."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                options["studio"] = studio
            room_capacities_raw = request.data.get("room_capacities")
            if room_capacities_raw:
                try:
                    options["room_capacities"] = json.loads(room_capacities_raw)
                except json.JSONDecodeError:
                    return Response(
                        {"error": "room_capacities must be valid JSON."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            result = import_report(uploaded_file, site, report_type, uploaded_by=request.user, options=options)
            if report_type == "sales_by_service":
                try:
                    from analytics.views import rebuild_membership_months_after_import

                    result["retention_automation"] = rebuild_membership_months_after_import(
                        site.id,
                        result["import"]["report_import_id"],
                    )
                except Exception as exc:
                    result["retention_automation"] = {
                        "skipped": True,
                        "error": f"Retention snapshot automation failed after import: {exc}",
                    }
            auto_reconcile = request.data.get("auto_schedule_reconcile", "true")
            if auto_reconcile in (True, "true", "True", "1", 1):
                try:
                    result["schedule_automation"] = automate_schedule_after_import(site, result, report_type)
                except Exception as exc:
                    result["schedule_automation"] = {
                        "skipped": True,
                        "error": f"Schedule automation failed after import: {exc}",
                    }
        except Exception as exc:
            return Response({"error": f"Could not import file: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        if "preview" in result:
            result["preview"] = mask_preview_money(request, result["preview"])
        return Response(result, status=status.HTTP_201_CREATED)


class ImportedDataFilterMixin:
    search_fields = []
    date_field = None
    scope_site_field = "site_id"
    scope_studio_field = None

    def filter_queryset(self, queryset):
        queryset = scoped_queryset_for_user(
            queryset,
            self.request.user,
            site_field=self.scope_site_field,
            studio_field=self.scope_studio_field,
        )
        site = self.request.query_params.get("site")
        client = self.request.query_params.get("client")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        search = self.request.query_params.get("search")

        if site:
            queryset = queryset.filter(site_id=site)
        if client:
            queryset = queryset.filter(client_id=client)
        if self.date_field and date_from:
            queryset = queryset.filter(**{f"{self.date_field}__gte": date_from})
        if self.date_field and date_to:
            queryset = queryset.filter(**{f"{self.date_field}__lte": date_to})
        if search:
            query = None
            for field in self.search_fields:
                condition = {f"{field}__icontains": search}
                if query is None:
                    from django.db.models import Q

                    query = Q(**condition)
                else:
                    query |= Q(**condition)
            if query is not None:
                queryset = queryset.filter(query)
        return queryset


class AttendanceVisitViewSet(ImportedDataFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = AttendanceVisitSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    read_capability = "can_upload_data"
    date_field = "visit_date"
    scope_studio_field = "visit_studio_id"
    search_fields = ["client__name", "client__mindbody_id", "staff_member__name", "pricing_option__name"]

    def get_queryset(self):
        return self.filter_queryset(
            AttendanceVisit.objects.select_related(
                "site",
                "client",
                "staff_member",
                "visit_studio",
                "sale_studio",
                "service_category",
                "pricing_option",
                "payment_method",
            ).all()
        )


class ScheduledClassViewSet(ImportedDataFilterMixin, viewsets.ModelViewSet):
    serializer_class = ScheduledClassSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    date_field = "class_date"
    scope_studio_field = "studio_id"
    write_capability = "can_edit_data"
    capability_by_action = {
        "reconcile_from_templates": "can_edit_data",
    }
    search_fields = ["name", "studio__name", "room__name", "staff_member__name"]

    def get_queryset(self):
        queryset = (
            ScheduledClass.objects.select_related(
                "site",
                "studio",
                "room",
                "staff_member",
                "template",
                "source_import",
                "source_row",
            )
            .annotate(
                attendance_count=Count("attendance_matches"),
                attended_count=Count(
                    "attendance_matches",
                    filter=Q(
                        attendance_matches__attendance_visit__no_show=False,
                        attendance_matches__attendance_visit__late_cancel=False,
                    ),
                ),
                no_show_count=Count(
                    "attendance_matches",
                    filter=Q(attendance_matches__attendance_visit__no_show=True),
                ),
                late_cancel_count=Count(
                    "attendance_matches",
                    filter=Q(attendance_matches__attendance_visit__late_cancel=True),
                ),
            )
        )
        room = self.request.query_params.get("room")
        studio = self.request.query_params.get("studio")
        staff_member = self.request.query_params.get("staff_member")
        status_value = self.request.query_params.get("status")
        schedule_status = self.request.query_params.get("schedule_status")
        expected_from_template = self.request.query_params.get("expected_from_template")
        if studio:
            queryset = queryset.filter(studio_id=studio)
        if room:
            queryset = queryset.filter(room_id=room)
        if staff_member:
            queryset = queryset.filter(staff_member_id=staff_member)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if schedule_status:
            queryset = queryset.filter(schedule_status=schedule_status)
        if expected_from_template in ("true", "false"):
            queryset = queryset.filter(expected_from_template=expected_from_template == "true")
        return self.filter_queryset(queryset)

    @action(detail=False, methods=["post"], url_path="reconcile-from-templates")
    def reconcile_from_templates(self, request):
        start = parse_iso_date(request.data.get("date_from") or request.query_params.get("date_from"))
        end = parse_iso_date(request.data.get("date_to") or request.query_params.get("date_to"))
        if not start or not end:
            return Response({"error": "date_from and date_to are required."}, status=status.HTTP_400_BAD_REQUEST)
        if end < start:
            return Response({"error": "date_to must be after date_from."}, status=status.HTTP_400_BAD_REQUEST)
        if (end - start).days > 120:
            return Response({"error": "Reconcile at most 120 days at a time."}, status=status.HTTP_400_BAD_REQUEST)

        site_id = request.data.get("site") or request.query_params.get("site")
        if not site_id:
            return Response({"error": "site is required."}, status=status.HTTP_400_BAD_REQUEST)

        stats = reconcile_scheduled_classes_from_templates(
            site_id=site_id,
            studio_id=request.data.get("studio") or request.query_params.get("studio"),
            room_id=request.data.get("room") or request.query_params.get("room"),
            date_from=start,
            date_to=end,
        )
        return Response({
            "date_range": {"from": start.isoformat(), "to": end.isoformat()},
            **stats,
        })


class SaleLineViewSet(ImportedDataFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = SaleLineSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    read_capability = "can_upload_data"
    date_field = "sale_date"
    scope_studio_field = "studio_id"
    search_fields = ["client__name", "client__mindbody_id", "sale_number", "item_name", "payment_method__name"]

    def get_queryset(self):
        queryset = self.filter_queryset(
            SaleLine.objects.select_related("site", "client", "studio", "payment_method").all()
        )
        studio = self.request.query_params.get("studio")
        if studio:
            queryset = queryset.filter(studio_id=studio)
        return queryset


class ServicePurchaseViewSet(ImportedDataFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ServicePurchaseSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    read_capability = "can_upload_data"
    date_field = "sale_date"
    scope_studio_field = "studio_id"
    search_fields = ["client__name", "client__mindbody_id", "pricing_option__name", "service_category__name"]

    def get_queryset(self):
        queryset = self.filter_queryset(
            ServicePurchase.objects.select_related("site", "studio", "client", "service_category", "pricing_option").all()
        )
        studio = self.request.query_params.get("studio")
        if studio:
            queryset = queryset.filter(studio_id=studio)
        return queryset


class RawRowFilterMixin:
    scope_site_field = "site_id"
    scope_studio_field = None

    def filter_queryset(self, queryset):
        queryset = scoped_queryset_for_user(
            queryset,
            self.request.user,
            site_field=self.scope_site_field,
            studio_field=self.scope_studio_field,
        )
        site = self.request.query_params.get("site")
        report_import = self.request.query_params.get("report_import")
        is_valid = self.request.query_params.get("is_valid")
        search = self.request.query_params.get("search")
        if site:
            queryset = queryset.filter(site_id=site)
        if report_import:
            queryset = queryset.filter(report_import_id=report_import)
        if is_valid in ("true", "false"):
            queryset = queryset.filter(is_valid=is_valid == "true")
        if search:
            queryset = queryset.filter(normalized_payload__icontains=search)
        return queryset


class AttendanceRawRowViewSet(RawRowFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = AttendanceRawRowSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    read_capability = "can_upload_data"

    def get_queryset(self):
        return self.filter_queryset(AttendanceRawRow.objects.select_related("site", "report_import").all())


class TrainerAvailabilityRawRowViewSet(RawRowFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = TrainerAvailabilityRawRowSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    read_capability = "can_upload_data"

    def get_queryset(self):
        return self.filter_queryset(
            TrainerAvailabilityRawRow.objects.select_related("site", "report_import").all()
        )


class AttendanceClassMatchViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AttendanceClassMatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = AttendanceClassMatch.objects.select_related(
            "attendance_visit",
            "attendance_visit__client",
            "scheduled_class",
        ).all()
        queryset = scoped_queryset_for_user(
            queryset,
            self.request.user,
            site_field="scheduled_class__site_id",
            studio_field="scheduled_class__studio_id",
        )
        scheduled_class = self.request.query_params.get("scheduled_class")
        match_method = self.request.query_params.get("match_method")
        if scheduled_class:
            queryset = queryset.filter(scheduled_class_id=scheduled_class)
        if match_method:
            queryset = queryset.filter(match_method=match_method)
        return queryset


class SaleRawRowViewSet(RawRowFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = SaleRawRowSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    read_capability = "can_upload_data"

    def get_queryset(self):
        return self.filter_queryset(SaleRawRow.objects.select_related("site", "report_import").all())


class ServicePurchaseRawRowViewSet(RawRowFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ServicePurchaseRawRowSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    read_capability = "can_upload_data"
    scope_studio_field = "studio_id"

    def get_queryset(self):
        queryset = self.filter_queryset(ServicePurchaseRawRow.objects.select_related("site", "studio", "report_import").all())
        studio = self.request.query_params.get("studio")
        if studio:
            queryset = queryset.filter(studio_id=studio)
        return queryset


class LoginLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LoginLogSerializer
    permission_classes = [IsAuthenticated, CapabilityPermission]
    required_capability = "can_view_admin_logs"

    def get_queryset(self):
        queryset = LoginLog.objects.select_related("user").all()
        user_id = self.request.query_params.get("user")
        login_type = self.request.query_params.get("login_type")
        success = self.request.query_params.get("success")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        search = self.request.query_params.get("search")
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if login_type:
            queryset = queryset.filter(login_type=login_type)
        if success in ("true", "false"):
            queryset = queryset.filter(success=success == "true")
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(ip_address__icontains=search)
            )
        return queryset


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    email = request.data.get("email")
    password = request.data.get("password")
    login_type = request.data.get("login_type", "main")

    if not email or not password:
        return Response({"message": "Email and password are required"}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(request, email=email, password=password)
    ip_address = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")

    if user:
        LoginLog.objects.create(
            user=user,
            ip_address=ip_address,
            login_type=login_type,
            user_agent=user_agent,
            success=True,
        )
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_staff": user.is_staff,
                "permissions": list(user.get_all_permissions()),
                "access": resolve_access_payload(user),
                "image": user.image,
                "message": "Login successful",
            }
        )

    try:
        failed_user = User.objects.get(email=email)
        LoginLog.objects.create(
            user=failed_user,
            ip_address=ip_address,
            login_type=login_type,
            user_agent=user_agent,
            success=False,
        )
    except User.DoesNotExist:
        pass

    return Response({"message": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(["POST"])
@permission_classes([AllowAny])
def validate_token_view(request):
    token_key = request.data.get("token")
    if not token_key:
        return Response({"message": "Token is required"}, status=status.HTTP_400_BAD_REQUEST)

    valid = Token.objects.filter(key=token_key).exists()
    return Response({"valid": valid}, status=status.HTTP_200_OK if valid else status.HTTP_401_UNAUTHORIZED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    Token.objects.filter(user=request.user).delete()
    LoginLog.objects.create(
        user=request.user,
        ip_address=get_client_ip(request),
        login_type="logout",
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        success=True,
    )
    return Response({"message": "Logout successful"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_permissions(request):
    return Response(resolve_access_payload(request.user))


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def me_language(request):
    language = request.data.get("language")
    valid_languages = {choice[0] for choice in UserAccessProfile.LANGUAGE_CHOICES}
    if language not in valid_languages:
        return Response({"error": "Invalid language."}, status=status.HTTP_400_BAD_REQUEST)

    profile = get_or_create_user_access_profile(request.user)
    profile.language = language
    profile.save(update_fields=["language"])
    return Response(resolve_access_payload(request.user))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def all_users(request):
    if not user_has_capability(request.user, "can_manage_users"):
        return Response({"error": "You do not have permission to perform this action."}, status=status.HTTP_403_FORBIDDEN)
    users = User.objects.filter(is_active=True).order_by("first_name", "last_name", "email")
    return Response(UserSerializer(users, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_groups(request):
    if not user_has_capability(request.user, "can_manage_users"):
        return Response({"error": "You do not have permission to perform this action."}, status=status.HTTP_403_FORBIDDEN)
    return Response(GroupSerializer(Group.objects.all().order_by("name"), many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "ok", "service": "beness-analytics-api"})
