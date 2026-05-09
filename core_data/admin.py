from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    AttendanceRawRow,
    AttendanceVisit,
    AttendanceVisitVersion,
    Client,
    CustomUser,
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


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "username", "image")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "first_name", "last_name"),
            },
        ),
    )
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    readonly_fields = ("last_login", "date_joined")


admin.site.register(ReportImport)
admin.site.register(LoginLog)


admin.site.register(Site)
admin.site.register(Studio)
admin.site.register(Client)
admin.site.register(StaffMember)
admin.site.register(ServiceCategory)
admin.site.register(PricingOption)
admin.site.register(PaymentMethod)
admin.site.register(AttendanceRawRow)
admin.site.register(AttendanceVisit)
admin.site.register(AttendanceVisitVersion)
admin.site.register(SaleRawRow)
admin.site.register(SaleLine)
admin.site.register(SaleLineVersion)
admin.site.register(ServicePurchaseRawRow)
admin.site.register(ServicePurchase)
admin.site.register(ServicePurchaseVersion)
