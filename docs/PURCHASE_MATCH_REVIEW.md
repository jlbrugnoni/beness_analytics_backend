# Sales by Service purchase match review

Branch in both repositories: `fix/service-purchase-match-review`.

## Behavior

Sunday reports may overlap previous weeks. Clear matches and new purchases continue
through the existing matching rules. Recognized purchases retain their stored
identity when repeated rows change order. Ambiguous rows and purchase identifier
conflicts are preserved in a review queue instead of aborting the upload.

An upload with unresolved rows returns HTTP 201 with status `needs_review` and
`service_purchase_pending_rows`. These rows do not create or change purchases;
existing purchases remain in place. The upload result remains visible after its
preview is cleared. Preview counts are estimates; final counts come from import.

Uploads → Purchase match review (`/uploads/purchase-matches`) supports:

- Site, studio, client, and status filters, with paginated results.
- Incoming values compared against the same client's purchases in that studio.
- Update an existing purchase, create a separate purchase, or ignore the input.
- Optional notes, actor/time audit, and history if a missing target requires review again.
- English and Spanish labels and the existing money-visibility restrictions.

The API is `/api/data/purchase-match-reviews/`, with detail `candidates/` and
`resolve/` actions. All endpoints require authentication, `can_upload_data`, and
site/studio access. Resolution requires the latest raw row ID. Updating also
requires the selected purchase ID and its `updated_at` comparison token.

## Consistency

Imports and resolutions lock the studio in PostgreSQL. Existing purchase keys are
never reassigned by this workflow. New-key conflicts use a savepoint, and only the
specific purchase natural-key uniqueness error becomes a review; other database
errors still abort the import.

Pending and resolved inputs are recognized by a fingerprint of purchase facts plus
the ordinal among otherwise identical inputs, independent of the order of distinct
activation/expiration variants. Exact repeat uploads reuse decisions. Every source
row is preserved and linked to its review. Changed facts can need a new review;
this export does not provide an immutable purchase transaction ID.

Manual updates cannot target another client or studio, overwrite a newer import,
or assign two rows from one report to the same purchase. Decisions and metric
rebuilds are atomic: a rebuild failure leaves the row pending. Membership snapshots
cover both old and new dates, including the subsequent not-renewed month; client
monthly and weekly metrics also rebuild. Once all reviews for an import resolve,
its status changes to `completed`.

The feature does not retroactively convert rows skipped by older importer versions.
Reupload the relevant report to bring those rows into the review workflow.

## Setup and validation

Apply backend migration `core_data.0019_service_purchase_match_review` before using
the updated importer or review API. No purchase backfill or deletion is required.

Backend regression command:

```sh
python manage.py test analytics core_data.test_purchase_matching core_data.test_purchase_repair core_data.test_analytics_import_guards
```

Frontend validation: `npm run lint` and `npm run build`.

The new regression suite exercises actual XLSX imports, reordered and unchanged
reports, corrected dates, partial HTTP success, identifier collisions, ambiguity,
all three decisions, repeat uploads, audit history, stale/repeated decisions,
permissions, money masking, rollback, and old/new membership recalculation.

Manual acceptance with a test copy of the failing Piantini report:

1. Preview and import the four-week report for the correct site and studio.
2. Confirm clear rows import and any pending count matches the review queue.
3. Open Uploads → Purchase match review and compare activation/expiration dates.
4. Resolve one row, verifying the purchase, audit entry, and affected metrics.
5. Repeat the same upload and confirm the decision is reused without duplication.
6. Repeat with a changed or reordered report to confirm exceptions remain visible.

Do not remove or deduplicate source rows merely to suppress a review: identical-looking
rows can represent separate legitimate purchases.
