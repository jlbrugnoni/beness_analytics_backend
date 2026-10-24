from rest_framework.permissions import BasePermission
from .access import can_use_finance


class FinancePermission(BasePermission):
    message = "Finance is unavailable or you do not have the required financial access."

    def has_permission(self, request, view):
        return can_use_finance(request.user, getattr(view, "required_finance_capability", "can_view_finance"))
