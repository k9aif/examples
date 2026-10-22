# K9Chat public showcase: landing page + Keycloak registration

Status: draft for review (2026-10-22). Nothing built yet.

## Goal

chat.k9x.ai sells itself as an application built on the K9-AIF framework.
A visitor first lands on a page that shows how K9Chat is built and why it is
secure, then registers to try it. The chat itself sits behind a login.

## Flow

```
chat.k9x.ai/            landing page (public, no GPU, no session)
  "Register to try it"  -> Keycloak hosted registration page (auth.k9x.ai)
                           email verification (Keycloak sends it)
  "Sign in"             -> Keycloak hosted login -> back to /app
chat.k9x.ai/app         the current chat UI, login required
```

Registration needs no K9Chat code: self-registration, email verification and
password policy are Keycloak realm settings. There is no approval queue (that
would conflict with the solo-operator, no-HIL-by-default rule). If a tighter
gate is wanted later, use a Keycloak invite code or a registration allowlist,
not a manual queue.

## Landing page

Follows the K9X landing standard: hero, cards, how it works, architecture,
ecosystem, scope, then sign-in. Every claim on a card is a mechanism that
exists in K9Chat or the framework today, and each card links to the code or
doc that proves it.

**Hero.** "K9Chat: a governed chat assistant, built on K9-AIF." One line on
what it is, plus the two buttons (Register, Sign in).

**Cards (the showcase):**

| Card | What it shows | Backed by |
|---|---|---|
| Governed by construction | k9x Shield runs on every agent call: injection, input size and PII checks in, PII check out | `security.shield` in config.yaml; framework BaseAgent |
| A second, semantic gate | Granite Guardian screens messages; reworded attacks that patterns miss | guard_agent.py |
| Nothing is stored unscreened | Project files, instructions and learned facts pass Shield and Guardian before storage; fail closed | persist_screen.py |
| Reads the web safely | Pasted links are fetched with an SSRF guard (public addresses only, redirect and peer checks) and each page is screened for injection | url_fetch.py, framework tool_result_guard |
| No tools, no blast radius | The model can only write text: no code execution, files or network | ChatAgent design |
| Fair use on one GPU | Per-account rate limits, concurrency queue, GPU thermal gate | rate_limit.py, queue_control.py |
| Answers without the LLM when it can | FAQ retrieve-then-rerank on CPU returns curated answers with zero hallucination risk | faq_shortcut.py |
| ABB / SBB | K9Chat is an SBB: framework building blocks, app-specific glue only | framework docs |

**How it works.** One diagram of a message's path: rate limit → FAQ
shortcut → GPU queue → Guardian → Shield ingress → context (knowledge
base, project files, web) → model router → model → Shield egress → reply.
Drawn in default PlantUML style, kept in the framework's docs/diagrams.

**Ecosystem.** Cards linking to Shield, SATAN (proves Shield holds),
Inspector, Sentinel, Studio and the Enterprise Repository.

**Scope.** What a registered user gets (the limits, in plain numbers taken
from config at render time, not hard-coded) and what K9Chat deliberately does
not do.

## Accounts and roles

- **Login:** OIDC authorization-code flow against Keycloak. Token validation
  reuses the framework's `KeycloakAuthenticator`
  (`k9_security/zero_trust/idp_adapters.py`): signature via JWKS, issuer,
  audience, expiry, realm and client roles.
- **The browser redirect and code exchange** is not in the framework today
  (it validates bearer tokens; it doesn't run a login). Options for review:
  1. Add a small OIDC login ABB to the framework, reusable by DAS, Inspector
     and the other K9X apps. Preferred: extend the framework, don't reinvent
     it in each app.
  2. App-level code in K9Chat only.
- **Identity:** the Keycloak `sub` replaces today's random `visitor_id`.
  Projects, rate limits and history are keyed on the account.
- **Roles:**
  - `k9chat-user`: chat, projects, own settings (tone dials, length).
  - `k9chat-admin`: global switches (model, Framework Mode, Internet Access,
    streaming, eval, FAQ). Today any visitor can flip these for everyone.
- **Rate limits** stay, keyed on the account plus IP.

## Deployment

- **Keycloak public at auth.k9x.ai** through the existing Cloudflare tunnel.
  Only the realm's login and registration paths are exposed; the admin
  console (`/admin`) stays LAN-only (tunnel path rule).
- **Email:** Keycloak needs SMTP for verification mail. This is an open
  question below.
- **K9Chat config:** issuer, client id and client secret in `.env`; the
  secret is never committed.

## Open questions for Ravi

1. Is a Keycloak instance already running for the K9X apps (the framework
   docs reference one on port 8113), or is this the first?
2. SMTP for verification mail: which provider/account?
3. Login flow: framework ABB (option 1) or K9Chat-only (option 2)?
4. Keep the demo/demo pattern for reviewers alongside self-registration, or
   registration only?
5. After login, should Framework Mode be locked ON for `k9chat-user`, with
   Internet Access available only to admins?

## Build order (after review)

1. Landing page at `/`, chat moved to `/app` (no auth yet; content reviewed).
2. Keycloak realm + client, auth.k9x.ai tunnel route, SMTP.
3. OIDC login, account identity, roles; global switches admin-only.
4. Verify: register a new account end to end, email verified, user vs admin
   permissions, rate limits per account, the landing page on phone width.
