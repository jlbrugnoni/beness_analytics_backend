from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import scoped_companies
from .catalog_transfer import export_catalog, read_csv, require_catalog_access, starting_rows, transfer_catalog
from .models import Company
from .permissions import FinancePermission


class CategoryCatalog(APIView):
    permission_classes = [IsAuthenticated, FinancePermission]
    required_finance_capability = 'can_import_finance_migration'
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def company(self, request, company_id):
        company = get_object_or_404(scoped_companies(Company.objects.all(), request.user), pk=company_id)
        require_catalog_access(request.user, company)
        return company

    def get(self, request, company_id):
        return export_catalog(self.company(request, company_id))

    def post(self, request, company_id):
        company = self.company(request, company_id)
        source = request.data.get('source', 'csv')
        if source not in ('csv', 'starting'):
            raise serializers.ValidationError({'source': 'Use csv or starting.'})
        rows = starting_rows() if source == 'starting' else read_csv(request.FILES.get('file'))
        return Response(transfer_catalog(company, request.user, rows, mode=request.data.get('mode', 'merge'),
            source=source, expected_plan=request.data.get('expected_plan')))
