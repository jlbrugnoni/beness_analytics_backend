import unicodedata
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


currency_validator = RegexValidator(r"^[A-Z]{3}$", "Use a three-letter uppercase currency code.")


def custom_catalog_code():
    return f"custom-{uuid.uuid4().hex}"


def normalized_source_value(value):
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


class Company(models.Model):
    sales_revision = models.PositiveIntegerField(default=1, editable=False)
    payment_revision = models.PositiveIntegerField(default=1, editable=False)
    name = models.CharField(max_length=180)
    site = models.ForeignKey("core_data.Site", on_delete=models.PROTECT, related_name="finance_companies")
    default_currency = models.CharField(max_length=3, validators=[currency_validator])
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)
    category_catalog_version = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.UniqueConstraint(fields=["site", "name"], name="finance_company_site_name")]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.site_id != self.site_id and (self.accounts.exists() or self.categories.exists() or self.source_mappings.exists() or self.feepolicy_set.exists() or self.settlementpolicy_set.exists() or self.taxprofile_set.exists() or self.sales_previews.exists() or self.migration_previews.exists() or self.payment_previews.exists()):
                raise ValidationError({"site": "A company with financial configuration or import history cannot be moved to another site."})
            if previous.default_currency != self.default_currency and (self.accounts.exists() or self.feepolicy_set.exists() or self.sales_previews.exists() or self.migration_previews.exists() or self.payment_previews.exists()):
                raise ValidationError({"default_currency": "A company with accounts, fee policies or import history cannot change its default currency."})


class Account(models.Model):
    ledger_revision = models.PositiveIntegerField(default=1, editable=False)
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
            if previous.kind == "bank" and self.kind != "bank" and self.bank_previews.exists():
                raise ValidationError({"kind": "An account with bank report history must remain a bank account."})
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


class Category(models.Model):
    TREATMENTS = [("operating", "Operating"), ("extraordinary", "Extraordinary"), ("review", "Review required")]
    ALLOCATIONS = [("direct", "Direct"), ("administration", "Shared administration")]
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="categories")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    name = models.CharField(max_length=180)
    normalized_name = models.CharField(max_length=240, editable=False, blank=True)
    catalog_code = models.CharField(max_length=64, default=custom_catalog_code, editable=False)
    default_treatment = models.CharField(max_length=20, choices=TREATMENTS, blank=True, default="review")
    default_allocation = models.CharField(max_length=20, choices=ALLOCATIONS, blank=True, default="direct")
    sensitive = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["company", "normalized_name"], condition=models.Q(parent__isnull=True), name="finance_category_root_name"),
            models.UniqueConstraint(fields=["company", "parent", "normalized_name"], condition=models.Q(parent__isnull=False), name="finance_category_child_name"),
            models.UniqueConstraint(fields=["company", "catalog_code"], name="finance_category_company_code"),
        ]

    def __str__(self):
        return self.name

    @property
    def effective_sensitive(self):
        return self.sensitive or bool(self.parent_id and self.parent.sensitive)

    @property
    def effective_active(self):
        return self.active and (not self.parent_id or self.parent.active)

    @property
    def effective_treatment(self):
        return self.default_treatment or self.parent.default_treatment

    @property
    def effective_allocation(self):
        return self.default_allocation or self.parent.default_allocation

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        self.normalized_name = " ".join(unicodedata.normalize("NFKC", self.name).split()).casefold()
        if not self.normalized_name:
            raise ValidationError({"name": "Enter a category name."})
        if len(self.normalized_name) > 240:
            raise ValidationError({"name": "Use a shorter category name."})
        if not self.parent_id and (not self.default_treatment or not self.default_allocation):
            raise ValidationError("Root categories require explicit treatment and allocation defaults.")
        if self.parent_id:
            if self.parent_id == self.pk or self.parent.parent_id:
                raise ValidationError({"parent": "Use a root category; only two levels are supported."})
            if self.company_id != self.parent.company_id:
                raise ValidationError({"parent": "Parent and subcategory must belong to the same company."})
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.company_id != self.company_id or previous.parent_id != self.parent_id:
                raise ValidationError("Company and parent cannot be reassigned; deactivate and create a new category instead.")

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        self.normalized_name = " ".join(unicodedata.normalize("NFKC", self.name).split()).casefold()
        super().save(*args, **kwargs)


class SourceMapping(models.Model):
    FIELDS = [
        ("alegra_cost_center", "Alegra / Centro de costo"), ("alegra_price_list", "Alegra / Lista de precios"),
        ("alegra_payment_method", "Alegra / Método de pago"), ("mindbody_payment_method", "Mindbody / Payment method"),
        ("mindbody_studio", "Mindbody / Studio"), ("historical_payment_method", "Historical / Payment method"),
        ("historical_studio", "Historical / Studio"),
    ]
    CHANNELS = [("card_terminal", "Cierre"), ("recurring", "Recurrentes"), ("payment_link", "Link"),
                ("transfer", "Transferencia"), ("cash", "Efectivo"), ("other", "Otros")]
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="source_mappings")
    source_field = models.CharField(max_length=32, choices=FIELDS)
    source_value = models.CharField(max_length=180)
    normalized_value = models.CharField(max_length=240, blank=True, editable=False)
    behavior = models.CharField(max_length=10, choices=[("map", "Map"), ("review", "Review"), ("neutral", "Neutral")], default="map")
    studio = models.ForeignKey("core_data.Studio", null=True, blank=True, on_delete=models.PROTECT, related_name="finance_source_mappings")
    channel = models.CharField(max_length=20, choices=CHANNELS, blank=True)
    requires_review = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_field", "source_value", "pk"]
        constraints = [models.UniqueConstraint(fields=["company", "source_field", "normalized_value"], name="finance_mapping_source_value")]

    def __str__(self):
        return self.source_value

    def clean(self):
        super().clean()
        self.normalized_value = normalized_source_value(self.source_value)
        if not self.normalized_value or len(self.normalized_value) > 240:
            raise ValidationError({"source_value": "Enter a source label of a suitable length."})
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if (self.company_id, self.source_field, self.source_value) != (previous.company_id, previous.source_field, previous.source_value):
                raise ValidationError("Company and source identity cannot change. Deactivate the old mapping and add a new one.")
        if self.behavior == "neutral" and self.source_field != "alegra_price_list":
            raise ValidationError({"behavior": "Neutral is only supported for Alegra price lists."})
        if self.source_field == "alegra_price_list" and self.normalized_value == "general" and self.behavior != "neutral":
            raise ValidationError({"behavior": "General is neutral price-list evidence, not a studio assignment."})
        if self.behavior != "map":
            if self.studio_id or self.channel or self.requires_review:
                raise ValidationError("Review/neutral mappings cannot carry a target or an additional review flag.")
        elif self.source_field.endswith("payment_method"):
            if not self.channel or self.studio_id:
                raise ValidationError("Payment methods require a channel and cannot assign a studio.")
        elif not self.studio_id or self.channel:
            raise ValidationError("Studio labels require a studio and cannot assign a payment channel.")
        if self.studio_id and self.company_id and self.studio.site_id != self.company.site_id:
            raise ValidationError({"studio": "Mapped studio must belong to the company's site."})

    def save(self, *args, **kwargs):
        self.normalized_value = normalized_source_value(self.source_value)
        super().save(*args, **kwargs)


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


class DatedPolicy(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, max_length=2000)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['company_id', '-valid_from', 'pk']

    def __str__(self):
        return f'{self.company} / {getattr(self, "channel", "tax")}'[:180]

    def clean(self):
        super().clean()
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError({'valid_until': 'End date must be on or after the start date.'})
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.company_id != self.company_id or getattr(previous, 'channel', None) != getattr(self, 'channel', None):
                raise ValidationError('Company and channel cannot change; deactivate and create another policy.')
        if self.active and self.company_id:
            overlap = type(self).objects.filter(company_id=self.company_id, active=True).exclude(pk=self.pk)
            if hasattr(self, 'channel'):
                overlap = overlap.filter(channel=self.channel)
            if self.valid_from:
                overlap = overlap.filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=self.valid_from))
            if self.valid_until:
                overlap = overlap.filter(models.Q(valid_from__isnull=True) | models.Q(valid_from__lte=self.valid_until))
            if overlap.exists():
                raise ValidationError('Active policy dates overlap. End or deactivate the previous policy first. End dates are inclusive.')


class FeePolicy(DatedPolicy):
    channel = models.CharField(max_length=20, choices=SourceMapping.CHANNELS)
    deposit_mode = models.CharField(max_length=10, choices=[('full', 'Full amount'), ('net', 'Net of withholding'), ('unknown', 'Unknown')], default='unknown')
    percentage = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    separate_fee_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    separate_fee_frequency = models.CharField(max_length=20, choices=[('unknown', 'Unknown'), ('monthly', 'Monthly'), ('per_transaction', 'Per transaction'), ('per_settlement', 'Per settlement')], default='unknown')
    reimbursement_expected = models.BooleanField(default=False)
    reimbursement_from = models.DateField(null=True, blank=True)
    reimbursement_until = models.DateField(null=True, blank=True)

    def clean(self):
        super().clean()
        if self.percentage is not None and not 0 <= self.percentage <= 100:
            raise ValidationError({'percentage': 'Use a percentage from 0 to 100.'})
        if self.deposit_mode != 'net' and self.percentage is not None:
            raise ValidationError({'percentage': 'Withheld percentage applies only to net deposits. Use separate fee fields for independent charges.'})
        if self.separate_fee_amount is not None and self.separate_fee_amount < 0:
            raise ValidationError({'separate_fee_amount': 'Use a non-negative fee amount.'})
        if (self.separate_fee_amount is None) != (self.separate_fee_frequency == 'unknown'):
            raise ValidationError('Provide both a confirmed separate fee amount and its frequency, or leave both unknown.')
        if not self.reimbursement_expected and (self.reimbursement_from or self.reimbursement_until):
            raise ValidationError('Enable expected reimbursement before entering offer dates.')
        if self.reimbursement_from and self.reimbursement_until and self.reimbursement_until < self.reimbursement_from:
            raise ValidationError({'reimbursement_until': 'Offer end must be on or after its start.'})


class SettlementPolicy(DatedPolicy):
    channel = models.CharField(max_length=20, choices=SourceMapping.CHANNELS)
    minimum_hours = models.PositiveIntegerField(default=24)
    maximum_hours = models.PositiveIntegerField(default=48)
    weekend_delays = models.BooleanField(default=False)

    def clean(self):
        super().clean()
        if self.maximum_hours < self.minimum_hours:
            raise ValidationError({'maximum_hours': 'Maximum must be at least the minimum.'})


class TaxProfile(DatedPolicy):
    treatment = models.CharField(max_length=12, choices=[('inclusive', 'Included in sales'), ('no_tax', 'No sales tax'), ('exempt', 'Exempt'), ('unknown', 'Unknown')], default='unknown')
    rate = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)

    def clean(self):
        super().clean()
        if self.treatment == 'inclusive':
            if self.rate is None or not 0 <= self.rate <= 100:
                raise ValidationError({'rate': 'Included tax requires a rate from 0 to 100.'})
        elif self.rate is not None:
            raise ValidationError({'rate': 'Only included tax has a percentage. Keep unknown, no-tax and exempt distinct.'})


class BankImportBatch(models.Model):
    migration_batch = models.ForeignKey('MigrationImportBatch',null=True,blank=True,on_delete=models.PROTECT,related_name='bank_imports')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='bank_previews')
    provider = models.CharField(max_length=10, choices=[('popular', 'Popular'), ('caixa', 'Caixa')])
    file_name = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64, db_index=True)
    byte_size = models.PositiveIntegerField()
    original_file = models.BinaryField(editable=False)
    encoding = models.CharField(max_length=20, blank=True)
    parser_version = models.CharField(max_length=40)
    status = models.CharField(max_length=10, choices=[('preview', 'Preview'), ('failed', 'Failed')])
    summary = models.JSONField(default=dict)
    file_issues = models.JSONField(default=list)
    duplicate_of = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['account', 'provider', 'file_hash'], name='finance_preview_hash')]


class BankImportRow(models.Model):
    migration_assignments = models.JSONField(default=dict,blank=True)
    migration_row = models.ForeignKey('MigrationImportRow',null=True,blank=True,on_delete=models.PROTECT,related_name='bank_rows')
    batch = models.ForeignKey(BankImportBatch, on_delete=models.CASCADE, related_name='rows')
    row_number = models.PositiveIntegerField()
    source_line = models.PositiveIntegerField()
    source_line_end = models.PositiveIntegerField()
    section = models.PositiveIntegerField(default=0)
    kind = models.CharField(max_length=10)
    raw = models.JSONField(default=list)
    parsed = models.JSONField(default=dict)
    issues = models.JSONField(default=list)

    class Meta:
        ordering = ['row_number']
        constraints = [models.UniqueConstraint(fields=['batch', 'row_number'], name='finance_preview_row_number')]


class BankPosting(models.Model):
    batch = models.OneToOneField(BankImportBatch, on_delete=models.PROTECT, related_name='posting')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, default='active')
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    undone_at = models.DateTimeField(null=True, blank=True)


class BankMovement(models.Model):
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='bank_movements')
    provider = models.CharField(max_length=10)
    source = models.JSONField(default=dict)
    fingerprint = models.CharField(max_length=64, db_index=True)
    created_from = models.ForeignKey(BankImportRow, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    reconciled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-pk']


class BankMovementClassification(models.Model):
    KINDS=[('customer_receipt','Income'),('expense','Expense'),('internal_transfer','Internal movement'),
        ('refund','Refund/reimbursement'),('extraordinary','Extraordinary')]
    DEBIT_KINDS=('expense','internal_transfer','refund')
    CREDIT_KINDS=('customer_receipt','internal_transfer','refund','extraordinary')
    movement=models.OneToOneField(BankMovement,on_delete=models.PROTECT,related_name='classification')
    description=models.TextField(blank=True,max_length=2000)
    operation_date=models.DateField(null=True,blank=True)
    expense_period=models.DateField(null=True,blank=True)
    category=models.ForeignKey(Category,null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    subcategory=models.ForeignKey(Category,null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    studio=models.ForeignKey('core_data.Studio',null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    administration=models.BooleanField(default=False)
    channel=models.CharField(max_length=24,blank=True,choices=SourceMapping.CHANNELS)
    terminal=models.ForeignKey(Terminal,null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    movement_kind=models.CharField(max_length=24,blank=True,choices=KINDS)
    reviewed=models.BooleanField(default=False)


class BankDecision(models.Model):
    posting = models.ForeignKey(BankPosting, on_delete=models.PROTECT, related_name='decisions')
    row = models.OneToOneField(BankImportRow, on_delete=models.PROTECT, related_name='decision')
    outcome = models.CharField(max_length=20)
    resolution = models.CharField(max_length=20, default='pending')
    movement = models.ForeignKey(BankMovement, null=True, blank=True, on_delete=models.PROTECT, related_name='decisions')
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['posting', 'movement'], condition=models.Q(movement__isnull=False), name='finance_posting_occurrence')]


class BankEvent(models.Model):
    posting = models.ForeignKey(BankPosting, on_delete=models.PROTECT, related_name='events')
    movement = models.ForeignKey(BankMovement, null=True, blank=True, on_delete=models.PROTECT, related_name='events')
    row = models.ForeignKey(BankImportRow, null=True, blank=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=30)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    note = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']


class SalesImportBatch(models.Model):
    """Immutable source preview; does not represent posted financial sales."""
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='sales_previews')
    provider = models.CharField(max_length=16, default='alegra')
    file_name = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64, db_index=True)
    byte_size = models.PositiveIntegerField()
    original_file = models.BinaryField(editable=False)
    encoding = models.CharField(max_length=20, blank=True)
    parser_version = models.CharField(max_length=40)
    status = models.CharField(max_length=10)
    summary = models.JSONField(default=dict)
    file_issues = models.JSONField(default=list)
    duplicate_of = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['company', 'provider', 'file_hash'], name='finance_sales_preview_hash')]


class SalesImportRow(models.Model):
    batch = models.ForeignKey(SalesImportBatch, on_delete=models.CASCADE, related_name='rows')
    row_number = models.PositiveIntegerField()
    source_line = models.PositiveIntegerField()
    source_line_end = models.PositiveIntegerField()
    kind = models.CharField(max_length=10)
    raw = models.JSONField(default=list)
    parsed = models.JSONField(default=dict)
    issues = models.JSONField(default=list)

    class Meta:
        ordering = ['row_number']
        constraints = [models.UniqueConstraint(fields=['batch', 'row_number'], name='finance_sales_preview_row')]


class SalesImportInvoice(models.Model):
    batch = models.ForeignKey(SalesImportBatch, on_delete=models.CASCADE, related_name='invoices')
    occurrence = models.PositiveIntegerField()
    code = models.TextField()
    source = models.JSONField(default=dict)
    item_count = models.PositiveIntegerField()
    row_numbers = models.JSONField(default=list)
    issues = models.JSONField(default=list)

    class Meta:
        ordering = ['occurrence']
        constraints = [models.UniqueConstraint(fields=['batch', 'occurrence'], name='finance_sales_preview_invoice')]


class SalesPosting(models.Model):
    batch = models.OneToOneField(SalesImportBatch, on_delete=models.PROTECT, related_name='posting')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, default='active')
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


class FinancialSale(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='financial_sales')
    provider = models.CharField(max_length=16, default='alegra')
    code = models.CharField(max_length=64)
    source = models.JSONField(default=dict)
    items = models.JSONField(default=list)
    created_from = models.ForeignKey(SalesImportInvoice, on_delete=models.PROTECT)
    studio = models.ForeignKey('core_data.Studio', null=True, blank=True, on_delete=models.PROTECT)
    channel = models.CharField(max_length=24, blank=True)
    assignments = models.JSONField(default=dict)
    cancellation_treatment = models.CharField(max_length=20, default='pending')
    replacement = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='replaces')
    cancellation_note = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    reconciled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-pk']
        constraints = [models.UniqueConstraint(fields=['company', 'provider', 'code'], condition=models.Q(active=True), name='finance_active_sale_code')]


class SalesDecision(models.Model):
    posting = models.ForeignKey(SalesPosting, on_delete=models.PROTECT, related_name='decisions')
    invoice = models.OneToOneField(SalesImportInvoice, on_delete=models.PROTECT)
    sale = models.ForeignKey(FinancialSale, null=True, on_delete=models.PROTECT, related_name='decisions')
    resolution = models.CharField(max_length=20)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['invoice__occurrence']


class SalesEvent(models.Model):
    posting = models.ForeignKey(SalesPosting, on_delete=models.PROTECT, related_name='events')
    sale = models.ForeignKey(FinancialSale, null=True, on_delete=models.PROTECT, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=30)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']


class MigrationImportBatch(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='migration_previews')
    selected_month = models.DateField()
    file_name = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64, db_index=True)
    byte_size = models.PositiveIntegerField()
    original_file = models.BinaryField(editable=False)
    parser_version = models.CharField(max_length=40)
    status = models.CharField(max_length=10)
    summary = models.JSONField(default=dict)
    file_issues = models.JSONField(default=list)
    sheets = models.JSONField(default=list)
    mappings = models.JSONField(default=dict)
    duplicate_of = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at','-pk']
        indexes = [models.Index(fields=['company','file_hash'],name='finance_migration_hash')]


class MigrationImportRow(models.Model):
    batch = models.ForeignKey(MigrationImportBatch, on_delete=models.CASCADE, related_name='rows')
    sheet = models.CharField(max_length=128)
    source_row = models.PositiveIntegerField()
    kind = models.CharField(max_length=10)
    bank_date = models.DateField(null=True)
    operation_date = models.DateField(null=True)
    expense_period = models.DateField(null=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    raw = models.JSONField(default=list)
    parsed = models.JSONField(default=dict)
    issues = models.JSONField(default=list)

    class Meta:
        ordering = ['sheet','source_row']
        constraints = [models.UniqueConstraint(fields=['batch','sheet','source_row'],name='finance_migration_row')]


class PaymentImportBatch(models.Model):
    """Shared immutable source snapshots for historical and routine payment imports."""
    company = models.ForeignKey(Company,on_delete=models.PROTECT,related_name='payment_previews')
    provider = models.CharField(max_length=16,default='alegra')
    origin = models.CharField(max_length=16,default='report')
    migration_batch = models.ForeignKey(MigrationImportBatch,null=True,on_delete=models.PROTECT)
    selected_month = models.DateField(null=True)
    file_name = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64)
    original_file = models.BinaryField(default=bytes,editable=False)
    parser_version = models.CharField(max_length=40)
    summary = models.JSONField(default=dict)
    file_issues = models.JSONField(default=list)
    duplicate_of = models.ForeignKey('self',null=True,on_delete=models.PROTECT)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering=['-pk']


class PaymentImportRow(models.Model):
    batch = models.ForeignKey(PaymentImportBatch,on_delete=models.CASCADE,related_name='rows')
    source_row = models.PositiveIntegerField()
    source = models.JSONField(default=dict)

    class Meta:
        ordering=['source_row']
        constraints=[models.UniqueConstraint(fields=['batch','source_row'],name='finance_payment_source_row')]


class PaymentPosting(models.Model):
    batch = models.OneToOneField(PaymentImportBatch,on_delete=models.PROTECT,related_name='posting')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL)
    status = models.CharField(max_length=20,default='active')
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


class FinancialReceipt(models.Model):
    company = models.ForeignKey(Company,on_delete=models.PROTECT,related_name='financial_receipts')
    provider = models.CharField(max_length=16,default='alegra')
    number = models.CharField(max_length=64)
    source = models.JSONField(default=dict)
    created_from = models.ForeignKey(PaymentImportRow,on_delete=models.PROTECT)
    sale = models.ForeignKey(FinancialSale,null=True,on_delete=models.PROTECT,related_name='receipts')
    link_issue = models.CharField(max_length=40,default='invoice_missing')
    channel = models.CharField(max_length=24,blank=True)
    studio = models.ForeignKey('core_data.Studio',null=True,on_delete=models.PROTECT)
    assignments = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=1)
    edited = models.BooleanField(default=False)
    reconciled = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering=['-pk']
        constraints=[models.UniqueConstraint(fields=['company','provider','number'],condition=models.Q(active=True),name='finance_active_receipt_number')]


class PaymentDecision(models.Model):
    posting = models.ForeignKey(PaymentPosting,on_delete=models.PROTECT,related_name='decisions')
    row = models.OneToOneField(PaymentImportRow,on_delete=models.PROTECT)
    receipt = models.ForeignKey(FinancialReceipt,null=True,on_delete=models.PROTECT,related_name='decisions')
    resolution = models.CharField(max_length=24)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering=['row__source_row']


class PaymentEvent(models.Model):
    posting = models.ForeignKey(PaymentPosting,null=True,on_delete=models.PROTECT,related_name='events')
    receipt = models.ForeignKey(FinancialReceipt,null=True,on_delete=models.PROTECT,related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL)
    action = models.CharField(max_length=30)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering=['created_at','pk']
