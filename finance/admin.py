from django.contrib import admin
from django import forms
from .models import AccessChange, Account, Category, Company, ConfigurationChange, Terminal, validate_account_studios


class TechnicalAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    has_add_permission = has_change_permission = has_delete_permission = has_view_permission


class ConfigurationAdmin(TechnicalAdmin):
    # The application editor is the audited, revision-aware write path.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = "__all__"

    def clean(self):
        data = super().clean()
        if data.get("company") and data.get("studios") is not None:
            validate_account_studios(Account(company=data["company"]), data["studios"])
        return data


@admin.register(Account)
class AccountAdmin(ConfigurationAdmin):
    form = AccountForm
    filter_horizontal = ("studios",)
    list_display = ("name", "company", "kind", "currency", "active")


admin.site.register(Company, ConfigurationAdmin)
admin.site.register(Terminal, ConfigurationAdmin)
admin.site.register(Category, ConfigurationAdmin)


@admin.register(AccessChange)
class AccessChangeAdmin(TechnicalAdmin):
    list_display = ("created_at", "actor", "target_type", "target_label", "operation")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConfigurationChange)
class ConfigurationChangeAdmin(AccessChangeAdmin):
    list_display = ("created_at", "actor", "target_type", "target_label")
