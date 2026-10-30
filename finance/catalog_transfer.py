"""Portable category catalogs, previewed atomically before any real changes."""
import csv
import hashlib
import io
import json
import re

from django.core import signing
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from core_data.access import get_or_create_user_access_profile, user_has_global_access
from .access import can_use_finance
from .catalog import CATALOG, CATALOG_VERSION
from .configuration import ConfigurationConflict
from .models import Category, Company, ConfigurationChange, normalized_source_value

FIELDS = ('catalog_code', 'parent_code', 'name', 'default_treatment', 'default_allocation', 'sensitive', 'active')
SALT = 'finance.category-catalog.v1'
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2000


def require_catalog_access(user, company):
    if not can_use_finance(user, 'can_import_finance_migration') or not can_use_finance(user, 'can_view_sensitive_finance'):
        raise PermissionDenied('Catalog transfer requires financial migration and sensitive-detail permissions.')
    if not user_has_global_access(user):
        profile = get_or_create_user_access_profile(user)
        if profile.allowed_studios.exists() or not profile.allowed_sites.filter(pk=company.site_id).exists():
            raise PermissionDenied('Catalog transfer requires company-wide site access.')


def safe_cell(value):
    text = str(value)
    return "'" + text if text.startswith("'") or text.lstrip().startswith(('=', '+', '-', '@')) else text


def decode_cell(text):
    if text.startswith("'") and (text[1:].startswith("'") or text[1:].lstrip().startswith(('=', '+', '-', '@'))):
        return text[1:]
    return text


def snapshot(category):
    return {name: getattr(category, name) for name in ('catalog_code', 'parent_id', 'name',
        'default_treatment', 'default_allocation', 'sensitive', 'active', 'revision')}


def export_catalog(company):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    for category in company.categories.select_related('parent').order_by('parent_id', 'catalog_code'):
        values = {name: getattr(category, name) for name in FIELDS if name != 'parent_code'}
        values['parent_code'] = category.parent.catalog_code if category.parent_id else ''
        values['sensitive'] = 'true' if category.sensitive else 'false'
        values['active'] = 'true' if category.active else 'false'
        writer.writerow({key: safe_cell(value) for key, value in values.items()})
    response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="finance-category-catalog-{company.pk}.csv"'
    response['Cache-Control'] = 'no-store'
    return response


def starting_rows():
    rows = []
    for code, name, children in CATALOG:
        rows.append(dict(catalog_code=code, parent_code='', name=name, default_treatment='operating',
            default_allocation='administration' if code == 'administracion' else 'direct', sensitive=code == 'personal', active=True))
        for child_code, child_name in children:
            treatment = ''
            if (code, child_name) in {('operacion', 'Equipamiento'), ('bancos', 'Intereses'), ('bancos', 'Devoluciones')}:
                treatment = 'review'
            elif (code, child_name) in {('administracion', 'Impuestos'), ('otros', 'Extraordinarios')}:
                treatment = 'extraordinary'
            rows.append(dict(catalog_code=f'{code}-{child_code}', parent_code=code, name=child_name,
                default_treatment=treatment, default_allocation='',
                sensitive=code == 'administracion' and child_name in {'Sueldos administración', 'Seguridad social administración'}, active=True))
    return rows


def read_csv(upload):
    if not upload or upload.size > MAX_BYTES:
        raise serializers.ValidationError({'file': 'Choose a UTF-8 CSV file of at most 2 MB.'})
    try:
        text = upload.read(MAX_BYTES + 1).decode('utf-8-sig')
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;')
        reader = csv.DictReader(io.StringIO(text, newline=''), dialect=dialect, strict=True)
        if not reader.fieldnames or len(reader.fieldnames) != len(FIELDS) or set(reader.fieldnames) != set(FIELDS):
            raise ValueError('Use the exact headers from the exported catalog: ' + ', '.join(FIELDS))
        rows = []
        for line, record in enumerate(reader, start=2):
            if line > MAX_ROWS + 1:
                raise ValueError(f'Limit the file to {MAX_ROWS} categories/subcategories.')
            if None in record or any(value is None for value in record.values()):
                raise ValueError(f'Row {line}: incorrect number of columns.')
            row = {key: decode_cell(value).strip() for key, value in record.items()}
            for key in ('sensitive', 'active'):
                if row[key].lower() not in ('true', 'false', '1', '0'):
                    raise ValueError(f'Row {line}: {key} must be true or false.')
                row[key] = row[key].lower() in ('true', '1')
            rows.append(row)
    except (UnicodeError, csv.Error, ValueError) as error:
        raise serializers.ValidationError({'file': str(error)}) from error
    if not rows:
        raise serializers.ValidationError({'file': 'The catalog has no data rows. Export the starting catalog as a template.'})
    return rows


def transfer_catalog(company, user, rows, *, mode='merge', source='csv', expected_plan=None):
    if mode not in ('merge', 'replace'):
        raise serializers.ValidationError({'mode': 'Use merge or replace.'})
    codes = [row['catalog_code'] for row in rows]
    if len(set(codes)) != len(codes) or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', code) for code in codes):
        raise serializers.ValidationError({'file': 'Catalog codes must be unique, 1–64 characters, using letters, numbers, underscores, dots or hyphens.'})
    roots = {row['catalog_code'] for row in rows if not row['parent_code']}
    for index, row in enumerate(rows, start=2):
        if row['parent_code'] and row['parent_code'] not in roots:
            raise serializers.ValidationError({'file': f'Row {index}: include its parent as a root row; only two levels are supported.'})
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=company.pk)
        require_catalog_access(user, company)
        if not company.active:
            raise serializers.ValidationError({'company': 'Activate the company before importing a catalog.'})
        existing = list(company.categories.select_for_update().order_by('pk'))
        state = {'company_revision': company.revision, 'categories': [(obj.pk, snapshot(obj)) for obj in existing]}
        payload = {'company': company.pk, 'actor': user.pk, 'mode': mode, 'source': source,
            'rows': hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
            'state': hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()}
        if expected_plan:
            try:
                previous = signing.loads(expected_plan, salt=SALT, max_age=3600)
            except signing.BadSignature as error:
                raise ConfigurationConflict('This preview expired. Preview the catalog again.') from error
            if previous != payload:
                raise ConfigurationConflict('The catalog, selected options or CSV changed. Preview again before applying.')
        by_code = {obj.catalog_code: obj for obj in existing}
        resolved, used, plans = {}, set(), []
        counts = {'created': 0, 'updated': 0, 'unchanged': 0, 'archived': 0}

        def audit(obj, before):
            ConfigurationChange.objects.create(actor=user, target_type='category', target_id=obj.pk,
                target_label=obj.name, before=before, after={**snapshot(obj), 'catalog_transfer': source})

        for row in sorted(rows, key=lambda value: bool(value['parent_code'])):
            parent = resolved[row['parent_code']] if row['parent_code'] else None
            obj = by_code.get(row['catalog_code'])
            if obj is None:
                # Manual target catalogs may have different generated codes. Preserve
                # existing IDs/codes when the exact normalized name and parent agree.
                obj = next((item for item in existing if item.parent_id == (parent.pk if parent else None)
                    and item.normalized_name == normalized_source_value(row['name'])), None)
            if obj and (obj.pk in used or obj.parent_id != (parent.pk if parent else None)):
                raise serializers.ValidationError({'file': f"Category {row['catalog_code']}: duplicate target or parent change. Existing category references were preserved."})
            before = snapshot(obj) if obj else {}
            if obj is None:
                obj = Category(company=company, parent=parent, catalog_code=row['catalog_code'])
            for name in ('name', 'default_treatment', 'default_allocation', 'sensitive', 'active'):
                setattr(obj, name, row[name])
            try:
                obj.full_clean()
            except ModelValidationError as error:
                raise serializers.ValidationError({'file': f"Category {row['catalog_code']} ({row['name']}): {'; '.join(error.messages)}"}) from error
            action = 'created' if not before else ('updated' if snapshot(obj) != before else 'unchanged')
            if action != 'unchanged':
                if before:
                    obj.revision += 1
                obj.save()
                audit(obj, before)
            used.add(obj.pk)
            resolved[row['catalog_code']] = obj
            counts[action] += 1
            plans.append({**row, 'target_code': obj.catalog_code, 'action': action})
        if mode == 'replace':
            for obj in existing:
                if obj.pk not in used and obj.active:
                    before = snapshot(obj)
                    obj.active = False
                    obj.revision += 1
                    obj.save(update_fields=['active', 'revision', 'updated_at'])
                    audit(obj, before)
                    counts['archived'] += 1
                    plans.append({'catalog_code': obj.catalog_code, 'target_code': obj.catalog_code,
                        'name': obj.name, 'parent_code': '', 'action': 'archived'})
        if any(counts[key] for key in ('created', 'updated', 'archived')):
            before = {'revision': company.revision, 'category_catalog_version': company.category_catalog_version}
            company.revision += 1
            company.category_catalog_version = CATALOG_VERSION if source == 'starting' else 'csv-v1'
            company.save(update_fields=['revision', 'category_catalog_version', 'updated_at'])
            ConfigurationChange.objects.create(actor=user, target_type='company', target_id=company.pk,
                target_label=company.name, before=before, after={'revision': company.revision,
                    'category_catalog_version': company.category_catalog_version, 'catalog_transfer': source,
                    'mode': mode, 'counts': counts, 'rows_hash': payload['rows']})
        result = {'counts': counts, 'rows': plans, 'applied': bool(expected_plan),
            'token': signing.dumps(payload, salt=SALT), 'company': company.pk}
        if not expected_plan:
            transaction.set_rollback(True)
        return result
