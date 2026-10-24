from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from .models import Account, validate_account_studios
from core_data.models import Studio


@receiver(m2m_changed, sender=Account.studios.through)
def validate_membership(sender, instance, action, reverse, pk_set, **kwargs):
    if action != "pre_add" or not pk_set:
        return
    if reverse:
        for account in Account.objects.filter(pk__in=pk_set).select_related("company"):
            validate_account_studios(account, [instance])
    else:
        validate_account_studios(instance, Studio.objects.filter(pk__in=pk_set))
