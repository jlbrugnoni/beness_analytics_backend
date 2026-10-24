from django.conf import settings
from core_data.access import get_or_create_user_access_profile, user_has_capability, user_has_global_access


def can_use_finance(user, capability="can_view_finance"):
    return bool(settings.FINANCE_ENABLED and user_has_capability(user, "can_view_money")
                and user_has_capability(user, "can_view_finance")
                and user_has_capability(user, capability))


def allowed_site_ids(user):
    """Existing studio restrictions take precedence over site-wide selection."""
    profile = get_or_create_user_access_profile(user)
    studios = profile.allowed_studios.all()
    if studios.exists():
        return set(studios.values_list("site_id", flat=True))
    return set(profile.allowed_sites.values_list("pk", flat=True))


def scoped_companies(queryset, user):
    if not can_use_finance(user):
        return queryset.none()
    if user_has_global_access(user):
        return queryset
    return queryset.filter(site_id__in=allowed_site_ids(user))


def can_view_full_account(user, account):
    if not can_use_finance(user, "can_view_finance_bank_accounts"):
        return False
    if user_has_global_access(user):
        return True
    profile = get_or_create_user_access_profile(user)
    studio_ids = set(profile.allowed_studios.values_list("pk", flat=True))
    if studio_ids:
        participating = set(account.studios.values_list("pk", flat=True))
        return bool(participating and participating <= studio_ids
                    and account.company.site_id in allowed_site_ids(user))
    return profile.allowed_sites.filter(pk=account.company.site_id).exists()


def can_view_sensitive_detail(user):
    # Callers must also check their record/company/studio scope.
    return can_use_finance(user, "can_view_sensitive_finance")


def configuration_sites(user):
    """Company-wide settings need site-wide authority, not a partial studio grant."""
    from core_data.models import Site
    sites = Site.objects.all()
    if not can_use_finance(user, "can_manage_finance_settings"):
        return sites.none()
    if user_has_global_access(user):
        return sites
    profile = get_or_create_user_access_profile(user)
    if profile.allowed_studios.exists():
        return sites.none()
    return sites.filter(pk__in=profile.allowed_sites.values_list("pk", flat=True))
