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
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)

    class Meta(SiteScopedModel.Meta):
        unique_together = ("site", "mindbody_id")


class StaffMember(SiteScopedModel):
    pass


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
