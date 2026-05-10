from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .importers import SUPPORTED_REPORT_TYPES, import_report, preview_report
from .models import (
    AttendanceRawRow,
    AttendanceVisit,
    AttendanceVisitVersion,
    Client,
    LoginLog,
    PaymentMethod,
    PricingOption,
    ReportImport,
    SaleLine,
    SaleLineVersion,
    SaleRawRow,
    ServiceCategory,
    ServicePurchase,
    ServicePurchaseRawRow,
    ServicePurchaseVersion,
    Site,
    StaffMember,
    Studio,
)
from .serializers import (
    AttendanceRawRowSerializer,
    AttendanceVisitSerializer,
    ChangePasswordSerializer,
    ClientSerializer,
    GroupSerializer,
    LoginLogSerializer,
    PaymentMethodSerializer,
    PricingOptionSerializer,
    ReportImportSerializer,
    SaleLineSerializer,
    SaleRawRowSerializer,
    ServiceCategorySerializer,
    ServicePurchaseRawRowSerializer,
    ServicePurchaseSerializer,
    SiteSerializer,
    StaffMemberSerializer,
    StudioSerializer,
    UserSerializer,
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
            result = import_report(uploaded_file, site, report_type, uploaded_by=request.user)
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
