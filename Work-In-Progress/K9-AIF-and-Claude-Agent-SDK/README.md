# Pet Store Agentic

**Status: working example.** The deterministic storefront — catalog, cart, checkout, accounts, order history, admin portal, and a live governance gate — is real, running, and tested. The agentic diagnosis path (two interchangeable substrates: Claude Agent SDK and a direct API call) is built and tested but deliberately not wired into the storefront UI yet — see the app's own `/about` page for why. See `PLAN.md` for the full current-status breakdown, `Architecture_Guide.md` and `Detailed_Design.md` for the design, `project.md` for the full build spec.

---

K9-AIF-Framework is Better at what it does — which isn't what the Agent SDK does.

K9-AIF has governance, architectural contracts, substitutability, provenance. The Claude Agent SDK has none of that; it's a harness with an agent loop. But it also has things K9-AIF doesn't build itself: tool execution plumbing, context compaction, session persistence, MCP client wiring. Those are unglamorous and expensive to maintain.

The honest comparison isn't K9-AIF vs. the SDK. It's K9-AIF-over-SDK vs. K9-AIF-over-direct-API — and there the SDK is one substrate option that saves you maintaining a loop, competing with alternatives you may prefer for control or portability reasons.

Where K9-AIF is genuinely stronger is the layer the SDK deliberately leaves empty. Anthropic isn't trying to solve enterprise architecture governance. That gap is your thesis, and it's a real one.

---

*Note: no LLMs were used for this demo application, built on the K9-AIF Framework. No LLMs were harmed.*
