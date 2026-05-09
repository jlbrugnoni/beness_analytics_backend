from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .importers import ATTENDANCE_REPORT_TYPE, import_attendance_report, preview_attendance_report
from .models import Client, LoginLog, PaymentMethod, PricingOption, ReportImport, ServiceCategory, Site, StaffMember, Studio
from .serializers import (
    ChangePasswordSerializer,
    ClientSerializer,
    GroupSerializer,
    LoginLogSerializer,
    PaymentMethodSerializer,
    PricingOptionSerializer,
    ReportImportSerializer,
    ServiceCategorySerializer,
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

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request):
        uploaded_file = request.FILES.get("file")
        site_id = request.data.get("site")
        report_type = request.data.get("report_type")

        if not uploaded_file:
            return Response({"error": "File is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not site_id:
            return Response({"error": "Site is required."}, status=status.HTTP_400_BAD_REQUEST)
        if report_type != ATTENDANCE_REPORT_TYPE:
            return Response(
                {"error": f"Unsupported report_type. Currently supported: {ATTENDANCE_REPORT_TYPE}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            site = Site.objects.get(pk=site_id)
        except Site.DoesNotExist:
            return Response({"error": "Site not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            preview = preview_attendance_report(uploaded_file, site)
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
        if report_type != ATTENDANCE_REPORT_TYPE:
            return Response(
                {"error": f"Unsupported report_type. Currently supported: {ATTENDANCE_REPORT_TYPE}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            site = Site.objects.get(pk=site_id)
        except Site.DoesNotExist:
            return Response({"error": "Site not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            result = import_attendance_report(uploaded_file, site, uploaded_by=request.user)
        except Exception as exc:
            return Response({"error": f"Could not import file: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_201_CREATED)


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
