from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .capabilities import FINANCE_CAPABILITIES

from .models import (
    AttendanceRawRow,
    AttendanceVisit,
    AttendanceVisitVersion,
    Client,
    CustomUser,
    GroupAccessProfile,
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
    UserAccessProfile,
)


class UserAccessProfileInline(admin.StackedInline):
    model = UserAccessProfile
    can_delete = False
    extra = 0
    filter_horizontal = ("allowed_sites", "allowed_studios")
    fieldsets = (
        (
            "Data Scope",
            {
                "fields": (
                    "language",
                    "allowed_sites",
                    "allowed_studios",
                )
            },
        ),
        (
            "Extra Capabilities",
            {
                "fields": (
                    "can_view_money",
                    "can_upload_data",
                    "can_edit_data",
                    "can_reset_data",
                    "can_manage_users",
                    "can_view_admin_logs",
                )
            },
        ),
    ) + (("Finance grants", {"fields": FINANCE_CAPABILITIES}),)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    inlines = (UserAccessProfileInline,)
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

    def save_formset(self, request, form, formset, change):
        if formset.model is not UserAccessProfile:
            return super().save_formset(request, form, formset, change)
        from finance.audit import access_snapshot, log_access_change
        profiles = formset.save(commit=False)
        changes = []
        for profile in profiles:
            previous = UserAccessProfile.objects.select_for_update().filter(pk=profile.pk).first()
            before = access_snapshot(previous) if previous else {}
            profile.revision = previous.revision + 1 if previous else 1
            profile.save()
            changes.append((profile, before))
        formset.save_m2m()
        for profile, before in changes:
            log_access_change(request.user, profile, "update" if before else "create", before, access_snapshot(profile))


class AccessProfileAdminAuditMixin:
    def save_model(self, request, obj, form, change):
        from finance.audit import access_snapshot
        previous = type(obj).objects.select_for_update().filter(pk=obj.pk).first() if change else None
        obj._access_before = access_snapshot(previous) if previous else {}
        obj.revision = previous.revision + 1 if previous else 1
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        from finance.audit import access_snapshot, log_access_change
        super().save_related(request, form, formsets, change)
        obj = form.instance
        log_access_change(request.user, obj, "update" if change else "create", obj._access_before, access_snapshot(obj))


@admin.register(GroupAccessProfile)
class GroupAccessProfileAdmin(AccessProfileAdminAuditMixin, admin.ModelAdmin):
    readonly_fields = ("revision",)
    list_display = (
        "group",
        "can_view_money",
        "can_upload_data",
        "can_edit_data",
        "can_reset_data",
        "can_manage_users",
        "can_view_admin_logs",
    )
    list_filter = (
        "can_view_money",
        "can_upload_data",
        "can_edit_data",
        "can_reset_data",
        "can_manage_users",
        "can_view_admin_logs",
    )
    search_fields = ("group__name",)


@admin.register(UserAccessProfile)
class UserAccessProfileAdmin(AccessProfileAdminAuditMixin, admin.ModelAdmin):
    readonly_fields = ("revision",)
    filter_horizontal = ("allowed_sites", "allowed_studios")
    list_display = (
        "user",
        "language",
        "can_view_money",
        "can_upload_data",
        "can_edit_data",
        "can_reset_data",
        "can_manage_users",
        "can_view_admin_logs",
    )
    list_filter = (
        "can_view_money",
        "can_upload_data",
        "can_edit_data",
        "can_reset_data",
        "can_manage_users",
        "can_view_admin_logs",
        "language",
        "allowed_sites",
        "allowed_studios",
    )
    search_fields = ("user__email", "user__first_name", "user__last_name")


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
