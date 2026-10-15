from django.conf import settings
from django.db import models


class AuditRecord(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_records",
    )
    action = models.CharField(max_length=40, db_index=True)
    object_type = models.CharField(max_length=120, db_index=True)
    object_id = models.CharField(max_length=64, blank=True, db_index=True)
    changes = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    request_id = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ("-occurred_at",)
        indexes = [models.Index(fields=("object_type", "object_id", "occurred_at"))]

    def __str__(self):
        return f"{self.action} {self.object_type}#{self.object_id}"
