from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import override_settings
from rest_framework.test import APITestCase

from core_data.access import get_or_create_user_access_profile, resolve_access_payload, user_has_capability
from core_data.capabilities import FINANCE_CAPABILITIES
from core_data.models import GroupAccessProfile, Site, Studio
from .access import can_view_sensitive_detail
from .admin import AccountForm
from .models import AccessChange, Account, Company

User = get_user_model()


@override_settings(FINANCE_ENABLED=True)
class FinanceAccessTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("finance-test@example.test")
        self.profile = get_or_create_user_access_profile(self.user)
        self.site = Site.objects.create(name="Finance DO", country_code="DO")
        self.spain = Site.objects.create(name="Finance ES", country_code="ES")
        self.one = Studio.objects.create(site=self.site, name="Finance studio one")
        self.two = Studio.objects.create(site=self.site, name="Finance studio two")
        self.estepona = Studio.objects.create(site=self.spain, name="Finance Estepona")
        self.company = Company.objects.create(name="Finance Dominican company", site=self.site, default_currency="DOP")
        self.es_company = Company.objects.create(name="Finance Spain company", site=self.spain, default_currency="EUR")
        self.shared = Account.objects.create(company=self.company, name="Shared account", currency="DOP")
        self.shared.studios.add(self.one, self.two)
        self.single = Account.objects.create(company=self.company, name="One studio account", currency="DOP")
        self.single.studios.add(self.one)
        self.company_account = Account.objects.create(company=self.company, name="Unassigned company account", currency="DOP")
        self.client.force_authenticate(self.user)

    def grant(self, **values):
        for key, value in {"can_view_money": True, "can_view_finance": True, **values}.items():
            setattr(self.profile, key, value)
        self.profile.save()
        self.profile.allowed_studios.add(self.one)

    def results(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["results"]

    def test_no_default_financial_grants(self):
        payload = resolve_access_payload(self.user)
        self.assertTrue(all(not payload["capabilities"][key] for key in FINANCE_CAPABILITIES))
        self.assertFalse(payload["finance"]["can_enter"])
        self.assertEqual(self.client.get("/api/finance/overview/").status_code, 403)

    def test_anonymous_cannot_enter(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/finance/overview/").status_code, 401)

    def test_finance_router_root_uses_the_same_access_gate(self):
        self.assertEqual(self.client.get("/api/finance/").status_code, 403)
        self.grant()
        self.assertEqual(self.client.get("/api/finance/").status_code, 200)
        with override_settings(FINANCE_ENABLED=False):
            self.assertEqual(self.client.get("/api/finance/").status_code, 403)

    def test_money_and_finance_view_both_required(self):
        self.grant(can_view_money=False)
        self.assertEqual(self.client.get("/api/finance/overview/").status_code, 403)
        self.profile.can_view_money = True
        self.profile.can_view_finance = False
        self.profile.save()
        self.assertEqual(self.client.get("/api/finance/overview/").status_code, 403)

    @override_settings(FINANCE_ENABLED=False)
    def test_disabled_feature_denies_even_granted_users(self):
        self.grant()
        self.assertFalse(resolve_access_payload(self.user)["finance"]["can_enter"])
        self.assertEqual(self.client.get("/api/finance/overview/").status_code, 403)

    def test_admin_keeps_operational_access_without_automatic_finance(self):
        self.user.groups.add(Group.objects.get(name="Admin"))
        self.assertTrue(user_has_capability(self.user, "can_manage_users"))
        self.assertFalse(user_has_capability(self.user, "can_view_finance"))
        self.assertEqual(self.client.get("/api/finance/overview/").status_code, 403)
        self.profile.can_view_finance = True
        self.profile.save()
        self.assertEqual(self.client.get("/api/finance/overview/").status_code, 200)

    def test_superuser_has_explicit_technical_exception(self):
        self.user.is_superuser = True
        self.user.save()
        payload = resolve_access_payload(self.user)
        self.assertEqual(payload["capability_sources"]["can_view_sensitive_finance"], ["superuser"])
        self.assertTrue(payload["finance"]["can_enter"])
        self.assertEqual(len(self.results("/api/finance/accounts/")), 3)

    def test_group_inheritance_and_live_revocation(self):
        group = Group.objects.create(name="Finance group")
        gp = GroupAccessProfile.objects.create(group=group, can_view_money=True, can_view_finance=True)
        self.user.groups.add(group)
        self.profile.allowed_studios.add(self.one)
        payload = resolve_access_payload(self.user)
        self.assertEqual(payload["capability_sources"]["can_view_finance"], ["group:Finance group"])
        self.assertEqual(self.client.get("/api/finance/overview/").status_code, 200)
        gp.can_view_finance = False
        gp.save()
        self.assertEqual(self.client.get("/api/finance/overview/").status_code, 403)

    def test_direct_grant_survives_group_revocation(self):
        group = Group.objects.create(name="Additional finance")
        gp = GroupAccessProfile.objects.create(group=group, can_view_finance=True)
        self.user.groups.add(group)
        self.grant()
        gp.can_view_finance = False
        gp.save()
        self.assertTrue(resolve_access_payload(self.user)["finance"]["can_enter"])

    def test_no_scope_has_no_company_or_account_data(self):
        self.grant(can_view_finance_bank_accounts=True)
        self.profile.allowed_studios.clear()
        self.assertEqual(self.results("/api/finance/companies/"), [])
        self.assertEqual(self.results("/api/finance/accounts/"), [])
        self.assertEqual(self.client.get(f"/api/finance/companies/{self.company.pk}/").status_code, 404)

    def test_cross_site_detail_is_hidden(self):
        self.grant()
        self.assertEqual([r["id"] for r in self.results("/api/finance/companies/")], [self.company.pk])
        self.assertEqual(self.client.get(f"/api/finance/companies/{self.es_company.pk}/").status_code, 404)

    def test_bank_account_capability_is_separate(self):
        self.grant()
        self.assertEqual(self.client.get("/api/finance/accounts/").status_code, 403)
        self.assertNotIn("accounts", self.client.get("/api/finance/overview/").data)

    def test_partial_scope_does_not_reveal_shared_or_unassigned_accounts(self):
        self.grant(can_view_finance_bank_accounts=True)
        self.assertEqual([r["id"] for r in self.results("/api/finance/accounts/")], [self.single.pk])
        for account in [self.shared, self.company_account]:
            self.assertEqual(self.client.get(f"/api/finance/accounts/{account.pk}/").status_code, 404)
        self.profile.allowed_studios.add(self.two)
        self.assertEqual(len(self.results("/api/finance/accounts/")), 2)

    def test_site_wide_scope_sees_company_accounts(self):
        self.grant(can_view_finance_bank_accounts=True)
        self.profile.allowed_studios.clear()
        self.profile.allowed_sites.add(self.site)
        self.assertEqual(len(self.results("/api/finance/accounts/")), 3)

    def test_studio_restriction_takes_precedence_over_sites(self):
        self.grant()
        self.profile.allowed_sites.add(self.site)
        self.profile.allowed_studios.set([self.estepona])
        self.assertEqual([r["id"] for r in self.results("/api/finance/companies/")], [self.es_company.pk])

    def test_sensitive_capability_does_not_replace_other_gates_or_scope(self):
        self.profile.can_view_sensitive_finance = True
        self.profile.save()
        self.assertFalse(can_view_sensitive_detail(self.user))
        self.grant(can_view_sensitive_finance=True, can_view_finance_bank_accounts=True)
        self.assertTrue(can_view_sensitive_detail(self.user))
        self.assertEqual(self.client.get(f"/api/finance/accounts/{self.shared.pk}/").status_code, 404)

    def test_inactive_user_denied_even_if_force_authenticated(self):
        self.grant()
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.get("/api/finance/overview/").status_code, 403)

    def test_accounts_cannot_link_studios_from_another_site(self):
        with self.assertRaises(ValidationError):
            self.single.studios.add(self.estepona)

    def test_reverse_account_membership_also_validated(self):
        with self.assertRaises(ValidationError):
            self.estepona.finance_accounts.add(self.single)

    def test_admin_form_rejects_cross_site_membership(self):
        form = AccountForm(data={"company": self.company.pk, "name": "Bad", "kind": "bank",
                                 "currency": "DOP", "studios": [self.estepona.pk], "active": True})
        self.assertFalse(form.is_valid())

    def test_account_company_and_company_site_cannot_be_reassigned(self):
        self.single.company = self.es_company
        with self.assertRaises(ValidationError):
            self.single.full_clean()
        self.company.site = self.spain
        with self.assertRaises(ValidationError):
            self.company.full_clean()

    def test_existing_seed_groups_receive_no_finance_grants_on_migration(self):
        for gp in GroupAccessProfile.objects.all():
            self.assertTrue(all(not getattr(gp, name) for name in FINANCE_CAPABILITIES))
        self.assertTrue(GroupAccessProfile.objects.get(group__name="Manager").can_view_money)

    def test_finance_foundation_apis_are_read_only(self):
        self.grant(can_manage_finance_settings=True)
        self.assertEqual(self.client.post("/api/finance/companies/", {"name": "Not yet"}).status_code, 405)


class AccessManagementTests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user("access-manager@example.test")
        profile = get_or_create_user_access_profile(self.manager)
        profile.can_manage_users = True
        profile.save()
        self.client.force_authenticate(self.manager)
        self.group = Group.objects.create(name="Partner finance")
        self.target = User.objects.create_user("partner@example.test")
        self.target_profile = get_or_create_user_access_profile(self.target)

    def test_group_catalog_includes_capabilities_and_profile_id(self):
        response = self.client.get("/api/data/groups/")
        self.assertEqual(response.status_code, 200)
        item = next(g for g in response.data if g["id"] == self.group.pk)
        self.assertIsNone(item["access_profile_id"])
        self.assertFalse(item["capabilities"]["can_view_finance"])

    def test_group_create_update_and_revision_audit(self):
        response = self.client.post("/api/data/group-access-profiles/", {
            "group": self.group.pk, "can_view_finance": True, "can_view_money": True,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        url = f"/api/data/group-access-profiles/{response.data['id']}/"
        response = self.client.patch(url, {"can_view_finance": False, "expected_revision": 1}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["revision"], 2)
        self.assertEqual(AccessChange.objects.count(), 2)
        event = AccessChange.objects.first()
        self.assertTrue(event.before["can_view_finance"])
        self.assertFalse(event.after["can_view_finance"])
        response = self.client.patch(url, {"can_view_finance": True, "expected_revision": 1}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(AccessChange.objects.count(), 2)
        self.assertFalse(GroupAccessProfile.objects.get(group=self.group).can_view_finance)

    def test_missing_group_profile_creation_preserves_default_operational_grants(self):
        gp = GroupAccessProfile.objects.get(group__name="Manager")
        group_id = gp.group_id
        gp.delete()
        response = self.client.post("/api/data/group-access-profiles/", {"group": group_id, "can_view_finance": True}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["can_view_money"])

    def test_group_profile_identity_cannot_be_changed(self):
        gp = GroupAccessProfile.objects.create(group=self.group)
        response = self.client.patch(f"/api/data/group-access-profiles/{gp.pk}/", {"group": Group.objects.get(name="Viewer").pk})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AccessChange.objects.count(), 0)

    def test_user_flags_and_effective_group_source(self):
        GroupAccessProfile.objects.create(group=self.group, can_view_finance=True)
        self.target.groups.add(self.group)
        url = f"/api/data/user-access-profiles/{self.target_profile.pk}/"
        response = self.client.patch(url, {"can_view_money": True, "can_view_finance": False,
                                           "can_view_sensitive_finance": True, "expected_revision": 1}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["can_view_finance"])
        effective = response.data["effective_access"]
        self.assertTrue(effective["capabilities"]["can_view_finance"])
        self.assertEqual(effective["capability_sources"]["can_view_finance"], ["group:Partner finance"])
        self.assertEqual(AccessChange.objects.first().actor_id, self.manager.pk)

    def test_user_profile_cannot_be_moved(self):
        response = self.client.patch(f"/api/data/user-access-profiles/{self.target_profile.pk}/", {"user": self.manager.pk})
        self.assertEqual(response.status_code, 400)

    def test_user_profile_scopes_logged(self):
        site = Site.objects.create(name="Audit scope", country_code="DO")
        response = self.client.patch(f"/api/data/user-access-profiles/{self.target_profile.pk}/", {"allowed_sites": [site.pk]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AccessChange.objects.first().after["allowed_sites"], [site.pk])

    def test_non_manager_cannot_edit_group_or_user_capabilities(self):
        self.client.force_authenticate(self.target)
        self.assertEqual(self.client.post("/api/data/group-access-profiles/", {"group": self.group.pk}).status_code, 403)
        self.assertEqual(self.client.patch(f"/api/data/user-access-profiles/{self.target_profile.pk}/", {"can_manage_users": True}).status_code, 403)

    def test_non_superuser_cannot_promote_a_user_or_edit_superuser_profile(self):
        response = self.client.put(f"/api/data/users/{self.target.pk}/", {"is_superuser": True}, format="json")
        self.assertEqual(response.status_code, 403)
        root = User.objects.create_superuser("technical@example.test", "TestPassword123!")
        profile = get_or_create_user_access_profile(root)
        self.assertEqual(self.client.patch(f"/api/data/user-access-profiles/{profile.pk}/", {"can_view_finance": False}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/data/user-access-profiles/{profile.pk}/").status_code, 403)

    def test_audit_failure_rolls_back_permission_change(self):
        url = f"/api/data/user-access-profiles/{self.target_profile.pk}/"
        with patch("finance.audit.log_access_change", side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                self.client.patch(url, {"can_view_finance": True})
        self.target_profile.refresh_from_db()
        self.assertFalse(self.target_profile.can_view_finance)
        self.assertEqual(self.target_profile.revision, 1)

    def test_combined_user_and_profile_update_rolls_back_on_stale_profile(self):
        self.target_profile.revision = 2
        self.target_profile.save()
        response = self.client.put(f"/api/data/users/{self.target.pk}/", {
            "first_name": "Should not persist", "groups": [self.group.pk],
            "access_profile": {"can_view_finance": True, "expected_revision": 1},
        }, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.target.refresh_from_db()
        self.assertEqual(self.target.first_name, "")
        self.assertFalse(self.target.groups.exists())
        self.assertEqual(AccessChange.objects.count(), 0)

    def test_combined_update_saves_membership_and_profile_with_audit(self):
        response = self.client.put(f"/api/data/users/{self.target.pk}/", {
            "groups": [self.group.pk],
            "access_profile": {"can_view_money": True, "can_view_finance": True, "expected_revision": 1},
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.target_profile.refresh_from_db()
        self.assertTrue(self.target_profile.can_view_finance)
        self.assertTrue(self.target.groups.filter(pk=self.group.pk).exists())
        self.assertEqual(set(AccessChange.objects.values_list("target_type", flat=True)), {"user", "user_membership"})

    def test_combined_create_invalid_profile_rolls_back_user_creation(self):
        response = self.client.post("/api/data/users/", {
            "email": "invalid-profile@example.test", "password": "LocalTest123!",
            "access_profile": {"allowed_sites": [99999999]},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="invalid-profile@example.test").exists())

    def test_combined_create_sets_finance_flags_atomically(self):
        response = self.client.post("/api/data/users/", {
            "email": "new-finance@example.test", "password": "LocalTest123!",
            "access_profile": {"can_view_money": True, "can_view_finance": True},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(pk=response.data["id"])
        self.assertTrue(user.access_profile.can_view_finance)

    def test_combined_update_rejects_invalid_profile_object(self):
        response = self.client.put(f"/api/data/users/{self.target.pk}/", {
            "groups": [self.group.pk], "access_profile": [],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.target.groups.exists())

    def test_technical_admin_edits_increment_revision_and_audit(self):
        root = User.objects.create_superuser("admin-audit@example.test", "LocalTest123!")
        self.client.force_login(root)
        gp = GroupAccessProfile.objects.create(group=self.group)
        response = self.client.post(f"/admin/core_data/groupaccessprofile/{gp.pk}/change/", {
            "group": self.group.pk, "can_view_finance": "on", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        gp.refresh_from_db()
        self.assertEqual(gp.revision, 2)
        self.assertTrue(gp.can_view_finance)
        self.assertEqual(AccessChange.objects.first().actor_id, root.pk)
