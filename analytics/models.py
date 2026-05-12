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
    STUDIO_METHOD_UNKNOWN = "unknown"

    STUDIO_METHOD_CHOICES = [
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
