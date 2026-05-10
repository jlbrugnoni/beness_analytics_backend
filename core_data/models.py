from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, Group, PermissionsMixin
from django.db import models
from django.utils.text import slugify


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True, blank=True, null=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    groups = models.ManyToManyField(Group, blank=True)
    image = models.URLField(blank=True, null=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    def __str__(self):
        return self.email


class BaseModel(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=200, blank=True, editable=False)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
    )
    active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Site(BaseModel):
    COUNTRY_DOMINICAN_REPUBLIC = "DO"
    COUNTRY_SPAIN = "ES"

    COUNTRY_CHOICES = [
        (COUNTRY_DOMINICAN_REPUBLIC, "Dominican Republic"),
        (COUNTRY_SPAIN, "Spain"),
    ]

    country_code = models.CharField(max_length=2, choices=COUNTRY_CHOICES)
    mindbody_site_id = models.CharField(max_length=100, blank=True, null=True)

    class Meta(BaseModel.Meta):
        unique_together = ("country_code", "name")


class SiteScopedModel(BaseModel):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="%(class)ss")
    mindbody_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    mindbody_name = models.CharField(max_length=255, blank=True, null=True)
    normalized_name = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ["site__name", "name"]

    def save(self, *args, **kwargs):
        if not self.mindbody_name:
            self.mindbody_name = self.name
        if not self.normalized_name:
            self.normalized_name = self.name.strip().casefold()
        super().save(*args, **kwargs)


class Studio(SiteScopedModel):
    pass


class Client(SiteScopedModel):
    first_name = models.CharField(max_length=150, blank=True, null=True)
    last_name = models.CharField(max_length=150, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)

    class Meta(SiteScopedModel.Meta):
        unique_together = ("site", "mindbody_id")


class StaffMember(SiteScopedModel):
    first_name = models.CharField(max_length=150, blank=True, null=True)
    last_name = models.CharField(max_length=150, blank=True, null=True)


class ServiceCategory(SiteScopedModel):
    pass


class PricingOption(SiteScopedModel):
    service_category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pricing_options",
    )


class PaymentMethod(SiteScopedModel):
    pass


class ReportImport(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    report_type = models.CharField(max_length=100)
    source_system = models.CharField(max_length=100, blank=True, null=True)
    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, null=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_imports",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.report_type} - {self.file_name}"


class AttendanceRawRow(models.Model):
    report_import = models.ForeignKey(ReportImport, on_delete=models.CASCADE, related_name="attendance_raw_rows")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="attendance_raw_rows")
    row_number = models.PositiveIntegerField()
    row_hash = models.CharField(max_length=64, db_index=True)
    raw_payload = models.JSONField()
    normalized_payload = models.JSONField(default=dict)
    is_valid = models.BooleanField(default=True)
    validation_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("report_import", "row_number")
        ordering = ["report_import_id", "row_number"]

    def __str__(self):
        return f"{self.report_import_id} row {self.row_number}"


class AttendanceVisit(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="attendance_visits")
    natural_key = models.CharField(max_length=64, unique=True, db_index=True)
    current_row_hash = models.CharField(max_length=64, db_index=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="attendance_visits")
    staff_member = models.ForeignKey(
        StaffMember,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_visits",
    )
    visit_studio = models.ForeignKey(Studio, on_delete=models.PROTECT, related_name="visit_attendance_visits")
    sale_studio = models.ForeignKey(
        Studio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sale_attendance_visits",
    )
    service_category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_visits",
    )
    pricing_option = models.ForeignKey(
        PricingOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_visits",
    )
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_visits",
    )
    visit_date = models.DateField()
    visit_time_raw = models.CharField(max_length=50)
    weekday_raw = models.CharField(max_length=50, blank=True, null=True)
    visit_type = models.CharField(max_length=255, blank=True, null=True)
    type_name = models.CharField(max_length=255, blank=True, null=True)
    expiration_date = models.DateField(blank=True, null=True)
    remaining_visits = models.IntegerField(blank=True, null=True)
    staff_paid = models.BooleanField(blank=True, null=True)
    late_cancel = models.BooleanField(default=False)
    no_show = models.BooleanField(default=False)
    scheduling_method = models.CharField(max_length=255, blank=True, null=True)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    first_seen_import = models.ForeignKey(
        ReportImport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="first_seen_attendance_visits",
    )
    last_seen_import = models.ForeignKey(
        ReportImport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_seen_attendance_visits",
    )
    source_raw_row = models.ForeignKey(
        AttendanceRawRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_attendance_visits",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-visit_date", "visit_time_raw", "client__name"]

    def __str__(self):
        return f"{self.visit_date} {self.visit_time_raw} - {self.client.name}"


class AttendanceVisitVersion(models.Model):
    attendance_visit = models.ForeignKey(AttendanceVisit, on_delete=models.CASCADE, related_name="versions")
    report_import = models.ForeignKey(ReportImport, on_delete=models.CASCADE, related_name="attendance_versions")
    raw_row = models.ForeignKey(AttendanceRawRow, on_delete=models.CASCADE, related_name="attendance_versions")
    row_hash = models.CharField(max_length=64, db_index=True)
    changed_fields = models.JSONField(default=list, blank=True)
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.attendance_visit_id} @ {self.report_import_id}"


class SaleRawRow(models.Model):
    report_import = models.ForeignKey(ReportImport, on_delete=models.CASCADE, related_name="sale_raw_rows")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="sale_raw_rows")
    row_number = models.PositiveIntegerField()
    row_hash = models.CharField(max_length=64, db_index=True)
    raw_payload = models.JSONField()
    normalized_payload = models.JSONField(default=dict)
    is_valid = models.BooleanField(default=True)
    validation_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("report_import", "row_number")
        ordering = ["report_import_id", "row_number"]

    def __str__(self):
        return f"{self.report_import_id} row {self.row_number}"


class SaleLine(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="sale_lines")
    natural_key = models.CharField(max_length=64, unique=True, db_index=True)
    current_row_hash = models.CharField(max_length=64, db_index=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="sale_lines")
    studio = models.ForeignKey(Studio, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_lines")
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sale_lines",
    )
    sale_date = models.DateField()
    sale_number = models.CharField(max_length=100, db_index=True)
    item_name = models.CharField(max_length=255)
    computation_number = models.CharField(max_length=100, blank=True, null=True)
    sale_notes = models.TextField(blank=True, null=True)
    item_notes = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=100, blank=True, null=True)
    size = models.CharField(max_length=100, blank=True, null=True)
    item_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    item_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    first_seen_import = models.ForeignKey(
        ReportImport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="first_seen_sale_lines",
    )
    last_seen_import = models.ForeignKey(
        ReportImport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_seen_sale_lines",
    )
    source_raw_row = models.ForeignKey(
        SaleRawRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_sale_lines",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-sale_date", "sale_number", "item_name"]

    def __str__(self):
        return f"{self.sale_number} - {self.item_name}"


class SaleLineVersion(models.Model):
    sale_line = models.ForeignKey(SaleLine, on_delete=models.CASCADE, related_name="versions")
    report_import = models.ForeignKey(ReportImport, on_delete=models.CASCADE, related_name="sale_line_versions")
    raw_row = models.ForeignKey(SaleRawRow, on_delete=models.CASCADE, related_name="sale_line_versions")
    row_hash = models.CharField(max_length=64, db_index=True)
    changed_fields = models.JSONField(default=list, blank=True)
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sale_line_id} @ {self.report_import_id}"


class ServicePurchaseRawRow(models.Model):
    report_import = models.ForeignKey(ReportImport, on_delete=models.CASCADE, related_name="service_purchase_raw_rows")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="service_purchase_raw_rows")
    row_number = models.PositiveIntegerField()
    row_hash = models.CharField(max_length=64, db_index=True)
    raw_payload = models.JSONField()
    normalized_payload = models.JSONField(default=dict)
    is_valid = models.BooleanField(default=True)
    validation_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("report_import", "row_number")
        ordering = ["report_import_id", "row_number"]

    def __str__(self):
        return f"{self.report_import_id} row {self.row_number}"


class ServicePurchase(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="service_purchases")
    natural_key = models.CharField(max_length=64, unique=True, db_index=True)
    current_row_hash = models.CharField(max_length=64, db_index=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="service_purchases")
    service_category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_purchases",
    )
    pricing_option = models.ForeignKey(
        PricingOption,
        on_delete=models.PROTECT,
        related_name="service_purchases",
    )
    sale_date = models.DateField()
    activation_date = models.DateField(blank=True, null=True)
    expiration_date = models.DateField(blank=True, null=True)
    activation_offset_days = models.IntegerField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cash_equivalent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    non_cash_equivalent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    first_seen_import = models.ForeignKey(
        ReportImport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="first_seen_service_purchases",
    )
    last_seen_import = models.ForeignKey(
        ReportImport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_seen_service_purchases",
    )
    source_raw_row = models.ForeignKey(
        ServicePurchaseRawRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_service_purchases",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-sale_date", "client__name", "pricing_option__name"]

    def __str__(self):
        return f"{self.client.name} - {self.pricing_option.name}"


class ServicePurchaseVersion(models.Model):
    service_purchase = models.ForeignKey(ServicePurchase, on_delete=models.CASCADE, related_name="versions")
    report_import = models.ForeignKey(ReportImport, on_delete=models.CASCADE, related_name="service_purchase_versions")
    raw_row = models.ForeignKey(ServicePurchaseRawRow, on_delete=models.CASCADE, related_name="service_purchase_versions")
    row_hash = models.CharField(max_length=64, db_index=True)
    changed_fields = models.JSONField(default=list, blank=True)
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.service_purchase_id} @ {self.report_import_id}"


class LoginLog(models.Model):
    LOGIN_TYPE_CHOICES = [
        ("main", "Login Principal"),
        ("secondary", "Login Secundario"),
        ("logout", "Cierre de Sesion"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_logs")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    login_type = models.CharField(max_length=10, choices=LOGIN_TYPE_CHOICES, default="main")
    user_agent = models.TextField(blank=True, null=True)
    success = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.login_type} - {self.created_at}"
