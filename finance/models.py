from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


currency_validator = RegexValidator(r"^[A-Z]{3}$", "Use a three-letter uppercase currency code.")


class Company(models.Model):
    name = models.CharField(max_length=180)
    site = models.ForeignKey("core_data.Site", on_delete=models.PROTECT, related_name="finance_companies")
    default_currency = models.CharField(max_length=3, validators=[currency_validator])
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.UniqueConstraint(fields=["site", "name"], name="finance_company_site_name")]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.pk and self.accounts.exists():
            previous = type(self).objects.get(pk=self.pk)
            if previous.site_id != self.site_id:
                raise ValidationError({"site": "A company with accounts cannot be moved to another site."})


class Account(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="accounts")
    name = models.CharField(max_length=180)
    kind = models.CharField(max_length=10, choices=[("bank", "Bank"), ("cash", "Cash")], default="bank")
    currency = models.CharField(max_length=3, validators=[currency_validator])
    bank_name = models.CharField(max_length=150, blank=True)
    studios = models.ManyToManyField("core_data.Studio", blank=True, related_name="finance_accounts")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.UniqueConstraint(fields=["company", "name"], name="finance_account_company_name")]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.company_id != self.company_id:
                raise ValidationError({"company": "An account cannot be moved to another company."})


class AccessChange(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    target_type = models.CharField(max_length=30)
    target_id = models.PositiveBigIntegerField()
    target_label = models.CharField(max_length=180)
    operation = models.CharField(max_length=10)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]


def validate_account_studios(account, studios):
    if any(studio.site_id != account.company.site_id for studio in studios):
        raise ValidationError("Account studios must belong to the company's site.")
