from django.db.models import Q
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .access import scoped_queryset_for_user, user_has_capability
from .models import ServicePurchase, ServicePurchaseMatchReview
from .permissions import CapabilityPermission
from .purchase_matching import resolve_purchase_review


def purchase_data(purchase, can_view_money):
    return {
        "id": purchase.pk, "service": purchase.pricing_option.name,
        "sale_date": purchase.sale_date, "activation_date": purchase.activation_date,
        "expiration_date": purchase.expiration_date, "quantity": purchase.quantity,
        "total_amount": purchase.total_amount if can_view_money else None,
        "cash_equivalent": purchase.cash_equivalent if can_view_money else None,
        "non_cash_equivalent": purchase.non_cash_equivalent if can_view_money else None,
        "activation_offset_days": purchase.activation_offset_days,
        "updated_at": purchase.updated_at,
        "last_import_id": purchase.last_seen_import_id,
    }


class PurchaseReviewSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    studio_name = serializers.CharField(source="studio.name", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    client_mindbody_id = serializers.CharField(source="client.mindbody_id", read_only=True)
    incoming = serializers.SerializerMethodField()
    file_name = serializers.CharField(source="latest_raw_row.report_import.file_name", read_only=True)
    report_import_id = serializers.IntegerField(source="latest_raw_row.report_import_id", read_only=True)
    row_number = serializers.IntegerField(source="latest_raw_row.row_number", read_only=True)
    resolved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ServicePurchaseMatchReview
        fields = ["id", "site", "site_name", "studio", "studio_name", "client_name", "client_mindbody_id",
                  "status", "reason", "latest_raw_row", "file_name", "report_import_id", "row_number",
                  "incoming", "purchase", "decision_history", "resolved_by_name", "resolved_at", "note", "created_at", "updated_at"]
        read_only_fields = fields

    def get_incoming(self, obj):
        payload = obj.latest_raw_row.normalized_payload
        money = user_has_capability(self.context["request"].user, "can_view_money")
        return {
            "service": payload.get("Nombre"), "sale_date": payload.get("_sale_date"),
            "activation_date": payload.get("_activation_date"), "expiration_date": payload.get("_expiration_date"),
            "quantity": payload.get("_quantity"), "activation_offset_days": payload.get("_activation_offset_days"),
            **{key: payload.get(f"_{key}") if money else None for key in ("total_amount", "cash_equivalent", "non_cash_equivalent")},
        }

    def get_resolved_by_name(self, obj):
        return obj.resolved_by.email if obj.resolved_by else None


class ServicePurchaseMatchReviewViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, CapabilityPermission]
    required_capability = "can_upload_data"
    serializer_class = PurchaseReviewSerializer

    def get_queryset(self):
        queryset = scoped_queryset_for_user(
            ServicePurchaseMatchReview.objects.select_related(
                "site", "studio", "client", "latest_raw_row__report_import", "resolved_by",
            ), self.request.user, studio_field="studio_id",
        )
        # Scope retrieval by access only; list filters must not affect resolution.
        if self.action == "list":
            state = self.request.query_params.get("status", "pending")
            if state != "all":
                queryset = queryset.filter(status=state)
            for field in ("site", "studio"):
                value = self.request.query_params.get(field)
                if value:
                    if not value.isdigit():
                        raise serializers.ValidationError({field: "Expected a numeric ID."})
                    queryset = queryset.filter(**{f"{field}_id": value})
            search = self.request.query_params.get("search", "").strip()
            if search:
                queryset = queryset.filter(Q(client__name__icontains=search) | Q(client__mindbody_id__icontains=search))
        return queryset

    @action(detail=True, methods=["get"])
    def candidates(self, request, pk=None):
        review = self.get_object()
        queryset = ServicePurchase.objects.filter(
            site=review.site, studio=review.studio, client=review.client,
        ).select_related("pricing_option").order_by("-sale_date", "-id")
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(pricing_option__name__icontains=search) | Q(sale_date__icontains=search))
        page = self.paginate_queryset(queryset)
        money = user_has_capability(request.user, "can_view_money")
        return self.get_paginated_response([purchase_data(purchase, money) for purchase in page])

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        review = self.get_object()
        resolved = resolve_purchase_review(review.id, review.studio_id, request.user, request.data)
        return Response(self.get_serializer(resolved).data)
