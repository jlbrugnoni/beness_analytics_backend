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
    revision = models.PositiveIntegerField(default=1)
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
            if previous.default_currency != self.default_currency:
                raise ValidationError({"default_currency": "A company with accounts cannot change its default currency."})


class Account(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="accounts")
    name = models.CharField(max_length=180)
    kind = models.CharField(max_length=10, choices=[("bank", "Bank"), ("cash", "Cash")], default="bank")
    currency = models.CharField(max_length=3, validators=[currency_validator])
    bank_name = models.CharField(max_length=150, blank=True)
    studios = models.ManyToManyField("core_data.Studio", blank=True, related_name="finance_accounts")
    active = models.BooleanField(default=True)
    statement_imports_expected = models.BooleanField(default=True)
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    opening_balance_date = models.DateField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.UniqueConstraint(fields=["company", "name"], name="finance_account_company_name")]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if (self.opening_balance is None) != (self.opening_balance_date is None):
            raise ValidationError({"opening_balance": "Provide both a reference balance and its date, or leave both empty."})
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.company_id != self.company_id:
                raise ValidationError({"company": "An account cannot be moved to another company."})
            if previous.currency != self.currency:
                raise ValidationError({"currency": "Create a separate account for a different currency."})
        if self.company_id and self.currency != self.company.default_currency:
            raise ValidationError({"currency": "Use the company's default currency in this version."})


class Terminal(models.Model):
    CHANNELS = [("card_terminal", "Cierre"), ("recurring", "Recurrentes"),
                ("payment_link", "Link"), ("other", "Other")]
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="terminals")
    identifier = models.CharField(max_length=40)
    studio = models.ForeignKey("core_data.Studio", on_delete=models.PROTECT, related_name="finance_terminals")
    channel = models.CharField(max_length=20, choices=CHANNELS)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["identifier", "pk"]
        constraints = [models.UniqueConstraint(fields=["account", "identifier"], name="finance_terminal_account_identifier")]

    def __str__(self):
        return self.identifier

    def clean(self):
        super().clean()
        if self.account_id and self.studio_id:
            if self.account.kind != "bank":
                raise ValidationError({"account": "Terminals require a bank account."})
            if self.account.company.site_id != self.studio.site_id:
                raise ValidationError({"studio": "Terminal and studio must belong to the same site."})
            if self.account.studios.exists() and not self.account.studios.filter(pk=self.studio_id).exists():
                raise ValidationError({"studio": "Studio must participate in the terminal's account."})
        if self.pk and type(self).objects.get(pk=self.pk).account_id != self.account_id:
            raise ValidationError({"account": "A terminal cannot be moved to another account; deactivate it and create a new mapping."})


class ConfigurationChange(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    target_type = models.CharField(max_length=30)
    target_id = models.PositiveBigIntegerField()
    target_label = models.CharField(max_length=180)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]


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
    studios = list(studios)
    if any(studio.site_id != account.company.site_id for studio in studios):
        raise ValidationError("Account studios must belong to the company's site.")
    if account.pk and studios:
        ids = {studio.pk for studio in studios}
        if account.terminals.exclude(studio_id__in=ids).exists():
            raise ValidationError("Keep all mapped terminal studios in the account, including inactive mappings.")
