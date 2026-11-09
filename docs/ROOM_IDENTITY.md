# Room renames and duplicate-room consolidation

## Operator workflow

Room identity tools appear on Uploads for Attendance and Trainer Availability,
for users with `can_edit_data`. Site/studio restrictions are checked by the API.

For a name that has not been imported yet:

1. Preview the Trainer Availability report.
2. Under Room names and aliases, leave **Create a new room** selected for a genuinely
   new room, or select **Existing room renamed** and the existing room.
3. **Save as renamed room** records the alias and updates the room's display name.
   The old label is retained as an alias. Preview refreshes before importing.
4. Confirm Import as usual. Existing room capacity is reused. Saving a room alias is
   a configuration change and persists even if the file is never imported.

For Estepona, map Sala Grupal to the existing Sala 1 record. Aliases are exact,
case-insensitive, whitespace-trimmed and studio-scoped. They never automatically
link another studio's Sala 1. The Rooms editor also preserves aliases on renaming.
An additional name can be registered without changing the display name.

For two room records already imported:

1. Choose the original room to keep and the duplicate room to retire in the same studio.
2. Enter the final display name, e.g. Sala Grupal.
3. Preview consolidation. It shows classes to move, duplicate classes to retire,
   templates/closures to move, and blocking conflicts.
4. Apply the reviewed preview. Any relevant state change invalidates its token and
   requires a new preview. No automatic production repair or fuzzy name match occurs.

## Preservation and limits

Consolidation is atomic and records actor, plan and before-state evidence in
RoomIdentityEvent. It retains both room records, every original report row and every
scheduled-class record. The duplicate room becomes inactive. Verified duplicate
classes become cancelled and have their import keys retired; their attendance links
and expected-slot references move to the survivor. Candidate lists are updated.
Manual attendance decisions are preserved. Existing ambiguous/unmatched attendance
matches are reevaluated after consolidation; successful and manual matches stay intact.

Weekly templates, legacy expected slots and closures move to the surviving room.
Overlapping templates or colliding legacy expected slots block consolidation until
reviewed. Class duplicates must agree on date, times, instructor, normalized class
name, session type, capacity and status, and have no manual class modifications or
conflicting template links. A matching expected-template placeholder can be retired
in favor of an imported class while preserving its template association. Conflicting
room capacities/types, different class facts and manual corrections are never guessed.
Room capacity edits do not retroactively rewrite historical class capacities.

The import's canonical room ID replaces the raw room label in new trainer class keys.
Legacy class keys are recognized using existing class facts before transitioning in
place. Preview, capacity lookup and conflict detection use the same alias resolution.
Raw report labels and hashes stay unchanged. Repeat and old/new-name overlap imports
reuse the same class record. Multiple existing same-room class candidates require
explicit cleanup rather than arbitrary selection.

## Deployment and validation

Apply `python manage.py migrate` (core_data migration 0022_room_identity) before
serving the updated backend/frontend. Back up the deployment database first. This
migration only adds alias/audit tables; it does not rename or merge saved client data.
Run the preview-and-apply workflow against the intended studio after deployment.

Tests: `core_data.test_room_identity` covers aliases, studio boundaries, existing-name
conflicts, raw report preservation, import/reimport and legacy identity, room editor
renames, permission/scope checks, preview/apply, stale tokens, manual match preservation,
automatic ambiguity recovery, template/closure moves and protected conflicts.
