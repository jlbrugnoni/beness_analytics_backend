from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser
from .models import (Objective,
                     Position,
                     Prop,
                     Machine,
                     Exercise,
                     GeneralRoutineAssignment,
                     Spring,
                     ExerciseSpringConfig,
                     Routine,
                     RoutineExercise,
                     RoutineSession,
                     SessionSeries,
                     Room,
                     Center,
                        Tag
                     )


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "username")}),
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
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                ),
            },
        ),
    )
    list_display = ("email", "first_name", "last_name", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)

    # Mark these fields as read-only
    readonly_fields = ("last_login", "date_joined")


admin.site.register(Objective)
admin.site.register(Position)
admin.site.register(Prop)
admin.site.register(Machine)
admin.site.register(Spring)


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "image", "video", "active")
    search_fields = ("=id", "code", "name", "image", "video")
    list_filter = ("active",)
    readonly_fields = ("id",)


@admin.register(Routine)
class RoutineAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "duration", "on_edit", "active")
    search_fields = ("=id", "name")
    readonly_fields = ("id",)


@admin.register(RoutineExercise)
class RoutineExerciseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "routine_id",
        "routine",
        "exercise_id",
        "exercise",
        "order",
        "repetitions",
        "duration_seconds",
    )
    search_fields = ("=id", "=routine__id", "routine__name", "=exercise__id", "exercise__name")
    raw_id_fields = ("routine", "exercise")
    readonly_fields = ("id",)


# admin.site.register(ExerciseSpringConfig)


@admin.register(RoutineSession)
class RoutineSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "routine_id", "routine", "room", "scheduled_at", "state")
    search_fields = ("=id", "name", "=routine__id", "routine__name", "room__name")
    raw_id_fields = ("routine", "room", "user", "session_series", "daily_routine_assignment")
    readonly_fields = ("id",)


admin.site.register(GeneralRoutineAssignment)
admin.site.register(SessionSeries)
admin.site.register(Room)
admin.site.register(Center)
admin.site.register(Tag)
