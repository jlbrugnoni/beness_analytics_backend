from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Center, ClassType, Client, CustomUser, Instructor, LoginLog, ReportImport, Room


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


@admin.register(Center)
class CenterAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "active")
    search_fields = ("name", "city")
    list_filter = ("active",)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "center", "capacity", "active")
    search_fields = ("name", "center__name")
    list_filter = ("center", "active")


admin.site.register(Instructor)
admin.site.register(Client)
admin.site.register(ClassType)
admin.site.register(ReportImport)
admin.site.register(LoginLog)
