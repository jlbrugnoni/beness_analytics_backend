# Finance V1.2: permission administration

Date: 2026-10-30. Status: implemented; client acceptance pending.
Branch in backend and frontend: `feature/finance-module-v1.2`.

## Problem and behavior

The user edit form always submits group membership, but the backend previously
rejected any `groups` field for a superuser. This blocked saving an otherwise valid
superuser permission/profile edit, even if membership was unchanged. Superuser
actors can now save group membership and individual grants for superusers. Other
user managers remain forbidden from editing superusers. Superuser `is_active`,
`is_staff`, `is_superuser` fields and deletion remain protected through this app.

Superusers already inherit every capability and unrestricted studio access. Stored
individual grants remain additive and cannot restrict a superuser. The edit page
explains this and refreshes the current user's effective access after a successful
self-edit. `FINANCE_ENABLED` still controls entry into finance, including for
superusers; permission edits cannot bypass it.

Settings → Group permissions now offers Create group. Enter its name, then select
and save its permissions in the existing editor. Assign users through the user form.
New groups have no members and all grants false. No one receives permissions merely
by creating a group. Existing groups, inherited grants, revision conflict checks and
permission audit behavior are preserved.

## API and security

`GET /api/data/groups/` retains the existing array response.
`POST /api/data/groups/` accepts `name` and returns the serialized group (201),
including its new access profile ID. Both require authentication and
`can_manage_users`. Names are required, trimmed, limited to 150 characters and
checked against case-insensitive duplicates. Exact database uniqueness conflicts
return 400. Group, access profile and creation audit are committed atomically;
audit failure rolls them back. No schema/data migration is required.

## Validation

- Finance PostgreSQL regression suite: 386 tests passed, including six new tests
  covering group creation/configuration/assignment, invalid/duplicate names,
  authentication and authorization, audit rollback, superuser self-edit and
  protected role fields. Tests use a disposable database, not finance QA records.
- Frontend production build passed; targeted ESLint includes undefined-name checks.
- Local browser: sign-in, Group permissions, Create group dialog, required-name
  disabled/enabled state and cancel verified. No group or real permission grant was
  created during browser checks.
- No existing local/production users, permissions or financial records changed.

## Client acceptance

1. Sign in as a superuser, open Users → your account → Edit. Save group membership
   and an individual permission. Reopen to confirm the stored values persist and
   that effective superuser permissions still show full access.
2. In Settings → Group permissions create a named group. Select grants, save, reload
   and confirm the values. Assign it to a test user and check effective permissions.
3. Try a duplicate group name; expect validation instead of a duplicate group.
4. With an ordinary user manager, verify superuser edits remain denied. Users without
   Manage users and group permissions must not be able to create or configure groups.

Changes remain local to the development branch pending acceptance; not pushed,
merged or deployed. Production activation/configuration remains a separate step.
