# Product Requirements Document: Integrated Split System

**Version:** 0.1 (design draft)  
**Date:** 24 October 2026  
**Status:** Proposed, awaiting design review  
**Proposed repository:** `ryanandrewbaker/integratedsplitsystem`  
**Product:** Integrated Split System, native Home Assistant integration with the existing Two State Thermostat dashboard card  
**Source system:** [Two State Thermostat dashboard repository](https://github.com/ryanandrewbaker/two-state-thermostat)  
**Home Assistant integration domain (proposed):** `integrated_split_system`  
**Display name:** Integrated Split System  
**Existing card identity:** `custom:two-state-thermostat` remains unchanged during compatibility/migration

## 1. Executive summary

Build Integrated Split System as a first-class Home Assistant custom integration installed through HACS, using the existing Two State Thermostat frontend and YAML controller as reference implementations. Each configured instance wraps an existing physical `climate` entity (initially Sensibo), creates a native dual-setpoint `ClimateEntity` under **Settings → Devices & services**, manages heat/cool/fan/dry/boost decisions centrally, and presents those decisions in the existing custom Lovelace card.

**One installation, many rooms, one authoritative controller per physical AC.** No room-specific YAML packages, automation chains, scripts, or ad hoc helper entities should be required for a *new* installation once feature parity is achieved.

This is a replacement backend project, **not** a rewrite of the proven Lit dashboard interface and **not** a new Sensibo protocol integration. The source Sensibo entity and its integration remain in place.

## 2. Problem statement and evidence

The current project delivers a strong two-target thermostat UI but delegates virtually all behavior to Home Assistant YAML and the external Dual Smart Thermostat integration. The Kitchen package exceeded 1,300 lines, with a parallel generated Family Room variant. It requires multiple helpers, restart-dependent changes, separate release paths, and hand-maintained entity mappings.

Observed failures during October 2026:

- Fan Only UI selected a virtual `fan_only` mode without a corresponding physical fan-mode actuator path in earlier packages.
- A historical `Kitchen AC Temperature Control` automation wrote to the same physical `climate.kitchen_ac` entity as the new actuator. **Disabling the historical automation stopped continuous beeping.** This is a confirmed conflict, not proof of a hardware fault.
- Generated Family Room YAML initially substituted placeholder temperature sources instead of the actual couch sensor and Sensibo `current_temperature` attribute.
- Live entities for Olivia's room, Alice's room, and main bedroom have not yet been verified.
- Passing isolated TypeScript tests did not validate actual Home Assistant service sequences, device response, or competing automations.

The replacement must reduce operational complexity, provide a traceable command owner, and make configuration and diagnostics discoverable in Home Assistant.

## 3. Goals and measurable outcomes

1. **Native installation:** HACS installs an integration with an Add Integration configuration flow; each configured room produces a native climate entity with stable unique ID and proper entity/device registration.
2. **No YAML requirement:** After migration, a normal user can add and configure a room entirely through the HA UI.
3. **Existing controller compatibility:** Operate through an existing HA `climate` entity, initially Sensibo, using standard HA services and advertised capabilities, without credentials for Sensibo itself.
4. **Complete functional parity:** Dual heat/cool target range, hysteresis, Boost and Maintain, Fan Only, manual/auto fan stages, Dry, min compressor cycles, temperature-source averaging, and meaningful diagnostics.
5. **Command safety:** In steady state, send **zero unnecessary physical climate commands**. Do not automatically battle external automation writers; surface divergence and suspected conflicts instead.
6. **Multi-room:** Independently configure Kitchen, Family Room, Olivia's room, Alice's room and main bedroom without copying controller code or inventing entity IDs.
7. **Safe migration:** Pilot one room only after a shadow/read-only comparison. Each room has backup, cutover and rollback procedures.
8. **Version alignment:** Preserve the current Lit card and provide one compatible, versioned integration/card installation experience after frontend packaging is validated.

**Success measurement:** All configured room climate entities survive restart; control actions work from both the custom card and standard HA climate services; a stable unit receives no service-call storms over a 30-minute observation; changing Fan Only and supported fan speeds is reflected in the physical unit or an explicit unsupported/error state.

## 4. Personas and journeys

**Homeowner/operator:** Installs through HACS, selects an existing physical AC, optionally picks one or more temperature sources, configures target temperatures and protection settings, then selects the created entity in any HA dashboard.

**Advanced operator:** Views requested vs reported HVAC/fan state, source sensor health, last command, retries, and controller operating state through native diagnostics. Can switch to read-only/shadow mode and export redacted diagnostics.

**Existing YAML user:** Migrates one room without losing original sensor selection, comfort targets, or the ability to roll back to the working configuration.

### Primary happy-path user flow

1. Install the new integration via HACS (Integration category) and restart HA as required by HACS.
2. Settings → Devices & services → Add Integration → Integrated Split System.
3. Choose room name and physical `climate` entity. Reject any source already bound to another Integrated Split System config entry.
4. Choose control-temperature source(s): sensor entity state and/or attribute of a selected entity, including `current_temperature` on the physical climate; pick averaging strategy and limits.
5. Set heat/cool defaults, minimum gap, tolerance/hysteresis, compressor protection, fan behavior, Boost/Dry options.
6. Create `climate.<room>_integrated_split_system` (name is a suggestion; actual entity IDs remain user-editable via HA). Register it to the integration and a virtual controller device.
7. Add the existing two-state thermostat card and select the new climate entity. Card works with no extra helper entity IDs.

## 5. Scope

### In scope (v1 target)

- HA custom integration using supported ConfigEntry/config/Options Flow patterns, `ClimateEntity`, device/entity registries, async subscriptions and native diagnostics.
- Multi-instance configuration, each bound to exactly one physical climate entity.
- Single authoritative state machine and command orchestrator per configured instance.
- Variable number of temperature inputs, sensor state or entity attribute, equal-average by default, valid-input fallback, staleness diagnostics, optional sensor weights deferred until confirmed necessary.
- Heat/cool range setpoints and minimum separation enforced by backend, including updates from other dashboard cards and automations.
- Operating modes: Off, Idle, Boost Heat, Maintain Heat, Boost Cool, Maintain Cool, Fan Only, manual Dry.
- Fan auto/manual control; map requested modes only to advertised physical HVAC/fan options.
- Boost with 30-minute default timer, internal boost flag + expiry (Kitchen model, **D01**); extension without compounding; **no** virtual setpoint mutation.
- Compressor short-cycle protection, bounded commands, delayed state acknowledgments, stale-intent cancellation and HA restart recovery.
- Native diagnostics sensors or attributes for operating state, effective temperature, requested/reported fan/mode, source health, command attempt counters, last command and errors.
- Reuse existing Lit Lovelace card, first with explicit compatibility mode, later bundled and version-pinned in the HACS Integration package.
- Test harness using Home Assistant runtime fixtures, fake climate devices and fault injection.
- Migration and rollback instructions per verified room.

### Out of scope (v1)

- Direct Sensibo API, token storage or physical device discovery independent of HA.
- Replacing the official Sensibo integration or controlling hardware bypassing `climate` services.
- Automatic takeover or deletion of existing YAML/automations.
- Automatically detecting **every** external writer: only best-effort warning and observable divergence are promised.
- Whole-home coordination, energy-price scheduling, weather prediction, occupancy optimization, cloud dashboards, or AI control.
- Treating unverified Olivia/Alice/main-bedroom entity names as known.

## 6. Detailed functional requirements

### FR-01. Configuration, entity model and ownership (P0)

- An integration config flow must select a **real** underlying `climate` entity, its room label, and optional temperature sources. Exclude the integration's own virtual entities from eligible source list.
- Each physical climate entity may belong to only one active Integrated Split System config entry. Duplicate configuration aborts cleanly without replacing existing entries.
- Each entry creates a stable, uniquely identified native `ClimateEntity` and an integration-owned virtual device. Do not attach the virtual device to the Sensibo config entry or rely on unsupported cross-entry device registry links.
- Separate options flow supports changing sources and controller settings without recreating an entry. Changing underlying physical climate source requires explicit reconfiguration, with duplicate checks and safe unload/reload.
- Missing required source entities at startup must raise an appropriate retry/repair condition; never send commands to an unknown target.

**Acceptance:** Configure two distinct mock source climates, find both integration entries under Devices & services, reboot and retain stable entities; duplicate physical binding is rejected.

### FR-02. Temperature sourcing (P0)

- Accept one or more temperature readings selected as either `states('sensor.xyz')` or `state_attr('climate.xyz','current_temperature')`, implemented with native HA state subscriptions rather than Jinja.
- Average valid readings equally by default; on one valid reading, fall back to that one. Ignore invalid/unavailable/non-numeric readings. If none is valid or readings are stale beyond configured policy, mark controller degraded and **do not start heat/cool from guessed temperatures**.
- Preserve per-room source selection exactly during migration. Record input values and calculation method in diagnostics.
- Normalize temperature units and precision; validate extreme or implausible readings.

**Known examples, subject to live confirmation:** Kitchen currently references `sensor.livingroom_soil_temperature` + `sensor.kitchen_temperature_feels_like`. Family Room's prior working design references `sensor.familyroom_temperature_couch_temperature` + physical `climate.family_room_ac.current_temperature`. All other rooms remain unverified.

### FR-03. Dual temperature range and state machine (P0)

- Support HA `heat_cool` operation with heating and cooling targets and fixed **minimum** gap (card default 2°C, room-configurable). Preserve wider user-selected gaps. Round to configured target step (current UI commonly 0.5°C).
- Backend enforces gap regardless of client: custom card, default HA card, service call or automation.
- Controller operating state derives from measured control temperature, requested range, tolerance/hysteresis, demand and last safe state. Explicitly distinguish Idle, Boost and Maintain in heating/cooling directions.
- Never let temperature-band logic override a selected Fan Only mode; Dry should likewise own its explicit mode transitions.
- Preserve user power-off intent across restarts; do not silently re-enable climate on entity availability changes.
- Boost semantics are defined in **D01** / `docs/DECISIONS.md` (resolved M0): card ±2°C arc is display-only; backend uses ±1°C control bands and 28/18 physical boost targets without changing virtual setpoints.

### FR-04. Fan Only, manual/automatic fan (P0)

- Fan Only invokes native virtual `HVACMode.FAN_ONLY` and maps to an **advertised** physical `fan` or `fan_only` mode, if present. No silent fallback to Heat or Off that appears successful.
- If unsupported, hide/disable the feature or surface a clear error/repair status. Test against actual Sensibo `hvac_modes` and `fan_modes` before enabling physical control.
- Manual fan request must issue a physical `climate.set_fan_mode` where supported and confirm the requested speed. Automatic fan may accept documented equivalent reported speeds; manual speeds are not silently considered satisfied by `auto`.
- Fan Only should not be blocked by a **compressor-only** minimum off-cycle when engaging ventilation doesn't run the compressor; physical device constraints take precedence.
- Exiting Fan Only resumes selected auto control safely. State changes from other HA clients must be respected.

### FR-05. Boost (P0)

**Canonical model:** Kitchen reference + **D01**. Virtual `target_temp_low` / `target_temp_high` are **not** modified when Boost starts, extends, or ends.

- Start Boost (climate not `off`): set internal **boost active** and **boost expiry** (default 30 minutes); apply ±1°C effective control band on the active direction; when the controller enters `boost`, command physical heat **28°C** / cool **18°C** where applicable; stage **high** fan while manual boost is active (without rewriting the user’s stored fan preference on the virtual climate).
- Extend: restart the 30-minute expiry; **do not** compound band offsets or re-baseline virtual setpoints.
- Cancel / expiry: clear boost active + expiry only; **do not** reverse or “restore” virtual setpoints (they were never changed). Controller and actuator reconcile from **current** virtual setpoints and fan preferences.
- Setpoint change or Fan Only (card): cancel Boost first, then apply the new user intent (B5); new targets are authoritative.
- Expose `boost_active` and `boost_remaining_seconds` on the virtual climate (M5 card) or equivalent sensors.

**Not in scope for Boost:** persisting a duplicate copy of heat/cool targets for later setpoint restoration; card README “snapshot” language applies to legacy YAML UX intent only, not integration virtual target mutation.

### FR-06. Dry (P0)

- Explicit manual Dry/dehumidify control where physical `dry` is supported, independent of the heat/cool range. Do not silently change a target temperature to imitate Dry.
- Suspend ordinary heat/cool control while Dry is active. Switching back restores the prior normal controller state appropriately.
- Surface humidity from selected HA sensor or physical climate attribute if available; humidity readings are informational in v1, with no automatic humidity threshold control.

### FR-07. Safe physical actuator (P0, release blocker)

- **Single serialized command owner per entry.** Requests combine/coalesce on the backend; a later user intent supersedes stale queued operations.
- Compare requested and reported physical mode/temperature/fan before issuing **each** call. Never send redundant commands only to satisfy a periodic timer.
- Command each changed attribute only as needed. Account for device state-report latency with a bounded acknowledgment window and controlled retry/backoff. A persistent mismatch must end in an explicit **unconfirmed/error** status, not an endless retry loop.
- Increment counters and log all outgoing physical service attempts, including failures, intent IDs, expected state, observed state and reasons. Rate-limit diagnostics storage, redact sensitive fields.
- Minimum cycle protection applies to **compressor-relevant** transitions; off requests should not be delayed without explicit agreed safety rationale. Protect restart and timer edge cases.
- Unexpected external physical changes must be visible. Do **not** automatically fight them indefinitely. Detect suspected competing control as best-effort from observed oscillation/HA events, issue a warning and pause reconciliation where prudent.
- Provide a **shadow/read-only mode** that computes proposed commands but never calls the physical climate services.

**Acceptance:** In tests, stable mode/fan/target causes zero physical calls over repeated evaluations; a single intentional change yields only necessary calls; delayed acknowledgments, unavailable device, duplicated triggers and external writes cannot generate an unbounded command storm.

### FR-08. Recovery, configuration storage and removal (P0)

- Persist **user configuration** in ConfigEntry `data` / `options` (sources, thresholds, room label, feature flags).
- Persist **runtime state** per config entry in a supported `Store` (or equivalent), including at minimum:
  - `boost_active` (bool)
  - `boost_expires_at` (UTC timestamp; monotonic deadline for countdown)
  - Actuator: intent generation counter, last physical command fingerprint, `pending_ack` / pause flags, compressor min-cycle timestamps, deferred min-cycle hold deadline (if active)
  - Shadow mode flag (migration)
- **Do not** persist a separate Boost “setpoint snapshot” — virtual targets live on the `ClimateEntity` and are not mutated by Boost (FR-05 / D01).
- On restart: reload persisted runtime state; **read-only** reconcile against physical state first; do not blindly push physical targets or force a compressor cycle.
- **Boost after restart:** If `boost_active` and `boost_expires_at` is still in the future and temperature sources are valid, resume manual boost behaviour; if expired or invalid, clear boost flags safely and report outcome.
- Subscribe/unsubscribe listeners on setup, update, unload; removal must not unexpectedly turn off the physical AC.

### FR-09. Home Assistant UX and diagnostics (P0)

- All instances visible under **Devices & services → Integrated Split System** with independently configurable entries.
- Expose native climate capabilities accurately (`hvac_modes`, `fan_modes`, range target features and supported services), with clear operating state and action; only advertise supported modes.
- Provide native, redacted diagnostics download. Include chosen physical/source entity IDs, available capabilities, control state, last attempted physical commands, ack/timeout statistics and source health.
- Optional diagnostic entities (disabled by default when noisy) may include physical command count, mismatch count, source temperature and controller stage.
- Use HA logging and repair issues for significant unsupported configuration/device failure, rather than anonymous `system_log.write` strings.

### FR-10. Dashboard card and packaging (required before production migration)

- Keep the existing Lit card design as the canonical frontend. **New integration installations** use a **native API** documented in `docs/ARCHITECTURE.md` §7: virtual `ClimateEntity` (dual setpoints, HVAC modes, fan modes via standard `climate.*` services), integration-owned `switch`/`sensor`/`button` entities where needed, and `integrated_split_system.*` services for Boost and other actions that do not map cleanly onto climate services.
- **Do not** register fake `script`, `input_boolean`, `input_select`, or `timer` entities from this integration; those domains are owned by other integrations and are not a supported custom-platform shortcut.
- **Legacy YAML mode:** When the card targets a legacy package virtual climate (no `integrated_split_system` marker), preserve today's helper/script service calls without regression (`src/services.ts`).
- **Integration mode (M5):** Update the card in `ryanandrewbaker/two-state-thermostat` to detect `integrated_split_system` on the selected climate entity and call the native contract only. Ship a **version-pinned** JS build; optional bundling under `custom_components/integrated_split_system/frontend/` after install tests.
- Register/serve JS via supported HA frontend APIs where available; test duplicate Lovelace resource handling.
- **M5 is mandatory before any production room cutover (M6).** M1–M4 are headless backend milestones; they do not require a working dashboard card.

## 7. Nonfunctional requirements

- **Correctness over speed:** Physical device actions must be deterministic, logged and bounded. A temperature control error must never turn into repeated beeping or rapid compressor cycling.
- **HA compatibility:** Use current published HA APIs, async lifecycle, ConfigEntry runtime data, supported feature flags, versioned manifest and quality checks. Agree on a minimum HA version by testing against the operator's installed version and current HA release.
- **No direct tokens:** Rely on the underlying HA climate integration; do not store Sensibo credentials.
- **Privacy:** Store only required entity identifiers, settings and bounded diagnostic metadata. No unrelated `.storage` export or secrets in logs.
- **Testing:** Python unit and HA integration tests with `pytest-homeassistant-custom-component` or current equivalent; mocked service calls, entity registry/config flow, state transitions, restart and stale events. Frontend tests remain in the old card repo until a deliberate source migration.
- **Maintainability:** No room-specific controller forks and no generator as production dependency; per-room differences are config entries/options.
- **CI:** Formatting/linting/type checks, pytest, HA validation/HACS action, manifest checks, frontend asset provenance and a build artifact suitable for review.

## 8. Migration requirements

1. **Inventory first:** Export and confirm physical and temperature entities for all five rooms. Never infer Olivia's, Alice's or main bedroom configuration from naming patterns.
2. **Baseline capture:** Record live existing controllers, disabled legacy automations, exact temperature averaging and configured thresholds; capture a read-only snapshot of operational behavior. The previous `Kitchen AC Temperature Control` conflict must stay disabled.
3. **Shadow stage:** Add new integration bound to a source but with **no physical writes** while old controller remains authoritative. Compare computed actions to observed modes for sufficient real use and fault scenarios.
4. **Card release (M5) before cutover:** Install integration build **and** integration-aware card release; pass every acceptance test in `docs/ARCHITECTURE.md` §7.3. Do not point production dashboards at the new climate entity until M5 is complete.
5. **Cutover one room at a time:** Back up HA config and current settings; explicitly disable all *old physical writers* for that room, then enable exactly one new physical writer. Verify other rooms remain unaffected.
6. **Rollback:** Disable the new controller's physical writes before restoring old automation/package control. Do not run both simultaneously. Preserve prior targets and state snapshots.
7. **Remove legacy YAML only after stable observation:** Migration sign-off includes test of Fan Only, manual fan speed, Boost, Maintain, Dry, Off, restart, delayed physical state, source outage and 30-minute no-chatter stability.

## 9. Delivery milestones and review gates

| Gate | Work | Required evidence before approval |
|---|---|---|
| M0 — PRD and contracts | Agree product, edge cases, modes, source mappings, repository strategy | This PRD reviewed; decisions recorded; no implementation |
| M1 — HA skeleton | Manifest, config flow, entry setup/unload, unique IDs, device/entity registration, tests | Can add/remove 2 fake rooms; no physical writes |
| M2 — Read-only controller | Native climate state model; temperature inputs; dual range; shadow mode; capability validation | Golden state table + pure tests + HA event fixtures |
| M3 — Actuator safety | Serialized command owner; convergence; ack windows; min-cycle; retries; fault handling | Service-call sequence tests, delayed Sensibo fixtures, zero-chatter proof |
| M4 — Mode parity (headless) | Fan Only, manual/auto fan, Boost, Dry, restart/persistence via integration entities/services | HA-level tests for every mode transition; **no** legacy-helper shim entities |
| M5 — Card + packaging (**required before M6**) | Card integration mode; pinned JS; full §7.3 acceptance matrix; optional HACS bundle | All AT-* card tests green; legacy YAML dashboards unchanged |
| M6 — One-room pilot | Inventory, backup, shadow run, cutover and rollback verification (**only after M5**) | Human-authorized live test; command trace and physical confirmation |
| M7 — Multi-room rollout | Additional verified rooms, documentation, release | Room-by-room approval, never bulk auto-deploy |

**At every gate:** Composer works in a feature branch and opens a draft PR. GPT-6 reviews the diff, tests, HA API compatibility and safety; the user approves the next gate. No automatic merge, release, HA restart or physical climate change.

## 10. Release-blocking acceptance scenarios

1. Add two config entries referencing two different physical climates; third duplicate binding is rejected. Both survive HA restart.
2. Control temperature from two real sources averages correctly; one unavailable falls back; both missing prevents new heat/cool demand and exposes degraded status.
3. Heat and cool target gap remains valid for calls from card, standard HA UI and `climate.set_temperature`.
4. Fan Only maps correctly when supported; unsupported mode produces a clear error and no unsupported physical command.
5. Manual High request is not reported as confirmed merely because the physical unit reports Auto.
6. Switching Fan Only ↔ heat/cool and Dry ↔ heat/cool never causes oscillating physical mode commands.
7. Boost extend restarts expiry without compounding; cancel/expiry clears boost flags only (virtual setpoints unchanged); restart restores boost only if expiry still valid (FR-05/FR-08).
8. A settled unit receives **zero calls** while monitored for 30 minutes with normal sensor updates.
9. Inject slow/no physical state acknowledgment; retry remains bounded and ends in unconfirmed state, not a loop.
10. Inject competing external `climate.turn_off` calls; warn/report, do not retaliate indefinitely.
11. Verify compressor minimum-off-time across restart, while fan-only ventilation is not incorrectly delayed by compressor-only protection.
12. Uninstall/unload integration without stopping an active physical unit or orphaning active listeners.
13. Test old frontend card while the new integration is installed and verify no duplicate Lovelace JS resource collision.
14. Demonstrate rollback to old per-room package with old controller disabled during new operation and vice versa.
15. With `integrated_split_system` climate selected, every dashboard control in §7.3 invokes the native contract (not `script`/`input_*` helpers).
16. `integrated_split_system.resume_control` after a pause does not replay superseded physical command intents.
17. `integrated_split_system.boost_start` / `boost_cancel` with `target.entity_id` on one virtual climate does not change Boost state on a second entry’s climate (multi-room isolation).
18. Service calls with missing target, wrong domain, or non-integration climate entity fail validation without side effects.

## 11. Known risks and open decisions

| ID | Question / risk | Owner / resolution gate |
|---|---|---|
| D01 | Boost semantics (card arc vs Kitchen backend) | **Resolved M0** — see `DECISIONS.md` D01; FR-05 aligned |
| D02 | Supported physical `hvac_modes`/`fan_modes` of each actual Sensibo entity are **unverified** | Live inventory before M4/M6 |
| D03 | Actual identifiers for Olivia's, Alice's and main bedroom remain unknown | Live inventory before room migration |
| D04 | Should an external physical change temporarily override controller intent or raise an immediate conflict warning? | Policy decision before M3 |
| D05 | Where to keep canonical Lit card source long-term: existing repository vs move to this repo? | Decide before M5; no premature duplicate source fork |
| D06 | Whether HA frontend resource registration can be fully automatic across supported HA versions | Prove in M5 installation tests |
| D07 | HA version minimum and Python version requirements | Choose after checking installed HA and official support in M1 |
| D08 | Existing temperature controls may use unusual room-specific sources/thresholds | Validate baseline before migrating each room |
| D09 | Fine-grained restart and failure policy: safe observation vs reclaiming physical state after restart | Review M2/M3 |
| D10 | Can the actual room hardware circulate fan without compressor and expose native fan HVAC mode? | Check each entity and device capabilities in M2/M4 |

## 12. Architectural guidance (non-binding design sketch)

```text
HACS Integration (new repo)
  custom_components/integrated_split_system/
    manifest.json, __init__.py, config_flow.py, climate.py
    controller.py, actuator.py, temperature.py, diagnostics.py
    const.py, strings.json, translations/, frontend/
           │
   one ConfigEntry per physical climate
           │
  HA native virtual ClimateEntity   ⇄    Existing Lit dashboard card
           │                             (old repo, version-pinned asset)
  pure state machine and safe actuator
           │
  HA climate services → existing Sensibo integration → physical AC
```

Use HA event subscriptions for source data changes, and an internal coordinator/intent queue for physical command evaluation. **No direct service calls from the frontend to the physical Sensibo**; the climate entity owns actions. Entity registry owns entity names/IDs. Avoid depending on mutable `friendly_name` strings. Create an integration-owned virtual device; don't attach to another integration's config entry.

## 13. References

- Current source and card contract: https://github.com/ryanandrewbaker/two-state-thermostat
- Home Assistant native ClimateEntity API: https://contributors.home-assistant.io/core/entities/climate/
- Home Assistant Config Flows: https://contributors.home-assistant.io/core/integrations/config-flow/
- Home Assistant runtime data recommendation: https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/runtime-data/
- HACS custom integration repository requirements: https://www.hacs.xyz/docs/publish/integration/

**PRD approval is the first gate. Do not implement or deploy from this draft before decisions D01–D04 are explicitly reviewed.**
