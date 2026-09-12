# Phase 13 acceptance report

## Architectural findings

- `ContentItem` already defines every Phase 13 content type and remains the sole publication,
  ranking, recommendation, analytics, and community identity.
- The signed receiver contract already supplies an ordered media array with image/video URLs,
  dimensions, duration, provider metadata, rights hints, and attribution. The Site previously lost
  that order, so Phase 13 adds `MediaAsset.position`.
- Schema `1.1` gains the optional `content.content_type` discriminator needed to create all extended
  media types through real ingestion. New items default to `article` when it is omitted, updates
  preserve the stored canonical type, and strict schema `1.0` rejects the field.
- The contract does not define event start/end times, venue addresses, or a live-state machine.
  Public UX therefore exposes only canonical geography, venue entities, media, and content type. It
  does not infer missing schedules or build streaming infrastructure.
- EN/ES continue to be representations of the same canonical item. A missing public Spanish
  translation remains a 404 and never falls back to English under an `/es` URL.

## Implemented surfaces

- Ordered, keyboard-accessible, responsive gallery with thumbnails and attribution.
- Media-first meme page.
- `/shorts` and `/es/shorts` vertical fullscreen-oriented feeds with one active autoplaying video,
  play/pause handoff, native controls, reactions, comments, share, save, related navigation, and
  playback analytics.
- Event story presentation using real canonical location/venue data only.
- Live story presentation using the existing normalized media URL and a non-inferred “Live
  coverage” label.
- Homepage extended-media highlights and type-aware cards without duplicate feed identities.

## Verification scope

- Backend integration tests cover all five types, ordered gallery data, canonical identity,
  public-state and geography isolation, EN/ES and missing-translation behavior, Shorts filtering and
  related selection, community reuse, and canonical analytics for `video_start`, `watch_time`, and
  `completion`.
- Frontend tests cover gallery button/keyboard navigation, highest-visibility Short autoplay
  handoff, document visibility, Strict Mode promise races, deduplicated impressions/playback events,
  and the reactions/comments/share/save/fullscreen/related controls.
- Alembic is checked from a clean database and through upgrade, downgrade, re-upgrade, and
  autogenerate check. The migration changes schema only; tenant feature-flag choices remain data.

Phase 14 and later work is intentionally absent.
