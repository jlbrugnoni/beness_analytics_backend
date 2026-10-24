from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from core_data.access import resolve_access_payload
from .access import can_view_full_account, scoped_companies
from .models import Account, Company
from .permissions import FinancePermission
from .serializers import AccountSerializer, CompanySerializer


class FinanceOverview(APIView):
    permission_classes = [IsAuthenticated, FinancePermission]

    def get(self, request):
        companies = scoped_companies(Company.objects.select_related("site"), request.user)
        return Response({"stage": "foundation", "companies": CompanySerializer(companies, many=True).data,
                         "capabilities": resolve_access_payload(request.user)["capabilities"]})


class CompanyViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, FinancePermission]
    serializer_class = CompanySerializer

    def get_queryset(self):
        return scoped_companies(Company.objects.select_related("site"), self.request.user)


class AccountViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, FinancePermission]
    required_finance_capability = "can_view_finance_bank_accounts"
    serializer_class = AccountSerializer

    def get_queryset(self):
        companies = scoped_companies(Company.objects.all(), self.request.user)
        candidates = Account.objects.filter(company__in=companies).select_related("company").prefetch_related("studios")
        visible = [account.pk for account in candidates if can_view_full_account(self.request.user, account)]
        return Account.objects.filter(pk__in=visible).prefetch_related("studios")
