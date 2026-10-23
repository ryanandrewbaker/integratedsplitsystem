# Engineering instructions for Composer and coding agents

**Read `docs/PRD.md` and `docs/REVIEW_PROCESS.md` before making changes.**

## Project identity

- Product: **Integrated Split System**; repository: `ryanandrewbaker/integratedsplitsystem`; proposed HA domain: `integrated_split_system`.
- Existing `ryanandrewbaker/two-state-thermostat` remains the source for the legacy Lovelace card (`custom:two-state-thermostat`) until an approved packaging milestone.
- Do not confuse or silently rename legacy card types and entity IDs while establishing the new integration.

## Critical safety constraints

- Never deploy to, restart, or send physical commands to the owner's Home Assistant without explicit separate approval.
- Do not modify the existing `ryanandrewbaker/two-state-thermostat` dashboard repository during backend development.
- Preserve the current production YAML controller until a proven and authorized per-room migration.
- Never run two authoritative physical climate writers concurrently for one AC.
- Do not fabricate sensor IDs, supported modes, temperature thresholds or HA runtime readings for Kitchen, Family Room, Olivia, Alice or main bedroom.
- Make every physical command attributable, idempotent where possible, serialized, bounded by confirmation/retry policy, and observable.
- Simulator success is not production proof: require Home Assistant integration fixtures and eventual opt-in physical verification.

## Working agreement

- One milestone, one branch, one draft PR; pause for GPT-6 review before beginning the next milestone.
- Prefer current supported Home Assistant Python APIs (ConfigEntry, ClimateEntity, native diagnostics, options flow and appropriate `runtime_data`). Do not blindly reuse legacy implementation patterns.
- Include tests for lifecycle/restart, multi-room isolation, physical service-call sequences and regression conditions relevant to the milestone.
- Report exact commands/results and unresolved assumptions. Treat anything not verified from user-provided live HA data as **unverified**.
- Do not automatically merge, tag, release or deploy.

## First task (M0)

Read and review `docs/PRD.md`. Create `docs/DECISIONS.md` with proposed resolutions for D01–D10 and a table contrasting old YAML observed behavior with documented intended behavior. **Do not write the runtime implementation until the user approves the architecture and behavior decisions.**
