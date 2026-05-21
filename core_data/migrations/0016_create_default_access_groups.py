from django.db import migrations


CAPABILITIES = [
    "can_view_money",
    "can_upload_data",
    "can_edit_data",
    "can_reset_data",
    "can_manage_users",
    "can_view_admin_logs",
]


DEFAULT_GROUPS = {
    "Admin": {
        "can_view_money": True,
        "can_upload_data": True,
        "can_edit_data": True,
        "can_reset_data": True,
        "can_manage_users": True,
        "can_view_admin_logs": True,
    },
    "Manager": {
        "can_view_money": True,
    },
    "Studio Manager": {},
    "Data Operator": {
        "can_upload_data": True,
        "can_edit_data": True,
    },
    "Viewer": {},
}


def create_default_access_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    GroupAccessProfile = apps.get_model("core_data", "GroupAccessProfile")
    for group_name, capabilities in DEFAULT_GROUPS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        profile, _ = GroupAccessProfile.objects.get_or_create(group=group)
        for capability in CAPABILITIES:
            setattr(profile, capability, capabilities.get(capability, False))
        profile.save()


def remove_default_access_profiles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    GroupAccessProfile = apps.get_model("core_data", "GroupAccessProfile")
    group_ids = Group.objects.filter(name__in=DEFAULT_GROUPS).values_list("id", flat=True)
    GroupAccessProfile.objects.filter(group_id__in=group_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core_data", "0015_useraccessprofile_groupaccessprofile"),
    ]

    operations = [
        migrations.RunPython(create_default_access_groups, remove_default_access_profiles),
    ]
