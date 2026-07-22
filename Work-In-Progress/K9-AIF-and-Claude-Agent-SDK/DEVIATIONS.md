# Deviations from `project.md` — verified against installed packages

Per `project.md` §0 and `CLAUDE.md`'s deviation policy: the installed package wins,
always. This file records where the actual installed `claude-agent-sdk` (0.2.125)
differs from what the spec assumed, and how the implementation follows the real
API instead of the guess.

---

## 1. Hook payloads are `TypedDict`, not attribute-access objects

`project.md` §6's pseudocode wrote `payload.tool_name`. The real
`PreToolUseHookInput` is a `TypedDict`:

```python
{
    "session_id": str, "transcript_path": str, "cwd": str,
    "permission_mode": str, "agent_id": str, "agent_type": str,
    "hook_event_name": Literal["PreToolUse"],
    "tool_name": str, "tool_input": dict[str, Any], "tool_use_id": str,
}
```

Access is `payload["tool_name"]`, not `payload.tool_name`.

---

## 2. The gate-deny mechanism is `can_use_tool`, not a `PreToolUse` hook

`project.md` §6 assumed a `PreToolUse` hook returning `deny(reason=...)` was
the mechanism for blocking the livestock fulfillment tool call. The SDK has
**two** related-but-distinct mechanisms:

- **`hooks["PreToolUse"]`** — a list of `HookMatcher`, general-purpose event
  observation/interception, `TypedDict` payload as above.
- **`can_use_tool`** — a dedicated callback on `ClaudeAgentOptions`:
  ```python
  async def can_use_tool(
      tool_name: str,
      tool_input: dict[str, Any],
      context: ToolPermissionContext,
  ) -> PermissionResultAllow | PermissionResultDeny: ...
  ```
  `PermissionResultDeny(behavior="deny", message=str, interrupt=bool)` and
  `PermissionResultAllow(behavior="allow", updated_input=..., updated_permissions=...)`.

**`can_use_tool` is the implementation's chosen mechanism** — it's purpose-built
for exactly "allow or deny this specific tool call," with plain function
arguments rather than a `TypedDict` to unpack, and it's the more idiomatic fit
for a single well-defined gate. `hooks["PreToolUse"]` remains available if a
future gate needs to observe rather than just allow/deny.

---

## 3. Subagents are opt-in, not something to explicitly disable

`project.md` §4 said "disable SDK subagents inside K9-AIF-managed agents,"
implying a flag to turn off. The real mechanism is simpler: subagents only
exist if defined in `ClaudeAgentOptions.agents: dict[str, AgentDefinition]`.
**Simply never populating that field means no subagents can be spawned** —
there's nothing to disable because nothing was enabled. `SdkDiagnosisAgent`
never sets `agents=`, which is the entire mechanism; `test_no_sdk_subagents.py`
asserts this by construction (see that test for how).

---

## 4. Entry points: `query()` and `ClaudeSDKClient`

```python
async def query(*, prompt: str, options: ClaudeAgentOptions | None = None) \
    -> AsyncIterator[UserMessage | AssistantMessage | SystemMessage | ResultMessage | ...]: ...

class ClaudeSDKClient:
    def __init__(self, options: ClaudeAgentOptions | None = None): ...
```

`SdkDiagnosisAgent` uses `query()` — a one-shot diagnosis session doesn't need
`ClaudeSDKClient`'s persistent multi-call session state.

---

## 5. `project.md`'s own tool list didn't include a fulfillment tool

`project.md` §5 lists `SdkDiagnosisAgent`'s tools as `search_catalog`,
`check_species_compatibility`, `retrieve_care_guide`, `check_inventory` --
none of them fulfillment-related. But §6's gate scenario describes the
agent "attempting to call `initiate_fulfillment`" as the adversarial case.
Diagnosis and fulfillment are different concerns, but the gate needs a
concrete tool call to enforce against.

**Resolution:** added `initiate_fulfillment` as a 5th tool on
`SdkDiagnosisAgent` (`petstore/sbb/sdk_tools.py`), specifically so
`test_gate_cannot_be_bypassed.py` has something real to deny. Whether
fulfillment initiation belongs on the diagnosis agent at all, versus
being reachable only from a separate fulfillment-flow agent once the
Router/Orchestrator phases exist, is worth revisiting once Phase 2 is
built -- noted here rather than silently decided.

## 6. Exact qualified tool-name string is unverified

The `allowed_tools` list in `SdkDiagnosisAgent._build_options()` uses bare
tool names (`"search_catalog"`, etc.). Whether the real CLI transport
expects a qualified form (commonly `mcp__<server>__<tool>` in similar SDKs)
isn't confirmable by reading the installed package's Python source alone --
it may be enforced in the underlying CLI subprocess protocol. This can
only be confirmed by an actual live run. If a live run shows tool calls
being rejected or unavailable, update `allowed_tools` and this note.

---

## What did NOT need correcting

`ClaudeAgentOptions` genuinely has `tools`, `system_prompt`, `hooks`,
`permission_mode`, `model`, `max_turns` — the spec's general shape (an options
object configuring a session) was right; only the exact hook/deny mechanism
and subagent-disable story needed correcting above.
