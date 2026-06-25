from collections import defaultdict
from datetime import timedelta

from django.db import transaction

from analytics.client_metrics import rebuild_client_metrics_for_periods
from core_data.importers import attendance_natural_key
from core_data.models import AttendanceVisit


def visit_payload(visit):
    if visit.source_raw_row_id and visit.source_raw_row:
        return dict(visit.source_raw_row.normalized_payload)
    return {
        "ID del cliente": visit.client.mindbody_id,
        "_visit_date": visit.visit_date.isoformat(),
        "Tiempo": visit.visit_time_raw,
        "Ubicación de visita": visit.visit_studio.name if visit.visit_studio_id else None,
        "Visita por categoría de servicio": (
            visit.service_category.name if visit.service_category_id else None
        ),
        "Tipo de Visita": visit.visit_type,
    }


def stable_attendance_key(visit):
    return attendance_natural_key(visit.site, visit_payload(visit))


def latest_visit_key(visit):
    uploaded_at = visit.last_seen_import.uploaded_at if visit.last_seen_import_id else None
    first_seen_at = visit.first_seen_import.uploaded_at if visit.first_seen_import_id else None
    return (
        uploaded_at or first_seen_at or visit.updated_at,
        visit.last_seen_import_id or 0,
        visit.id,
    )


def affected_week(value):
    return value - timedelta(days=value.weekday())


def repair_attendance_staff_duplicates(
    site_id=None,
    studio_id=None,
    date_from=None,
    date_to=None,
    dry_run=False,
    rebuild_metrics=True,
):
    visits = AttendanceVisit.objects.select_related(
        "site",
        "client",
        "visit_studio",
        "service_category",
        "source_raw_row",
        "first_seen_import",
        "last_seen_import",
    ).all()
    if site_id:
        visits = visits.filter(site_id=site_id)
    if studio_id:
        visits = visits.filter(visit_studio_id=studio_id)
    if date_from:
        visits = visits.filter(visit_date__gte=date_from)
    if date_to:
        visits = visits.filter(visit_date__lte=date_to)

    grouped = defaultdict(list)
    for visit in visits.iterator():
        grouped[stable_attendance_key(visit)].append(visit)

    duplicate_groups = [
        sorted(group, key=latest_visit_key, reverse=True)
        for group in grouped.values()
        if len(group) > 1
    ]
    stale_key_updates = [
        group[0]
        for group in grouped.values()
        if len(group) == 1 and group[0].natural_key != stable_attendance_key(group[0])
    ]

    stats = {
        "duplicate_groups": len(duplicate_groups),
        "duplicate_visits_deleted": sum(len(group) - 1 for group in duplicate_groups),
        "stale_natural_keys_updated": len(stale_key_updates),
        "class_matches_deleted": 0,
        "class_matches_moved": 0,
        "versions_moved": 0,
        "metrics_rebuilt": None,
    }
    affected = defaultdict(lambda: {"months": set(), "weeks": set()})

    with transaction.atomic():
        for group in duplicate_groups:
            canonical = group[0]
            stable_key = stable_attendance_key(canonical)
            if canonical.natural_key != stable_key and not dry_run:
                canonical.natural_key = stable_key
                canonical.save(update_fields=["natural_key", "updated_at"])

            affected[canonical.site_id]["months"].add(canonical.visit_date.replace(day=1))
            affected[canonical.site_id]["weeks"].add(affected_week(canonical.visit_date))

            canonical_match = getattr(canonical, "class_match", None)
            for duplicate in group[1:]:
                affected[duplicate.site_id]["months"].add(duplicate.visit_date.replace(day=1))
                affected[duplicate.site_id]["weeks"].add(affected_week(duplicate.visit_date))

                duplicate_match = getattr(duplicate, "class_match", None)
                if duplicate_match:
                    if canonical_match:
                        stats["class_matches_deleted"] += 1
                        if not dry_run:
                            duplicate_match.delete()
                    else:
                        stats["class_matches_moved"] += 1
                        canonical_match = duplicate_match
                        if not dry_run:
                            duplicate_match.attendance_visit = canonical
                            duplicate_match.save(update_fields=["attendance_visit"])

                version_count = duplicate.versions.count()
                stats["versions_moved"] += version_count
                if not dry_run:
                    duplicate.versions.update(attendance_visit=canonical)
                    duplicate.delete()

        for visit in stale_key_updates:
            stable_key = stable_attendance_key(visit)
            affected[visit.site_id]["months"].add(visit.visit_date.replace(day=1))
            affected[visit.site_id]["weeks"].add(affected_week(visit.visit_date))
            if not dry_run:
                visit.natural_key = stable_key
                visit.save(update_fields=["natural_key", "updated_at"])

        if dry_run:
            transaction.set_rollback(True)

    if not dry_run and rebuild_metrics:
        metrics_stats = {}
        for affected_site_id, periods in affected.items():
            metrics_stats[affected_site_id] = rebuild_client_metrics_for_periods(
                affected_site_id,
                months=periods["months"],
                weeks=periods["weeks"],
            )
        stats["metrics_rebuilt"] = metrics_stats

    return stats
