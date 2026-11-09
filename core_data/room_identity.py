"""Explicit, studio-scoped room identity and conservative duplicate recovery."""
import hashlib
import json
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError
from .models import (Room, RoomAlias, RoomIdentityEvent, Studio, ScheduledClass,
                     WeeklyRoomTemplate, ExpectedClassSlot, StudioClosure, AttendanceClassMatch)


def normalize(value):
    return str(value or "").replace("\xa0", " ").strip().casefold()


def resolve_room(site, studio, name):
    alias = RoomAlias.objects.select_related("room").filter(
        studio=studio, studio__site=site, normalized_name=normalize(name), room__active=True).first()
    if alias:
        return alias.room
    return Room.objects.filter(site=site, studio=studio, normalized_name=normalize(name), active=True).first()


def _alias(room, name, actor, excluding=None):
    name = str(name or "").strip()
    if not name or len(name) > 150:
        raise ValidationError("Room name must contain between 1 and 150 characters.")
    if Room.objects.filter(studio=room.studio, active=True, normalized_name=normalize(name)).exclude(pk__in=[room.pk, excluding]).exists():
        raise ValidationError("This name belongs to another room. Preview a room consolidation instead.")
    alias = RoomAlias.objects.filter(studio=room.studio, normalized_name=normalize(name)).first()
    if alias and alias.room_id not in [room.pk, excluding]:
        raise ValidationError("This alias already belongs to another room.")
    if alias:
        alias.room = room
        alias.save(update_fields=["room"])
    else:
        RoomAlias.objects.create(studio=room.studio, room=room, name=name, normalized_name=normalize(name), created_by=actor)


@transaction.atomic
def add_alias(room, name, actor, display_name=None):
    Studio.objects.select_for_update(of=("self",)).get(pk=room.studio_id)
    room = Room.objects.select_for_update(of=("self",)).get(pk=room.pk)
    if not room.active:
        raise ValidationError("Select an active room.")
    if display_name is not None and not isinstance(display_name, str):
        raise ValidationError("Display name must be text.")
    before = room.name
    _alias(room, room.name, actor)
    _alias(room, name, actor)
    if display_name:
        _alias(room, display_name, actor)
        room.name = display_name.strip()
        room.normalized_name = normalize(room.name)
        room.save(update_fields=["name", "normalized_name", "updated_at"])
    RoomIdentityEvent.objects.create(room=room, actor=actor, action="alias", evidence={"name": name, "before_name": before, "display_name": room.name})
    return room


def class_signature(item):
    return (item.class_date, item.start_time, item.end_time, item.staff_member_id, normalize(item.name), item.session_type)


def _snapshot(qs):
    return list(qs.order_by("pk").values())


def repair_plan(source, target, display_name=None):
    if display_name is not None and (not isinstance(display_name, str) or not display_name.strip() or len(display_name.strip()) > 150):
        raise ValidationError("Display name must contain between 1 and 150 characters.")
    if source.pk == target.pk or source.site_id != target.site_id or source.studio_id != target.studio_id:
        raise ValidationError("Select two different rooms in the same studio and site.")
    if not source.active or not target.active:
        raise ValidationError("Both rooms must be active.")
    classes = list(ScheduledClass.objects.filter(room_id__in=[source.pk, target.pk]).order_by("pk"))
    blockers, moves, duplicates = [], [], []
    if source.room_type != target.room_type:
        blockers.append("Room types differ; resolve their configuration first.")
    for field in ("group_capacity", "private_capacity"):
        if getattr(source, field) and getattr(target, field) and getattr(source, field) != getattr(target, field):
            blockers.append(f"Room {field} differs; confirm the capacity before consolidating.")
    target_classes = [item for item in classes if item.room_id == target.pk and item.status != ScheduledClass.STATUS_CANCELLED]
    target_by_date = {}
    for item in target_classes:
        target_by_date.setdefault(item.class_date, []).append(item)
    affected_dates = sorted({item.class_date.isoformat() for item in classes if item.room_id == source.pk})
    for item in classes:
        if item.room_id != source.pk:
            continue
        day_classes = target_by_date.get(item.class_date, [])
        matches = [other for other in day_classes if class_signature(item) == class_signature(other)]
        overlaps = [other for other in day_classes if other.class_date == item.class_date and other.start_time < item.end_time and item.start_time < other.end_time]
        if len(matches) == 1 and item.status != ScheduledClass.STATUS_CANCELLED:
            other = matches[0]
            expected_pair = {item.source, other.source} == {
                ScheduledClass.SOURCE_EXPECTED_TEMPLATE, ScheduledClass.SOURCE_TRAINER_AVAILABILITY}
            if (item.manually_modified or other.manually_modified or item.capacity != other.capacity
                    or item.status != other.status or (item.source != other.source and not expected_pair)
                    or (item.template_id and other.template_id and item.template_id != other.template_id)):
                blockers.append(f"Classes {item.pk}/{other.pk} need manual review (source, capacity, status, templates or manual corrections differ).")
            elif expected_pair and item.source == ScheduledClass.SOURCE_TRAINER_AVAILABILITY:
                duplicates.append({"retire": other.pk, "keep": item.pk})
                moves.append(item.pk)
            else:
                duplicates.append({"retire": item.pk, "keep": other.pk})
        elif overlaps and item.status != ScheduledClass.STATUS_CANCELLED:
            blockers.append(f"Class {item.pk} overlaps another class with different details; resolve it before consolidating.")
        else:
            moves.append(item.pk)
    if len({pair["retire"] for pair in duplicates}) != len(duplicates):
        blockers.append("Several source classes compete for one existing class; resolve duplicate classes first.")
    # Uniqueness-sensitive legacy slots must be resolved explicitly, never discarded.
    slots = ExpectedClassSlot.objects.filter(room=source)
    for slot in slots:
        if ExpectedClassSlot.objects.filter(room=target, slot_date=slot.slot_date, start_time=slot.start_time, end_time=slot.end_time).exists():
            blockers.append(f"Expected slot {slot.pk} conflicts with an existing slot.")
    for template in WeeklyRoomTemplate.objects.filter(room=source, active=True):
        if WeeklyRoomTemplate.objects.filter(room=target, active=True, weekday=template.weekday,
                start_time__lt=template.end_time, end_time__gt=template.start_time).filter(
                Q(active_until__isnull=True) | Q(active_until__gte=template.active_from)).filter(
                **({"active_from__lte": template.active_until} if template.active_until else {})).exists():
            blockers.append(f"Weekly template {template.pk} overlaps a target-room template. Resolve the templates first.")
    aliases = RoomAlias.objects.filter(room_id__in=[source.pk, target.pk])
    for name in [source.name, target.name, display_name or target.name, *aliases.values_list("name", flat=True)]:
        if RoomAlias.objects.filter(studio=target.studio, normalized_name=normalize(name)).exclude(room_id__in=[source.pk, target.pk]).exists() or Room.objects.filter(studio=target.studio, active=True, normalized_name=normalize(name)).exclude(pk__in=[source.pk, target.pk]).exists():
            blockers.append(f"Room name {name} is assigned elsewhere.")
    evidence = {
        "rooms": _snapshot(Room.objects.filter(pk__in=[source.pk, target.pk])),
        "classes": _snapshot(ScheduledClass.objects.filter(pk__in=[c.pk for c in classes])),
        "matches": _snapshot(AttendanceClassMatch.objects.filter(attendance_visit__site_id=source.site_id,
            attendance_visit__visit_studio_id=source.studio_id, attendance_visit__visit_date__in=affected_dates)),
        "templates": _snapshot(WeeklyRoomTemplate.objects.filter(room_id__in=[source.pk, target.pk])),
        "slots": _snapshot(ExpectedClassSlot.objects.filter(room_id__in=[source.pk, target.pk])),
        "closures": _snapshot(StudioClosure.objects.filter(room_id__in=[source.pk, target.pk])),
        "aliases": _snapshot(aliases),
    }
    plan = {"source": source.pk, "target": target.pk, "display_name": display_name or target.name,
            "move_classes": moves, "duplicate_classes": duplicates, "blockers": blockers, "affected_dates": affected_dates,
            "templates": len([x for x in evidence["templates"] if x["room_id"] == source.pk]),
            "closures": len([x for x in evidence["closures"] if x["room_id"] == source.pk])}
    token = hashlib.sha256(json.dumps([plan, evidence], cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()
    return plan, token, evidence


@transaction.atomic
def consolidate_rooms(source, target, actor, token, display_name=None):
    Studio.objects.select_for_update(of=("self",)).get(pk=target.studio_id)
    locked = {r.pk: r for r in Room.objects.select_for_update(of=("self",)).filter(pk__in=[source.pk, target.pk])}
    source, target = locked[source.pk], locked[target.pk]
    # Lock existing dependants before rechecking the preview token. Room FK locks
    # also serialize new dependant inserts against consolidation on PostgreSQL.
    for model in (ScheduledClass, WeeklyRoomTemplate, ExpectedClassSlot, StudioClosure, RoomAlias):
        list(model.objects.select_for_update(of=("self",)).filter(room_id__in=[source.pk, target.pk]).order_by("pk"))
    source_dates = ScheduledClass.objects.filter(room=source).order_by().values_list("class_date", flat=True)
    list(AttendanceClassMatch.objects.select_for_update(of=("self",)).filter(
        attendance_visit__visit_studio_id=target.studio_id, attendance_visit__visit_date__in=source_dates).order_by("pk"))
    plan, current_token, evidence = repair_plan(source, target, display_name)
    if token != current_token:
        raise ValidationError("Room records changed. Preview the consolidation again.")
    if plan["blockers"]:
        raise ValidationError({"blockers": plan["blockers"]})
    if not plan["display_name"].strip() or len(plan["display_name"].strip()) > 150:
        raise ValidationError("Invalid display name.")
    # Preserve all report rows and class records. Retire only verified duplicates.
    for pair in plan["duplicate_classes"]:
        retired = ScheduledClass.objects.get(pk=pair["retire"])
        survivor = ScheduledClass.objects.get(pk=pair["keep"])
        if retired.template_id and not survivor.template_id:
            survivor.template_id = retired.template_id
            survivor.expected_from_template = True
            survivor.schedule_status = ScheduledClass.SCHEDULE_STATUS_MATCHED
            survivor.save(update_fields=["template", "expected_from_template", "schedule_status", "updated_at"])
        AttendanceClassMatch.objects.filter(scheduled_class_id=pair["retire"]).update(scheduled_class_id=pair["keep"])
        ExpectedClassSlot.objects.filter(scheduled_class_id=pair["retire"]).update(scheduled_class_id=pair["keep"])
        ScheduledClass.objects.filter(pk=pair["retire"]).update(status=ScheduledClass.STATUS_CANCELLED,
            natural_key=hashlib.sha256(f"room-merge-retired:{pair['retire']}".encode()).hexdigest(),
            reconciliation_notes=f"Retired by room consolidation; surviving class {pair['keep']}.")
    ScheduledClass.objects.filter(pk__in=plan["move_classes"]).update(room=target)
    for model in (WeeklyRoomTemplate, ExpectedClassSlot, StudioClosure):
        model.objects.filter(room=source).update(room=target)
    source.active = False
    source.save(update_fields=["active", "updated_at"])
    for name in [source.name, target.name, plan["display_name"], *RoomAlias.objects.filter(room=source).values_list("name", flat=True)]:
        _alias(target, name, actor, excluding=source.pk)
    for field in ("group_capacity", "private_capacity"):
        if not getattr(target, field):
            setattr(target, field, getattr(source, field))
    target.name = plan["display_name"].strip()
    target.normalized_name = normalize(target.name)
    # The inactive room keeps its historical label; release the old unique lookup key.
    source.normalized_name = f"retired-room-{source.pk}"
    source.save(update_fields=["normalized_name", "updated_at"])
    target.save(update_fields=["name", "normalized_name", "group_capacity", "private_capacity", "updated_at"])
    replacements = {p["retire"]: p["keep"] for p in plan["duplicate_classes"]}
    for match in AttendanceClassMatch.objects.filter(attendance_visit__site_id=target.site_id,
            attendance_visit__visit_studio_id=target.studio_id, attendance_visit__visit_date__in=plan["affected_dates"]):
        candidates = list(dict.fromkeys(replacements.get(pk, pk) for pk in match.candidate_class_ids))
        if candidates != match.candidate_class_ids:
            match.candidate_class_ids = candidates
            match.save(update_fields=["candidate_class_ids"])
    # Only unresolved automatic matches are rebuilt; explicit manual choices survive.
    from analytics.views import match_visit_to_class
    classes = ScheduledClass.objects.filter(studio=target.studio, class_date__in=plan["affected_dates"]).exclude(status__in=[ScheduledClass.STATUS_CANCELLED, ScheduledClass.STATUS_UNAVAILABLE])
    by_slot = {}
    for item in classes:
        by_slot.setdefault((item.site_id, item.studio_id, item.class_date, item.start_time.replace(second=0, microsecond=0)), []).append(item)
    for match in AttendanceClassMatch.objects.select_related("attendance_visit").filter(
            attendance_visit__visit_studio_id=target.studio_id, attendance_visit__is_active=True,
            attendance_visit__visit_date__in=plan["affected_dates"], match_method__in=[AttendanceClassMatch.METHOD_AMBIGUOUS, AttendanceClassMatch.METHOD_UNMATCHED]):
        values = match_visit_to_class(match.attendance_visit, by_slot)
        for key, value in values.items():
            setattr(match, key, value)
        match.save()
    RoomIdentityEvent.objects.create(room=target, actor=actor, action="consolidate", evidence=json.loads(json.dumps({"plan": plan, "before": evidence}, cls=DjangoJSONEncoder)))
    return plan
