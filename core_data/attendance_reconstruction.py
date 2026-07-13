import hashlib
import json
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from .importers import ATTENDANCE_REPORT_TYPE, attendance_natural_key, clean_value
from .models import AttendanceRawRow, AttendanceVisit, ReportImport, Site, Studio


REMOVED_FROM_RECONSTRUCTION = "missing_from_historical_reconstruction"
LEGACY_RECONSTRUCTION_REASONS = [
    REMOVED_FROM_RECONSTRUCTION,
    "missing_from_latest_import",
]


def _historical_import_hash(rows):
    payload = [
        {
            "site_id": row.site_id,
            "row_number": row.row_number,
            "row_hash": row.row_hash,
            "normalized_payload": row.normalized_payload,
        }
        for row in rows
    ]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _report_window(rows):
    dates = sorted({
        row.normalized_payload.get("_visit_date")
        for row in rows
        if row.normalized_payload.get("_visit_date")
    })
    if not dates:
        return None, None
    return dates[0], dates[-1]


def _studios_for_rows(site_id, rows, present_visits):
    studio_ids = {visit.visit_studio_id for visit in present_visits.values() if visit.visit_studio_id}
    studio_names = {
        clean_value(row.normalized_payload.get("Ubicación de visita"))
        for row in rows
        if clean_value(row.normalized_payload.get("Ubicación de visita"))
    }
    if studio_names:
        for studio in Studio.objects.filter(site_id=site_id, name__in=studio_names):
            studio_ids.add(studio.id)
    return studio_ids


def reconstruct_attendance_history(*, site_id=None, apply=False):
    imports = (
        ReportImport.objects.filter(
            report_type=ATTENDANCE_REPORT_TYPE,
            status=ReportImport.STATUS_COMPLETED,
            attendance_raw_rows__isnull=False,
        )
        .distinct()
        .order_by("uploaded_at", "id")
    )
    if site_id:
        imports = imports.filter(attendance_raw_rows__site_id=site_id).distinct()

    active_scope = AttendanceVisit.objects.all()
    if site_id:
        active_scope = active_scope.filter(site_id=site_id)
    simulated_active_ids = set(active_scope.filter(is_active=True).values_list("id", flat=True))

    totals = {
        "imports_processed": 0,
        "imports_with_rows": 0,
        "report_periods_updated": 0,
        "file_hashes_updated": 0,
        "visits_reactivated": 0,
        "visits_removed": 0,
        "missing_present_visits": 0,
    }
    duplicate_hashes = defaultdict(list)
    affected_ranges = {}
    import_summaries = []
    now = timezone.now()

    with transaction.atomic():
        for report_import in imports:
            rows = list(
                AttendanceRawRow.objects.filter(
                    report_import=report_import,
                    is_valid=True,
                )
                .select_related("site")
                .order_by("site_id", "row_number")
            )
            if site_id:
                rows = [row for row in rows if row.site_id == int(site_id)]
            totals["imports_processed"] += 1
            if not rows:
                continue
            totals["imports_with_rows"] += 1

            content_hash = _historical_import_hash(rows)
            duplicate_hashes[content_hash].append(report_import.id)
            period_start, period_end = _report_window(rows)
            should_update_file_hash = not report_import.file_hash
            if period_start and period_end:
                if report_import.period_start != period_start or report_import.period_end != period_end:
                    totals["report_periods_updated"] += 1
                if should_update_file_hash:
                    totals["file_hashes_updated"] += 1
                if apply:
                    report_import.period_start = period_start
                    report_import.period_end = period_end
                    update_fields = ["period_start", "period_end"]
                    if should_update_file_hash:
                        report_import.file_hash = content_hash
                        update_fields.append("file_hash")
                    report_import.save(update_fields=update_fields)

            rows_by_site = defaultdict(list)
            for row in rows:
                rows_by_site[row.site_id].append(row)

            import_removed = 0
            import_reactivated = 0
            import_missing_present = 0

            for row_site_id, site_rows in rows_by_site.items():
                try:
                    site = site_rows[0].site or Site.objects.get(id=row_site_id)
                except Site.DoesNotExist:
                    continue

                current_candidates = {}
                for row in site_rows:
                    natural_key = attendance_natural_key(site, row.normalized_payload)
                    current_candidates[natural_key] = row

                present_visits = {
                    visit.natural_key: visit
                    for visit in AttendanceVisit.objects.filter(
                        site_id=row_site_id,
                        natural_key__in=current_candidates.keys(),
                    )
                }
                import_missing_present += len(current_candidates) - len(present_visits)
                present_ids = {visit.id for visit in present_visits.values()}
                reactivated_ids = present_ids - simulated_active_ids
                if reactivated_ids:
                    import_reactivated += len(reactivated_ids)
                    simulated_active_ids.update(reactivated_ids)
                    if apply:
                        AttendanceVisit.objects.filter(id__in=reactivated_ids).update(
                            is_active=True,
                            removed_seen_import=None,
                            removed_at=None,
                            removed_reason=None,
                        )

                if not period_start or not period_end:
                    continue
                studio_ids = _studios_for_rows(row_site_id, site_rows, present_visits)
                if not studio_ids:
                    continue

                range_visits = AttendanceVisit.objects.filter(
                    site_id=row_site_id,
                    visit_date__range=(period_start, period_end),
                    visit_studio_id__in=studio_ids,
                ).values("id", "natural_key")
                remove_ids = [
                    row["id"]
                    for row in range_visits
                    if row["id"] in simulated_active_ids and row["natural_key"] not in current_candidates
                ]
                if remove_ids:
                    import_removed += len(remove_ids)
                    simulated_active_ids.difference_update(remove_ids)
                    if apply:
                        AttendanceVisit.objects.filter(id__in=remove_ids).update(
                            is_active=False,
                            removed_seen_import=report_import,
                            removed_at=now,
                            removed_reason=REMOVED_FROM_RECONSTRUCTION,
                        )
                    affected = affected_ranges.setdefault(
                        row_site_id,
                        {"site_id": row_site_id, "from": period_start, "to": period_end},
                    )
                    affected["from"] = min(affected["from"], period_start)
                    affected["to"] = max(affected["to"], period_end)

            totals["visits_reactivated"] += import_reactivated
            totals["visits_removed"] += import_removed
            totals["missing_present_visits"] += import_missing_present
            if import_removed or import_reactivated or import_missing_present:
                import_summaries.append({
                    "report_import_id": report_import.id,
                    "file_name": report_import.file_name,
                    "uploaded_at": report_import.uploaded_at.isoformat() if report_import.uploaded_at else None,
                    "period_start": period_start,
                    "period_end": period_end,
                    "visits_removed": import_removed,
                    "visits_reactivated": import_reactivated,
                    "missing_present_visits": import_missing_present,
                })

        if not apply:
            transaction.set_rollback(True)

    duplicate_import_groups = [
        {"file_hash": file_hash, "report_import_ids": ids, "count": len(ids)}
        for file_hash, ids in duplicate_hashes.items()
        if len(ids) > 1
    ]
    return {
        "dry_run": not apply,
        "confirmation_required": "RECONSTRUCT ATTENDANCE",
        "site_id": int(site_id) if site_id else None,
        "totals": totals,
        "affected_ranges": list(affected_ranges.values()),
        "duplicate_import_groups": duplicate_import_groups[:20],
        "duplicate_import_group_count": len(duplicate_import_groups),
        "import_summaries": import_summaries[:50],
        "import_summary_count": len(import_summaries),
    }


def restore_reconstructed_attendance(*, site_id, date_from=None, date_to=None, apply=False):
    queryset = AttendanceVisit.objects.filter(
        site_id=site_id,
        is_active=False,
        removed_reason__in=LEGACY_RECONSTRUCTION_REASONS,
    )
    if date_from:
        queryset = queryset.filter(visit_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(visit_date__lte=date_to)

    affected = queryset.order_by().values("site_id").distinct()
    affected_ranges = []
    for row in affected:
        site_visits = queryset.filter(site_id=row["site_id"]).order_by("visit_date")
        first_visit = site_visits.first()
        last_visit = site_visits.last()
        if first_visit and last_visit:
            affected_ranges.append({
                "site_id": row["site_id"],
                "from": first_visit.visit_date.isoformat(),
                "to": last_visit.visit_date.isoformat(),
            })

    count = queryset.count()
    if apply and count:
        queryset.update(
            is_active=True,
            removed_seen_import=None,
            removed_at=None,
            removed_reason=None,
        )

    return {
        "dry_run": not apply,
        "confirmation_required": "RESTORE ATTENDANCE",
        "site_id": int(site_id),
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "visits_to_restore": count,
        "visits_restored": count if apply else 0,
        "affected_ranges": affected_ranges,
    }
