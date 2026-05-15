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

from .importers import SUPPORTED_REPORT_TYPES, import_report, preview_report
from .models import (
    AttendanceRawRow,
    AttendanceClassMatch,
    AttendanceVisit,
    AttendanceVisitVersion,
    Client,
    ExpectedClassSlot,
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
    WeeklyRoomTemplate,
)
from .serializers import (
    AttendanceClassMatchSerializer,
    AttendanceRawRowSerializer,
    AttendanceVisitSerializer,
    ChangePasswordSerializer,
    ClientSerializer,
    ExpectedClassSlotSerializer,
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
    UserSerializer,
    WeeklyRoomTemplateSerializer,
)


User = get_user_model()


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class UserViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        users = User.objects.filter(is_superuser=False).order_by("first_name", "last_name", "email")
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


class SiteViewSet(viewsets.ModelViewSet):
    queryset = Site.objects.all()
    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated]


class StudioViewSet(viewsets.ModelViewSet):
    queryset = Studio.objects.select_related("site").all()
    serializer_class = StudioSerializer
    permission_classes = [IsAuthenticated]


class RoomViewSet(viewsets.ModelViewSet):
    serializer_class = RoomSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Room.objects.select_related("site", "studio").all()
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
    queryset = Client.objects.select_related("site").all()
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]


class StaffMemberViewSet(viewsets.ModelViewSet):
    queryset = StaffMember.objects.select_related("site").all()
    serializer_class = StaffMemberSerializer
    permission_classes = [IsAuthenticated]


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    queryset = ServiceCategory.objects.select_related("site").all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsAuthenticated]


class PricingOptionViewSet(viewsets.ModelViewSet):
    queryset = PricingOption.objects.select_related("site", "service_category").all()
    serializer_class = PricingOptionSerializer
    permission_classes = [IsAuthenticated]


class PaymentMethodViewSet(viewsets.ModelViewSet):
    queryset = PaymentMethod.objects.select_related("site").all()
    serializer_class = PaymentMethodSerializer
    permission_classes = [IsAuthenticated]


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


def find_matching_scheduled_class(template, slot_date):
    candidates = ScheduledClass.objects.filter(
        site=template.site,
        studio=template.studio,
        room=template.room,
        class_date=slot_date,
        start_time=template.start_time,
        end_time=template.end_time,
    ).exclude(status=ScheduledClass.STATUS_CANCELLED)
    if template.staff_member_id:
        exact = candidates.filter(staff_member_id=template.staff_member_id).first()
        if exact:
            return exact
    if candidates.count() == 1:
        return candidates.first()
    return None


def generate_expected_slots(site_id=None, studio_id=None, room_id=None, date_from=None, date_to=None):
    templates = WeeklyRoomTemplate.objects.select_related("site", "studio", "room", "staff_member").filter(active=True)
    if site_id:
        templates = templates.filter(site_id=site_id)
    if studio_id:
        templates = templates.filter(studio_id=studio_id)
    if room_id:
        templates = templates.filter(room_id=room_id)

    stats = {"created": 0, "updated": 0, "matched": 0, "missing": 0}
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
            expected_slot, created = ExpectedClassSlot.objects.update_or_create(
                site=template.site,
                room=template.room,
                slot_date=current_date,
                start_time=template.start_time,
                end_time=template.end_time,
                defaults={
                    "studio": template.studio,
                    "template": template,
                    "scheduled_class": scheduled_class,
                    "staff_member": template.staff_member,
                    "name": template.name,
                    "capacity": template.capacity,
                    "status": status_value,
                },
            )
            stats["created" if created else "updated"] += 1
            stats["matched" if expected_slot.scheduled_class_id else "missing"] += 1
        current_date += timedelta(days=1)
    return stats


class WeeklyRoomTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = WeeklyRoomTemplateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = WeeklyRoomTemplate.objects.select_related("site", "studio", "room", "staff_member").all()
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


class ExpectedClassSlotViewSet(viewsets.ModelViewSet):
    serializer_class = ExpectedClassSlotSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ExpectedClassSlot.objects.select_related(
            "site",
            "studio",
            "room",
            "template",
            "scheduled_class",
            "staff_member",
        ).all()
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
        return Response({"date_range": {"from": start.isoformat(), "to": end.isoformat()}, **stats})


class StudioClosureViewSet(viewsets.ModelViewSet):
    serializer_class = StudioClosureSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = StudioClosure.objects.select_related("site", "studio", "room").all()
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
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        queryset = ReportImport.objects.select_related("uploaded_by").all()
        report_type = self.request.query_params.get("report_type")
        status_value = self.request.query_params.get("status")
        search = self.request.query_params.get("search")
        if report_type:
            queryset = queryset.filter(report_type=report_type)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if search:
            queryset = queryset.filter(file_name__icontains=search)
        return queryset

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

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

    @action(detail=False, methods=["post"], url_path="reset-analytics-data")
    def reset_analytics_data(self, request):
        if not settings.ENABLE_ANALYTICS_RESET:
            return Response(
                {"error": "Analytics reset is disabled for this environment."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"error": "Only staff users can reset analytics data."},
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
            StaffMember,
            ServiceCategory,
            Client,
            Studio,
        ]

        deleted_counts = {}
        with transaction.atomic():
            for model in models_to_clear:
                deleted_counts[model.__name__] = model.objects.count()
                model.objects.all().delete()

        return Response({
            "message": "Analytics data reset completed.",
            "deleted_counts": deleted_counts,
            "preserved": ["users", "groups", "permissions", "sites"],
        })

    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request):
        uploaded_file = request.FILES.get("file")
        site_id = request.data.get("site")
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
            site = Site.objects.get(pk=site_id)
        except Site.DoesNotExist:
            return Response({"error": "Site not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            preview = preview_report(uploaded_file, site, report_type)
        except Exception as exc:
            return Response({"error": f"Could not parse file: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(preview)

    @action(detail=False, methods=["post"], url_path="import-file")
    def import_file(self, request):
        uploaded_file = request.FILES.get("file")
        site_id = request.data.get("site")
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
            site = Site.objects.get(pk=site_id)
        except Site.DoesNotExist:
            return Response({"error": "Site not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            options = {}
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
        except Exception as exc:
            return Response({"error": f"Could not import file: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_201_CREATED)


class ImportedDataFilterMixin:
    search_fields = []
    date_field = None

    def filter_queryset(self, queryset):
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
    permission_classes = [IsAuthenticated]
    date_field = "visit_date"
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
    permission_classes = [IsAuthenticated]
    date_field = "class_date"
    search_fields = ["name", "studio__name", "room__name", "staff_member__name"]

    def get_queryset(self):
        queryset = (
            ScheduledClass.objects.select_related(
                "site",
                "studio",
                "room",
                "staff_member",
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
        if studio:
            queryset = queryset.filter(studio_id=studio)
        if room:
            queryset = queryset.filter(room_id=room)
        if staff_member:
            queryset = queryset.filter(staff_member_id=staff_member)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return self.filter_queryset(queryset)


class SaleLineViewSet(ImportedDataFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = SaleLineSerializer
    permission_classes = [IsAuthenticated]
    date_field = "sale_date"
    search_fields = ["client__name", "client__mindbody_id", "sale_number", "item_name", "payment_method__name"]

    def get_queryset(self):
        return self.filter_queryset(
            SaleLine.objects.select_related("site", "client", "studio", "payment_method").all()
        )


class ServicePurchaseViewSet(ImportedDataFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ServicePurchaseSerializer
    permission_classes = [IsAuthenticated]
    date_field = "sale_date"
    search_fields = ["client__name", "client__mindbody_id", "pricing_option__name", "service_category__name"]

    def get_queryset(self):
        return self.filter_queryset(
            ServicePurchase.objects.select_related("site", "client", "service_category", "pricing_option").all()
        )


class RawRowFilterMixin:
    def filter_queryset(self, queryset):
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
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.filter_queryset(AttendanceRawRow.objects.select_related("site", "report_import").all())


class TrainerAvailabilityRawRowViewSet(RawRowFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = TrainerAvailabilityRawRowSerializer
    permission_classes = [IsAuthenticated]

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
        scheduled_class = self.request.query_params.get("scheduled_class")
        match_method = self.request.query_params.get("match_method")
        if scheduled_class:
            queryset = queryset.filter(scheduled_class_id=scheduled_class)
        if match_method:
            queryset = queryset.filter(match_method=match_method)
        return queryset


class SaleRawRowViewSet(RawRowFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = SaleRawRowSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.filter_queryset(SaleRawRow.objects.select_related("site", "report_import").all())


class ServicePurchaseRawRowViewSet(RawRowFilterMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ServicePurchaseRawRowSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.filter_queryset(ServicePurchaseRawRow.objects.select_related("site", "report_import").all())


class LoginLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LoginLog.objects.select_related("user").all()
    serializer_class = LoginLogSerializer
    permission_classes = [IsAuthenticated]


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
def all_users(request):
    users = User.objects.filter(is_active=True).order_by("first_name", "last_name", "email")
    return Response(UserSerializer(users, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_groups(request):
    return Response(GroupSerializer(Group.objects.all().order_by("name"), many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "ok", "service": "beness-analytics-api"})
