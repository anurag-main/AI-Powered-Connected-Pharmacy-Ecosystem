# WhatsApp Cloud API Integration

> Verified against the source, real MySQL and a real signed webhook: **2026-09-16**.
>
> **Sending is OFF by default.** `WHATSAPP_ENABLED` defaults to `false`, which
> makes the application use an in-memory fake provider. Cloning this repo and
> running the sweep cannot message a real customer.

---

## 1. Which WhatsApp product, and why

| | |
|---|---|
| **WhatsApp Business App** | A phone app. No API. Cannot be automated. **Not usable.** |
| **WhatsApp Business Platform (Cloud API)** | Hosted by Meta, REST over HTTPS, webhooks. **This is what we use.** |
| On-Premises API | Deprecated by Meta. Self-hosted. No reason to choose it. |

Cloud API needs no infrastructure of our own — no container, no certificate, no
media server. For a single pharmacy that is the whole argument.

## 2. What Meta requires

**For development**
* A Meta developer account and an app with the WhatsApp product added.
* A **test phone number** Meta issues free. It can message up to 5 recipient
  numbers, and each recipient must be **added and verified by OTP** in the
  dashboard first.
* A temporary access token (valid ~24 hours) from the API Setup screen.
* `hello_world` — a pre-approved template that exists on every new account, which
  is the right thing to send for the very first end-to-end test.

**For production**
* A verified **Meta Business Account** (business verification: legal name,
  address, documents — this takes days, not minutes).
* A real phone number, **not already registered on WhatsApp**, added and verified.
* A **permanent access token** via a System User. The 24-hour token is a
  development convenience and will expire mid-run in production.
* Every business-initiated template **submitted and approved** by Meta.
* A publicly reachable **HTTPS** webhook URL.
* **India only:** billing must be migrated to INR by **31 Dec 2026** or Meta
  stops delivering messages for that account.

**What requires approval:** the business, the phone number, and each template.
Nothing else.

## 3. Environment variables

All in `.env`, which is gitignored. `.env.example` carries the shape only.

| Variable | Required | Notes |
|---|---|---|
| `WHATSAPP_ENABLED` | no | Defaults `false`. Anything else uses the fake provider. |
| `WHATSAPP_ACCESS_TOKEN` | when enabled | Never reaches the browser. |
| `WHATSAPP_PHONE_NUMBER_ID` | when enabled | The *phone number ID*, not the number. |
| `WHATSAPP_API_VERSION` | no | Defaults `v21.0`. |
| `WHATSAPP_BASE_URL` | no | Defaults `https://graph.facebook.com`. Override to point at a mock. |
| `WHATSAPP_TEMPLATE_NAME` | no | Defaults `refill_reminder`. |
| `WHATSAPP_TEMPLATE_LANGUAGE` | no | Defaults `en`. |
| `PHARMACY_NAME` | no | Rendered into the message as `{{2}}`. |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | for webhooks | Any string; must match Meta's dashboard. |
| `WHATSAPP_APP_SECRET` | for webhooks | Validates `X-Hub-Signature-256`. **Without it every webhook is rejected** — deliberate. |

**The token never leaves the backend.** The browser talks to our FastAPI, which
talks to Meta. There is no code path from Next.js to `graph.facebook.com`, and a
frontend test asserts no token, `Bearer` or `wamid` ever appears in the DOM.

## 4. Template design

```
Hello {{1}}, this is a reminder from {{2}}.
Our records suggest you may be due for a refill.
Reply or visit us if you would like us to prepare it.
```

Category **UTILITY**, not MARKETING — it follows from a transaction the customer
made, which is both cheaper (≈ $0.01 in India) and the honest classification.

**The medicine name is deliberately absent.** A WhatsApp message shows on a lock
screen; "your Metformin is due" tells anyone holding the phone that its owner is
diabetic. No diagnosis, no dosage, no condition. The medicine is discussed in the
shop. A test asserts the medicine name never reaches the template parameters.

### Versioning

`template_name` and `template_language` are **frozen onto each notification**, not
read from config at display time. Templates get edited and re-approved, and
without this a message sent last month would be explained by this month's
wording.

There is deliberately **no invented `template_version` integer**. Meta exposes no
version on an approved template, so any number would be ours alone and would mean
nothing to anyone reading a log. The parameters that were sent are stored, so the
rendered text can always be reconstructed.

## 5. Sending flow

```
scripts/refill_sweep.py                        (cron / Task Scheduler)
  -> NotificationService.run_sweep()
      -> RefillService.find_candidates(due_only, contactable_only)
      -> for each candidate: send_for_candidate()
          consent check            -> STOP if not contactable
          find_by_key(idempotency) -> STOP if already sent
          status = SENDING, attempts += 1
          -> MessagingProvider.send_template()
              -> WhatsAppProvider  POST {base}/{version}/{phone_id}/messages
                 -> Meta Cloud API -> customer's WhatsApp
          ACCEPTED  -> status SENT, store wamid
          RETRYABLE -> status PENDING  (next sweep tries again)
          PERMANENT -> status FAILED
```

Manual sends from `/refills` enter at `send_reminder_for()`, which **re-derives
the candidate from the database first**, so a stale click cannot message someone
who bought the medicine an hour ago.

## 6. Webhook flow

```
Meta -> POST /api/v1/webhooks/whatsapp
  -> app/routers/whatsapp_webhook.py  receive()
       read RAW body   (re-serialising JSON would break the HMAC)
       signature_is_valid(raw, X-Hub-Signature-256)  -> 403 if not
  -> WhatsAppWebhookService.process()
       for each status: dedupe on (wamid, status)
                        find notification by wamid
                        record event, advance status
  -> MySQL
  -> /refills shows the new state
```

`GET` on the same path answers Meta's subscription handshake: it compares
`hub.verify_token` with `compare_digest` and echoes `hub.challenge` **as plain
text**. Returning JSON (with quotes) fails verification with an error that does
not say why.

## 7. Message lifecycle

```
PENDING -> SENDING -> SENT -> DELIVERED -> READ
              |                    
              +-> FAILED           (send error, or a failed webhook)
PENDING ------+-> CANCELLED        (no longer wanted)
```

Three rules make this survive the real world:

**Rank, don't assume order.** Statuses only ever move *up* (`sent` 2 →
`delivered` 3 → `read` 4). Meta can deliver a late `sent` after a `read`, and
without ranking it would drag the message backwards.

**`failed` after `delivered` is ignored.** One message can emit *both* in
multi-device setups — delivered on the phone, failed on a linked desktop. The
customer received it, so delivery wins; marking it failed would send a pharmacist
chasing a reminder that actually arrived.

**Terminal means terminal.** Nothing leaves `FAILED` or `CANCELLED`.

## 8. Idempotency

Two independent guarantees, both enforced by the **database**, not by code:

| Concern | Guarantee |
|---|---|
| Duplicate reminder | `UNIQUE(notifications.idempotency_key)` |
| Duplicate webhook | `UNIQUE(notification_events.provider_event_id, status)` |

The reminder key is `refill:{sale_item_id}:{date}:whatsapp`. Keyed on the sale
**item** rather than `(customer, medicine, date)` so that correcting a sale line's
`days_supply` moves the date and correctly produces a *different* opportunity,
instead of reusing the old one's "already sent" record. The `:whatsapp` suffix
means a future voice reminder for the same opportunity is its own row.

The webhook key is the **pair**, not the wamid alone: one message legitimately
emits `sent`, `delivered` and `read`, all carrying the same wamid. Deduplicating
on the wamid alone would discard delivery and read and freeze every message at
"sent".

`_create()` also catches `IntegrityError` and re-reads the winner's row, because
two sweeps can pass the pre-check simultaneously. The pre-check is the fast path;
the constraint is the guarantee.

## 9. Retry policy

Classification lives in `WhatsAppProvider`, the only layer that should know what
`131026` means.

| Meta says | Outcome | Why |
|---|---|---|
| 200 with a wamid | **ACCEPTED** | |
| 131026 undeliverable, 131047, 132000/1/5/7, 133010 | **PERMANENT** | Retrying can never succeed; it burns quota and damages the number's quality rating, which throttles delivery to every other customer |
| 190 / 10 / 200 auth | **PERMANENT + alert** | Stops *every* message for *every* customer — a human is needed now |
| 429, 80007 | **RETRYABLE** | Rate limited |
| 5xx, timeout, transport error | **RETRYABLE** | |
| any other 4xx | **PERMANENT** | Retrying an error we do not understand is how a bug becomes thousands of failed sends |
| 200 **without** a wamid | **PERMANENT** | No wamid means no webhook can ever match; a retry could duplicate invisibly |

Retries are **not** a sleep loop inside the request — holding a web worker open
for a backoff is how one slow provider takes down the whole API. A retryable
failure returns the row to `PENDING` and the next sweep picks it up.
`MAX_SEND_ATTEMPTS = 3`, then `FAILED`.

## 10. Security

* Token and app secret live only in `.env` (gitignored) and are read server-side.
* Webhooks **fail closed**: no app secret configured ⇒ every POST is rejected. An
  unsigned endpoint would let anyone mark any message as read, or fabricate a
  delivery.
* `compare_digest` for both the signature and the verify token — a
  short-circuiting `==` leaks length and prefix through timing.
* `provider_message_id` is **not** in any API response. A wamid identifies a
  customer's message and has no reason to reach a browser.
* Logs carry ids, never phone numbers, message bodies or tokens. An inbound
  reply's text is explicitly not logged — it is a customer's own words about
  their medicine.
* **No authentication on these endpoints**, like the rest of the project. The
  webhook is signature-protected; `POST /notifications/refill-reminder` is not,
  and anyone who can reach the port can trigger a send to a consenting customer.
  This is the largest outstanding gap.

## 11. Testing

`FakeMessagingProvider` is a **real implementation** of the provider interface,
not a mock of our own code. The entire pipeline — eligibility, persistence, state
machine, idempotency — runs exactly as in production, right up to the wire.

```
tests/unit/test_whatsapp_provider.py   46  error mapping, config, signatures
tests/integration/test_notifications.py 33  pipeline, consent, webhooks
pharmacy-frontend/tests/refills-page.test.jsx  32  status display, manual send
```

## 12. Going live — the checklist

1. Create the Meta app, add WhatsApp, note the **phone number ID**.
2. Add your own number as a **verified test recipient** (OTP).
3. Submit the `refill_reminder` template (category **UTILITY**, 2 body params).
   While waiting, test with the pre-approved `hello_world`.
4. Expose the backend over HTTPS — `ngrok http 8000` is enough for a first test.
5. In Meta → WhatsApp → Configuration, set the callback URL to
   `https://<tunnel>/api/v1/webhooks/whatsapp`, paste your verify token, and
   subscribe to the **messages** field.
6. Fill `.env`, set `WHATSAPP_ENABLED=true`, restart.
7. `python -m scripts.refill_sweep` and watch the logs.
8. Replace the temporary token with a **System User permanent token** before
   anything real depends on it.
