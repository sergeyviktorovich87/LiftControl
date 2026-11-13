# LiftControl Push, self-hosted channel (0.12 prototype)

## Purpose
Keep FCM HTTP v1 as the default low-power Android delivery mechanism while adding
an independent HTTPS channel on our own Django API. Notifications use the same
`organization_id + target + object_id + event_id` identity and the same native
Android notification channels. Only one visible alert should be produced when
both routes deliver an event.

This is **not yet an always-on Android background push service**. Phase 1 is an
authenticated, cursor-based feed polled every 20 seconds by the active Flutter
process. Android can suspend it in Doze, after force-stop, or when the app is
removed from the background. Do not rely on it alone for trapped passengers
or other emergency response. FCM remains enabled and unchanged.

## Included in this branch

- `GET /api/mobile/push/self/` backed by the existing immutable ticket and
  personal-task events. No new data tables or migrations are required.
- Scoped to a valid Android `MobileSession`, an active organization membership,
  the selected `X-Organization-ID`, and notification preferences.
- Metadata only: target, record and event IDs, action, status, category and time;
  no lift addresses, texts, phones, credentials, or attachment URLs.
- Two independent monotonically increasing cursors (`tickets_after`,
  `tasks_after`) and `bootstrap=1` to avoid a flood of old alerts.
- Ignore superseded changes and changes older than 30 minutes.
- App stores cursors in encrypted local storage scoped by server/user/org;
  stopped and revoked sessions cannot continue polling.
- FCM and the self-hosted path converge in `displayPushEvent`, which uses
  the existing Android notification API and shared duplicate-event cursor.
- Opt-in through `SELF_PUSH_ENABLED=true`. The default is OFF.
- Named diagnostic events (no tokens or payloads) and authorization tests.

### Example API response

```json
{
  "provider": "LIFTCONTROL",
  "events": [
    {
      "target": "ticket",
      "organization_id": 1,
      "ticket_id": 25,
      "event_id": 190,
      "kind": "created",
      "priority": "ENTRAPMENT",
      "status": "NEW",
      "created_at": "2026-11-13T10:00:00+00:00"
    }
  ],
  "tickets_after": 190,
  "tasks_after": 46,
  "server_time": "2026-11-13T10:00:00+00:00",
  "max_age_seconds": 1800
}
```

Use `Authorization: Bearer <mobile-session-token>` and
`X-Organization-ID: <id>` over HTTPS. Never expose the token in URLs,
logs, analytics, or push messages.

## Deployment procedure for test only

1. Finish and tag backend 0.11 first. Rebase this branch onto the verified 0.11
   release and resolve Android/API changes before merging.
2. Run the Django tests and Android analysis, tests and APK build in CI.
3. Create a PostgreSQL backup, deploy the candidate API and signed test APK to
   a staging/test server; do not change production users silently.
4. On staging set `SELF_PUSH_ENABLED=true` for the Django API process and
   restart only that service. FCM credentials are neither changed nor removed.
5. Sign in on Android, verify notifications permissions, create an actual ticket
   and task, then verify two transports emit **one** notification each.
6. Repeat with Google services unavailable; leave the app in foreground for
   the phase-1 test. Check diagnostic records `self_push_poll_ok`,
   `self_event_displayed`, `self_duplicate_suppressed` and FCM diagnostics.

For current working production installations, **do not set**
`SELF_PUSH_ENABLED=true` until the compatible candidate APK and API are
validated together.

## Next phase: independent delivery in background

- Implement an explicitly enabled Android foreground service with an
  authenticated TLS WebSocket connection, notification showing service state,
  app-managed reconnect, bounded backoff, and idempotent event acknowledgement.
- Consider a dedicated ASGI gateway / Redis notification broker as scale
  grows. Do not hold regular Django WSGI workers in long-poll loops.
- Check Google and non-Google Android devices under screen-off and Doze,
  mobile/Wi-Fi switching, force-stop, process kill and battery optimization.
- Build an on-server notification inbox with read/delivered states and clear
  retention, preserving all audit-critical ticket and task history.
- Provide per-device delivery metrics (pending, FCM accepted, self accepted,
  displayed, clicked) without logging message bodies or personal content.
- For trapped-passenger incidents, keep escalation to dispatcher/phone as a
  separate safety policy. No single mobile push system guarantees arrival.
- Perform penetration tests: token reuse, revoked sessions, cross-org IDOR,
  replay/dedup, disconnect storms, oversized payloads and resource exhaustion.

## What the owner must provide

- Now: no secrets or server access for preparation in GitHub.
- During staging: access to the staging VPS and an HTTPS endpoint; one phone
  with Google services and one Honor/Huawei without working FCM; test accounts
  in separate organizations.
- Before organization-wide rollout: production app-signing key in a safe secret
  store, selected delivery settings and an agreed incident-escalation process.
