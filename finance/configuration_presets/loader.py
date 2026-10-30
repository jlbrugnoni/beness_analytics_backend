"""Install the checked-in Dominican setup without copying local IDs or records."""
import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction

from core_data.models import Site, Studio
from finance.models import (
    Account, Category, Company, ConfigurationChange, FeePolicy, SettlementPolicy,
    SourceMapping, TaxProfile, Terminal, normalized_source_value, validate_account_studios,
)

PRESET_PATH = Path(__file__).with_name("beness_dominicana.json")
MODELS = {
    "accounts": Account, "categories": Category, "terminals": Terminal,
    "source_mappings": SourceMapping, "fee_policies": FeePolicy,
    "settlement_policies": SettlementPolicy, "tax_profiles": TaxProfile,
}


def load_preset():
    return json.loads(PRESET_PATH.read_text())


def install_preset(*, site, actor, apply=False, preset=None):
    """Dry-run by default. Fail on conflicts; never overwrite existing settings."""
    if not actor.is_active or not actor.is_superuser:
        raise ValidationError("Use an active superuser as the deployment audit actor.")
    preset = load_preset() if preset is None else preset
    if preset.get("schema_version") != 1 or set(preset) != {"schema_version", "company", *MODELS}:
        raise ValidationError("Unsupported configuration preset format.")
    if preset["company"]["name"] != "Beness Dominicana" or preset["company"]["country_code"] != "DO":
        raise ValidationError("This preset is only for Beness Dominicana in Dominican Republic.")
    counts = {section: {"created": 0, "unchanged": 0} for section in ["company", *MODELS]}
    with transaction.atomic():
        # Serialize installs for this destination, including initial company creation.
        site = Site.objects.select_for_update().get(pk=site.pk)
        if site.country_code != preset["company"]["country_code"]:
            raise ValidationError("Select the existing Dominican Republic site (DO).")
        required_studios = {row["studio"] for section in ["terminals", "source_mappings"]
                            for row in preset[section] if row["studio"]}
        required_studios.update(name for row in preset["accounts"] for name in row["studios"])
        studios = {}
        for name in sorted(required_studios):
            matches = list(Studio.objects.filter(site=site, name=name))
            if len(matches) != 1:
                raise ValidationError(f"Expected exactly one existing studio named '{name}' in the selected site.")
            studios[name] = matches[0]

        def ensure(section, model, key, values, studio_ids=None):
            matches = list(model.objects.filter(**key))
            if len(matches) > 1:
                raise ValidationError(f"Ambiguous existing {section}: {key}.")
            obj = matches[0] if matches else model(**values)
            if matches:
                differences = [name for name, value in values.items() if getattr(obj, name) != value]
                if studio_ids is not None and set(obj.studios.values_list("pk", flat=True)) != studio_ids:
                    differences.append("studios")
                if differences:
                    raise ValidationError(f"Existing {section} '{obj}' differs in: {', '.join(differences)}. Resolve before installing; nothing is overwritten.")
                counts[section]["unchanged"] += 1
                return obj
            obj.full_clean()
            obj.save()
            if studio_ids is not None:
                validate_account_studios(obj, Studio.objects.filter(pk__in=studio_ids))
                obj.studios.set(studio_ids)
            after = {}
            for name, value in values.items():
                field = model._meta.get_field(name)
                after[name] = getattr(obj, field.attname) if field.is_relation else field.value_to_string(obj)
            if studio_ids is not None:
                after["studios"] = sorted(studio_ids)
            ConfigurationChange.objects.create(actor=actor, target_type=model._meta.model_name,
                target_id=obj.pk, target_label=str(obj)[:180], before={},
                after={**after, "configuration_preset": "beness_dominicana/v1"})
            counts[section]["created"] += 1
            return obj

        values = {name: value for name, value in preset["company"].items() if name != "country_code"}
        values["site"] = site
        company = ensure("company", Company, {"site": site, "name": values["name"]}, values)
        accounts, categories = {}, {}
        for section, model in MODELS.items():
            rows = preset[section]
            if section == "categories":
                rows = sorted(rows, key=lambda row: row["parent"] is not None)
            for row in rows:
                values = dict(row)
                studio_ids = None
                if model == Account:
                    studio_ids = {studios[name].pk for name in values.pop("studios")}
                    values["company"] = company
                    key = {"company": company, "name": values["name"]}
                elif model == Category:
                    parent = values.pop("parent")
                    values.update(company=company, parent=categories[parent] if parent else None)
                    key = {"company": company, "catalog_code": values["catalog_code"]}
                elif model == Terminal:
                    values["account"] = accounts[values["account"]]
                    values["studio"] = studios[values["studio"]]
                    key = {"account": values["account"], "identifier": values["identifier"]}
                elif model == SourceMapping:
                    values["company"] = company
                    values["studio"] = studios[values["studio"]] if values["studio"] else None
                    key = {"company": company, "source_field": values["source_field"],
                           "normalized_value": normalized_source_value(values["source_value"])}
                else:
                    values["company"] = company
                    key = {name: values[name] for name in ["company", "valid_from", "valid_until"]}
                    if model != TaxProfile:
                        key["channel"] = values["channel"]
                # Restore typed dates/decimals before comparison and model validation.
                values = {name: (value if model._meta.get_field(name).is_relation else model._meta.get_field(name).to_python(value))
                          for name, value in values.items()}
                obj = ensure(section, model, key, values, studio_ids)
                if model == Account:
                    accounts[obj.name] = obj
                elif model == Category:
                    categories[obj.catalog_code] = obj
        if not apply:
            transaction.set_rollback(True)
    return counts
