# Phase 15 acceptance

- Advertising placements, campaigns, creatives, targeting, impressions, and clicks are separate portal-scoped domain entities.
- Public ad decisions require the portal feature flag and deterministically apply placement, time window, language, geography, category, and content-type targeting.
- Any content-bound decision or impression uses canonical `ContentItem.id` and the shared public eligibility policy.
- Impression/click client UUID replay is idempotent; conflicting identity reuse is rejected.
- Notification subscriptions are portal/user-owned, CSRF-protected, and never expose stored push credentials or full destinations.
- Email and web-push integrations use configured gateway adapters, bounded delivery retries, durable status, and provider idempotency keys.
- Advertising and notification admin reads require `admin`; mutations additionally require CSRF and write `EditorialAuditLog` rows.
- Texas defaults keep both public features disabled until explicitly enabled.
- Migration `0016_phase_15_ads_notifications` supports upgrade, downgrade to Phase 14, and re-upgrade.
- Backend/frontend focused tests plus the full Phase 0–14 regression suite cover the release.
