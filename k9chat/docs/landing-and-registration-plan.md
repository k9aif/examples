# K9Chat public showcase: landing page + Keycloak registration

Status: draft for review (2026-10-22). Nothing built yet.

## Goal

chat.k9x.ai sells itself as an application built on the K9-AIF framework.
A visitor first lands on a page that shows how K9Chat is built and why it is
secure, then registers to try it. The chat itself sits behind a login.

## Flow

```
chat.k9x.ai/            landing page (public, no GPU, no session)
  "Register to try it"  -> chat.k9x.ai/register: framework quiz, then the
                           account form once the visitor scores 4/5 or better
                           -> account created in Keycloak, verification email
  "Sign in"             -> Keycloak hosted login (auth.k9x.ai) -> back to /app
chat.k9x.ai/app         the current chat UI, login required
```

No approval queue (that would conflict with the solo-operator,
no-HIL-by-default rule): the quiz is the gate, and it runs unattended.

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

## Registration page: earn your account

To register, a visitor answers 5 questions about how K9Chat and K9-AIF are
built and must get at least 4 right. Every answer is on the landing page, so
reading the showcase is the way in: the page sells itself and filters
drive-bys in one step.

**Question bank**
- About 30 curated multiple-choice questions in a YAML file (e.g.
  `k9chat/registration/questions.yaml`), each with one answer checked by
  Ravi. Not LLM-generated: a quiz with a wrong "right answer" is worse than
  no quiz.
- Drawn from the landing page cards and the existing knowledge files
  (`knowledge/faq.md`, `knowledge/glossary.md`). Examples: "What screens a
  Project file before it's stored?", "What does an SBB build on?", "What
  happens to a pasted link that resolves to a 10.x address?"
- Each attempt draws 5 at random, with the options shuffled.

**Grading and abuse limits**
- Graded on the server. The browser gets questions and option ids, never
  the answers.
- A pass issues a short-lived signed token (about 15 minutes) that the
  account form must present. No token, no account.
- Attempts limited per IP (e.g. 3 per hour) so the bank can't be brute-forced.
- A failed attempt shows the score and which topics were missed (linked to
  the landing page section), not the right answers.
- Honest limit: the answers are public, so a determined person or an
  LLM-driven bot can pass. The quiz is a speed bump and a showcase. Real
  protection stays with accounts, rate limits, Shield, Guardian and
  admin-only switches.

**Account creation**
- Keycloak self-registration is turned off: its hosted page can't check the
  quiz token without a custom Java extension.
- After a pass, K9Chat's register page collects name, email and password and
  creates the user through the Keycloak Admin REST API, with the "verify
  email" required action set. Keycloak sends the verification mail; the
  account works once the email is confirmed.
- The service account K9Chat uses for this holds only the `manage-users`
  role in the realm. Its secret lives in `.env`, never committed.
- Name and email are screened like any other persisted input
  (persist_screen.py) before the account is created.

**Bypass for invited reviewers**
IEEE reviewers and DoW officers shouldn't have to sit a quiz. An invite code
Ravi sends skips it, or the reviewer uses the demo login (see open questions).

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

- **Keycloak:** the existing instance (Podman on PowerAI, port 8113), with a
  new `k9chat` realm. The `k9x` realm stays as it is: it holds the
  framework Zero Trust demo's client (`k9x-cli`) and test users, and public
  self-registered accounts never share it.
- **Public at auth.k9x.ai** through the existing Cloudflare tunnel: only the
  `k9chat` realm's login paths. The `k9x` realm and the admin console
  (`/admin`) stay LAN-only (tunnel path rules).
- **All connection details and secrets in `.env`** (never committed;
  config.yaml reads them as `${VAR}`, with an example `.env` listing the
  names only):

  | Variable | Purpose |
  |---|---|
  | `K9CHAT_KEYCLOAK_URL` | Keycloak base URL, e.g. `https://auth.k9x.ai` |
  | `K9CHAT_KEYCLOAK_REALM` | realm name |
  | `K9CHAT_OIDC_CLIENT_ID` / `K9CHAT_OIDC_CLIENT_SECRET` | login client (authorization-code flow) |
  | `K9CHAT_KEYCLOAK_ADMIN_CLIENT_ID` / `K9CHAT_KEYCLOAK_ADMIN_CLIENT_SECRET` | service account with `manage-users` only |
  | `K9CHAT_INVITE_CODES` | comma-separated quiz-bypass codes for reviewers |
  | `K9CHAT_QUIZ_PASS_MARK` / `K9CHAT_QUIZ_ATTEMPTS_PER_HOUR` | defaults 4 (of 5) and 3 |

- **Email:** Keycloak sends the verification mail through the SMTP account
  configured in the realm. The SMTP host, user and password go in the
  Keycloak container's own `.env` and are applied by the realm import, so
  they never reach K9Chat.

## Open questions for Ravi

1. Login flow: framework ABB (option 1) or K9Chat-only (option 2)?
2. Reviewer bypass: invite codes, the demo/demo login, or both?
3. Who writes the question bank: Ravi drafts, or Claude drafts from the
   landing page and knowledge files and Ravi checks every answer?
4. After login, should Framework Mode be locked ON for `k9chat-user`, with
   Internet Access available only to admins?

## Build order (after review)

1. Landing page at `/`, chat moved to `/app` (no auth yet; content reviewed).
2. Question bank (answers checked by Ravi) and the quiz: draw, server-side
   grading, pass token, attempt limits.
3. Keycloak realm + clients (login client, user-management service account),
   self-registration off, auth.k9x.ai tunnel route, SMTP.
4. Register page: quiz -> account form -> Keycloak Admin API -> verification
   email. Invite-code bypass.
5. OIDC login, account identity, roles; global switches admin-only.
6. Verify: fail the quiz (3/5) and pass it (4/5, 5/5); reuse or forge a pass
   token; exceed the attempt limit; register end to end with email
   verification; user vs admin permissions; rate limits per account; the
   landing and register pages on phone width.
