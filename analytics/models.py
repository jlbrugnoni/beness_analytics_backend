from django.db import models


class MembershipMonthStatus(models.Model):
    STATUS_RETAINED = "retained"
    STATUS_NEW = "new"
    STATUS_REACTIVATED = "reactivated"
    STATUS_NOT_RENEWED = "not_renewed"

    STATUS_CHOICES = [
        (STATUS_RETAINED, "Retained"),
        (STATUS_NEW, "New"),
        (STATUS_REACTIVATED, "Reactivated"),
        (STATUS_NOT_RENEWED, "Not Renewed"),
    ]

    STUDIO_METHOD_ATTENDANCE_MONTH = "attendance_month"
    STUDIO_METHOD_RECENT_ATTENDANCE = "recent_attendance"
    STUDIO_METHOD_PREVIOUS_MONTH = "previous_month"
    STUDIO_METHOD_PURCHASE = "purchase"
    STUDIO_METHOD_UNKNOWN = "unknown"

    STUDIO_METHOD_CHOICES = [
        (STUDIO_METHOD_PURCHASE, "Membership Purchase"),
        (STUDIO_METHOD_ATTENDANCE_MONTH, "Attendance in Month"),
        (STUDIO_METHOD_RECENT_ATTENDANCE, "Recent Attendance"),
        (STUDIO_METHOD_PREVIOUS_MONTH, "Previous Month"),
        (STUDIO_METHOD_UNKNOWN, "Unknown"),
    ]

    site = models.ForeignKey("core_data.Site", on_delete=models.CASCADE, related_name="membership_month_statuses")
    month = models.DateField(db_index=True)
    client = models.ForeignKey("core_data.Client", on_delete=models.CASCADE, related_name="membership_month_statuses")
    studio = models.ForeignKey(
        "core_data.Studio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="membership_month_statuses",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, db_index=True)
    current_month_member = models.BooleanField(default=False)
    previous_month_member = models.BooleanField(default=False)
    membership_days = models.PositiveIntegerField(default=0)
    previous_membership_days = models.PositiveIntegerField(default=0)
    membership_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    source_purchase = models.ForeignKey(
        "core_data.ServicePurchase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="membership_month_statuses",
    )
    studio_inference_method = models.CharField(
        max_length=30,
        choices=STUDIO_METHOD_CHOICES,
        default=STUDIO_METHOD_UNKNOWN,
    )
    rebuilt_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("site", "month", "client")
        ordering = ["-month", "status", "client__name"]

    def __str__(self):
        return f"{self.month:%Y-%m} - {self.client} - {self.status}"


class ClientStudioMonthlyMetric(models.Model):
    site = models.ForeignKey(
        "core_data.Site",
        on_delete=models.CASCADE,
        related_name="client_studio_monthly_metrics",
    )
    studio = models.ForeignKey(
        "core_data.Studio",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="client_monthly_metrics",
    )
    client = models.ForeignKey(
        "core_data.Client",
        on_delete=models.CASCADE,
        related_name="studio_monthly_metrics",
    )
    month = models.DateField(db_index=True)

    total_bookings = models.PositiveIntegerField(default=0)
    attended_visits = models.PositiveIntegerField(default=0)
    no_shows = models.PositiveIntegerField(default=0)
    late_cancels = models.PositiveIntegerField(default=0)
    active_weeks = models.PositiveIntegerField(default=0)
    active_week_starts = models.JSONField(default=list, blank=True)
    attendance_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    service_purchase_count = models.PositiveIntegerField(default=0)
    service_spending = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    membership_spending = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    non_membership_spending = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    general_sales_spending = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    first_visit_date = models.DateField(null=True, blank=True)
    last_visit_date = models.DateField(null=True, blank=True)
    first_purchase_date = models.DateField(null=True, blank=True)
    last_purchase_date = models.DateField(null=True, blank=True)

    active_membership_days = models.PositiveIntegerField(default=0)
    active_membership_dates = models.JSONField(default=list, blank=True)
    membership_status = models.CharField(
        max_length=20,
        choices=MembershipMonthStatus.STATUS_CHOICES,
        null=True,
        blank=True,
        db_index=True,
    )
    rebuilt_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month", "site__name", "studio__name", "client__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["site", "studio", "client", "month"],
                condition=models.Q(studio__isnull=False),
                name="unique_client_studio_month_metric",
            ),
            models.UniqueConstraint(
                fields=["site", "client", "month"],
                condition=models.Q(studio__isnull=True),
                name="unique_client_unassigned_month_metric",
            ),
        ]
        indexes = [
            models.Index(fields=["site", "month"]),
            models.Index(fields=["studio", "month"]),
            models.Index(fields=["client", "month"]),
        ]

    def __str__(self):
        studio = self.studio.name if self.studio_id else "Unassigned"
        return f"{self.month:%Y-%m} - {studio} - {self.client}"
