# Integrated Split System — architecture (M0)

**Status:** M0 design draft — revised per [GPT-6 PR #1 review](https://github.com/ryanandrewbaker/integratedsplitsystem/pull/1#issuecomment-6374685858). No runtime code yet.  
**Domain (proposed):** `integrated_split_system`  
**Behavioural reference (read-only):** [two-state-thermostat](https://github.com/ryanandrewbaker/two-state-thermostat) — `homeassistant/packages/kitchen_auto_climate.yaml`, `homeassistant/lib/kitchen-climate-state-machine.ts`, `homeassistant/lib/kitchen-climate-actuator.ts`, `src/services.ts`, `src/state.ts`

## 1. Purpose

Replace per-room Home Assistant YAML packages (Dual Smart Thermostat virtual entity, helpers, scripts, automations, and actuator chains) with a **single HACS custom integration** that:

- Exposes one native `ClimateEntity` per configured room under **Settings → Devices & services**.
- Owns control logic, mode state, Boost/Dry/Fan Only semantics, and **serialized** physical `climate.*` service calls to an existing underlying climate entity (initially Sensibo).
- Preserves the existing `custom:two-state-thermostat` card through a documented attribute/service contract (M5 packaging).

The Sensibo (or other) integration remains the hardware adapter. This integration never stores vendor credentials.

## 2. PRD alignment review (vs two-state-thermostat)

| PRD theme | Legacy repo reality | Gap / integration response |
|-----------|---------------------|------------------------------|
| Native HA install | Card is HACS Dashboard; logic lives in `homeassistant/packages/*_auto_climate.yaml` (+ generator for Family Room) | Config/options flow + `ClimateEntity` replace YAML surface area |
| Multi-room | One package per room; Kitchen hand-maintained, others generated from `rooms/*.json` | One config entry per physical climate; shared Python modules |
| Dual setpoint + min gap | Virtual climate + card enforce `minimum_target_separation` (default 2°C) | `ClimateEntity` `TARGET_TEMPERATURE_RANGE` + backend enforcement on all writers |
| Operating states | Template sensors (`*_auto_operating_state`) derived from controller | Expose via climate attributes and/or diagnostic entities for card discovery |
| Boost / timer / snapshot | Scripts, `input_boolean`, `timer`, snapshot helpers in YAML | Persist snapshot + deadline in ConfigEntry storage / `Store` |
| Fan Only | Virtual `fan_only` on virtual climate; actuator maps to physical `fan` / `fan_only` | Virtual `HVACMode.FAN_ONLY` + capability-gated physical mapping |
| Dry | Separate `switch.*_dry_mode`, not climate HVAC mode | Integration-internal Dry flag + physical `dry` when supported |
| Safe actuator | `kitchen-climate-actuator.ts` mirrors YAML: intent counter, min-cycle deferral, convergence checks | Python `Actuator` with same invariants; shadow mode for migration |
| Diagnostics | Debug log prefix, command counters in YAML | Native diagnostics + repair issues |
| Card | Calls `climate.*` **and** helpers (`script`, `input_boolean`, `input_select`, `switch`) per `src/services.ts` | M4: companion shims + attributes; M5: optional native card services |

**Verified from repo (not live HA):** Kitchen and Family Room entity IDs and temperature source definitions in `homeassistant/rooms/kitchen.json` and `family_room.json`. Olivia, Alice, and main bedroom are **blocked** in repo audit (`audit_status: blocked`). Live `hvac_modes` / `fan_modes` for any room are **unverified** until operator export.

## 3. System context

```text
┌─────────────────────────────────────────────────────────────────┐
│  Lovelace: custom:two-state-thermostat (existing repo, unchanged) │
│  Reads/writes virtual ClimateEntity + optional legacy attributes │
└────────────────────────────┬────────────────────────────────────┘
                             │ HA state / services (climate.*)
┌────────────────────────────▼────────────────────────────────────┐
│  integrated_split_system (this repo, future)                     │
│  ┌──────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │ ConfigEntry  │→ │ Controller core │→ │ Actuator (serialized)│ │
│  │ per physical │  │ state machine   │  │ compare-before-send  │ │
│  │ climate      │  │ temp inputs     │  │ ack / retry bounds   │ │
│  └──────────────┘  └─────────────────┘  └──────────┬──────────┘ │
│         ▲                    ▲                        │            │
│         │ options flow       │ sensor subscriptions  │ climate.* │
└─────────┼────────────────────┼────────────────────────┼──────────┘
          │                    │                        ▼
          │            temperature / humidity      ┌──────────────┐
          │            entity states               │ climate.*    │
          └──────────────────────────────────────│ (e.g. Sensibo)│
                                                 └──────┬───────┘
                                                        ▼
                                                   Physical split
```

**Authority rule:** At most one writer may issue physical climate commands per underlying entity. The integration must detect divergence and **not** enter command wars (see `COMPETING_CONTROLS.md` in the card repo).

## 4. Logical components (planned package layout)

Matches PRD §12; names are stable contracts for M1+.

| Module | Responsibility |
|--------|----------------|
| `__init__.py` | Config entry setup/unload; `runtime_data` container |
| `config_flow.py` | User setup: room label, physical climate picker (dedupe), temperature sources, defaults |
| `climate.py` | `ClimateEntity`: `heat_cool`, targets, modes, fan, attributes for card compatibility |
| `controller.py` | Pure/stateful control: bands, Idle/Boost/Maintain, Dry, Fan Only, Boost timer |
| `temperature.py` | Subscriptions, averaging, staleness, unit normalization |
| `actuator.py` | Physical intent, min-cycle, convergence, service call batching, shadow mode |
| `diagnostics.py` | Redacted diagnostics payload, optional diagnostic entities |
| `const.py` / `strings.json` | Domain constants and UI strings |

### 4.1 Config entry model

- **One config entry ↔ one physical `climate` entity ↔ one virtual `ClimateEntity`.**
- Unique ID derived from physical entity registry ID (stable across renames where possible).
- Integration-owned virtual device (not attached to Sensibo config entry).
- Options flow mutates sources and tuning without rebinding physical entity unless explicit reconfigure flow runs.
- Duplicate physical binding: abort with clear error (FR-01).

### 4.2 Controller core

Port **behavior** from reference TypeScript (`kitchen-climate-state-machine.ts`), not YAML line-by-line:

- Inputs: power, `fan_only`, control temperature, heat/cool targets, manual boost flag, heat/cool demand flags, fan auto/manual, prior state/direction.
- Outputs: direction, `off | idle | boost | maintain`, recommended fan stage, whether to apply automatic fan staging.
- Hysteresis bands: reference uses 1.0°C / 1.5°C offsets for heat/cool transitions (see DECISIONS D01).

Fan Only: when virtual fan-only is active and climate is on, state machine returns idle with no automatic fan staging from band logic (reference TS).

#### 4.2.1 Controller state transitions (reference golden table)

Reference function: `computeKitchenClimateController` (`kitchen-climate-state-machine.ts`).  
Example band: `baseLow = 21`, `baseHigh = 24`, `climateOn = true`, `virtualFanOnly = false`, `manualBoost = false`, `fanAutomatic = true`, initial `currentDirection = heat`.

| # | Prior state | Temp (°C) | heat/cool demand flags | Next `desiredState` | Notes |
|---|-------------|-----------|------------------------|---------------------|-------|
| T1 | `maintain` | 22.6 | off | `idle` | Heat idle hysteresis: exit above `low + 1.5` (21+1.5) |
| T2 | `idle` | 22.6 | off | `idle` | Stays idle in band |
| T3 | `idle` | 21.0 | off | `maintain` | Re-enter maintain at/below low |
| T4 | `maintain` | 19.5 | off | `boost` | Heat boost below `low - 1.0` |
| T5 | `boost` | 21.2 | off | `maintain` | Recover into maintain band |
| T6 | `maintain` | any | `heatDemandActive` | `boost` | Debounced demand path |
| T7 | any | any | off, `virtualFanOnly` | `idle` | Fan-only suppresses band logic; `applyAutomaticFanStage = false` |

With **`manualBoost = true`** (Kitchen boolean on), heat band uses `low = baseLow + 1.0` (22 in example); cool band uses `high = baseHigh - 1.0`. Fan staging forces **high** when manual boost and state is `boost` or `maintain` (`kitchen-climate-state-machine.test.ts`).

Operating labels for the card come from `sensor.*_auto_operating_state` templates (Boost/Maintain + direction), not from `hvac_action` alone, unless `usesHvacActionFallback` is enabled on the card.

### 4.3 Temperature service

- Subscribe to each configured source (entity state or `current_temperature` / other attributes on a climate entity).
- Default: equal average of valid numeric readings; single valid reading fallback; none valid → degraded, no new heat/cool demand (FR-02).
- Diagnostics: per-source values, staleness, calculation method.

### 4.4 Actuator

Port invariants from `kitchen-climate-actuator.ts` and package README:

- **Latest intent wins** (serialized queue; supersede stale work).
- **Compare before send** — no periodic churn when settled.
- **Min compressor cycle** default 300s for heat/cool start from off and stop to off; user off bypasses deferred shutdown (reference).
- Fan-only / dry paths: do not apply compressor-only deferral where reference exempts non-compressor modes (FR-07, D10).
- **Shadow mode:** compute intents and log; zero physical `climate.*` calls (migration FR-07).

#### 4.4.1 Acknowledgement vs external conflict

See **DECISIONS.md §D04**. Implementation must mirror Kitchen **convergence checks** (`evaluatePhysicalConverged`, 0.1°C) and **reconcile throttle** (25s after `last_apply`) before treating mismatch as an external writer. Integration adds **`external_conflict_paused`** after bounded failed reconciles so a second HA automation cannot cause command storms.

### 4.5 Boost (canonical backend — not card README alone)

**Source of truth:** `script.kitchen_climate_boost` / `kitchen_climate_cancel_boost` + `manual_boost` flag in actuator — **not** a virtual `target_temp_*` shift.

| Concern | Kitchen / TS behaviour | Integration v1 |
|---------|------------------------|----------------|
| Start Boost | Boolean on + 30m timer | Same |
| Virtual setpoints | Unchanged | Same |
| Control bands | ±1°C on active direction when boolean on | Port `computeKitchenClimateController` |
| Physical boost | 28°C heat / 18°C cool when controller `boost` | Port `computePhysicalIntent` |
| Card arc ±2°C | `DEFAULT_BOOST_TEMPERATURE_OFFSET = 2` display only | Unchanged card; optional M5 alignment |

Golden scenarios **B1–B7:** `docs/DECISIONS.md` §D01.

### 4.6 Card compatibility layer (summary)

Attributes on the climate entity are for **discovery** (`two_state_thermostat`, entity ID pointers). The card still invokes **services on those entities** (`src/services.ts`). M4 requires **companion shim entities** (scripts, helpers, sensors) wired to the integration coordinator. Full contract: **§7**.

**Target end state (M5+):** Optional card changes to call `integrated_split_system` services directly; shims deprecated after acceptance tests.

## 5. Behavior that must be preserved

Derived from card README, package docs, and reference TypeScript (production YAML is authoritative for Kitchen once live version confirmed).

### 5.1 User-facing (card contract)

- Dual heat/cool range with **minimum** separation (default 2°C); wider bands unchanged; opposite target moves only when needed to satisfy minimum gap.
- Operating state feedback: Off, Idle, Boost/Maintain heating/cooling.
- Boost: 30-minute timer + boolean (Kitchen); extend restarts timer; cancel clears boolean/timer; setpoint change cancels Boost via card; high fan while Boost active; fan controls locked on card while Boost active (`readOnly: boostActive`).
- Card boost arc ±2°C is **display-only**; backend parity uses ±1°C bands + 28/18 physical boost (DECISIONS D01).
- Dry: separate manual cycle; suspends normal heat/cool UI semantics; humidity informational.
- Fan Only: virtual `fan_only`; does not use `climate.set_fan_mode` from card; cancels Boost when entering fan only.
- Power off intent preserved across restarts (no silent re-enable).

### 5.2 Control / actuator (reference implementation)

- Equal-average control temperature for Kitchen and Family Room source lists (repo-confirmed).
- Controller state machine hysteresis and fan staging rules as in `computeKitchenClimateController`.
- Physical mapping for maintain/boost as in `computePhysicalIntent` (28°C / 18°C boost; maintain offsets).
- Sensibo fan mapping preference order (`mapSelectedFanToSensibo`).
- Manual fan confirmation: do not treat `auto` as satisfying manual high (reference `evaluateFanConfirmation`).
- Min-cycle deferral with timer-based reconcile after HA restart (`minCycleHoldSecondsFromTimestamps` pattern).
- Reconcile throttle 25s and mismatch timers 60s / 90s from Kitchen actuator automation.
- External writer: pause after bounded reconcile (D04), not infinite retaliation.

### 5.3 Operational / migration

- Kitchen: `Kitchen AC Temperature Control` automation must stay **disabled** while package/integration is authoritative.
- Shadow comparison before cutover; one room at a time; rollback disables new writer before re-enabling YAML.

## 6. Home Assistant API considerations

| Area | Approach | Notes |
|------|----------|-------|
| Lifecycle | `ConfigEntry` + `async_setup_entry` / `async_unload_entry` | Store coordinator on `entry.runtime_data` per HA quality scale |
| Entity | `ClimateEntity` subclass | `HVACMode.HEAT_COOL`, `FAN_ONLY`, `OFF`; feature flags for range targets |
| Subscriptions | `async_track_state_change_event` / `entity_component` helpers | Avoid Jinja templates for control temperature |
| Services | `hass.services.async_call("climate", ...)` on **underlying** entity only | Never from frontend to physical entity |
| Persistence | ConfigEntry `data` / `options`; `Store` for boost snapshot, deadlines, compressor timestamps | Survive restart without forcing physical writes |
| Diagnostics | `async_get_config_entry_diagnostics` | Redact tokens; include command stats |
| Repairs | `RepairsFlow` / `issue_registry` | Missing sources, unsupported modes, conflict detection |
| Unload | Cancel listeners, drain actuator | Must not turn off physical AC on removal (FR-08) |
| Testing | `pytest-homeassistant-custom-component` | Fake climate entities; service call assertions |

**Minimum HA / Python versions:** Deferred to M1 (D07). M0 assumes current stable HA APIs (`ClimateEntity`, config flow, diagnostics) without pinning a version number.

**Entity registry:** Use `unique_id` and device registry entries; do not rely on `friendly_name` for logic.

## 7. Dashboard card ↔ integration contract (unchanged card, M4 shims)

Derived from `src/two-state-thermostat.ts` handlers and `src/services.ts`. The card **never** calls `climate.set_fan_mode` on the virtual entity (`FORBIDDEN_SERVICES`).

### 7.1 Per-control contract

| UI control | Card handler | Service call(s) | Config / attribute keys | Shim entity (M4) | Acceptance test (M4+) |
|------------|--------------|-----------------|-------------------------|------------------|------------------------|
| Power | `_togglePower` | `climate.set_hvac_mode` → `heat_cool` or `off`; if off, `cancelDry` first | `entity` / `climate_entity`, `power_on_mode` | Native `ClimateEntity` | `services.test.ts` power payloads + HA fixture |
| Heat/cool knobs | `_handleTargetChange` | If Boost active: `script.turn_on` cancel → `climate.set_temperature` (`target_temp_low/high`, `hvac_mode: heat_cool`) | `entity`, `minimum_target_separation`, `target_step` | Native climate enforces min gap | Dial adjustment + gap enforcement test |
| Boost start / extend | `_handleBoost` | `script.turn_on` → `boost_script_entity` | `boost_script_entity` | `ScriptEntity` → `boost_start` service | Timer + boolean on; no virtual target change |
| Boost cancel | `_handleBoostCancel` | `script.turn_on` → `boost_cancel_script_entity` | `boost_cancel_script_entity` | `ScriptEntity` → `boost_cancel` | Boolean off, timer cancelled |
| Fan only toggle | `_toggleFanOnly` | If enabling and Boost on: cancel Boost → `climate.set_hvac_mode` `fan_only` or `power_on_mode` | `entity`, `power_on_mode` | Native climate `fan_only` | No `set_fan_mode` from card |
| Fan Auto toggle | `_toggleFanAuto` | `input_boolean.turn_on/off` **or** `input_select.select_option` `auto`/`low` | `fan_auto_entity`, `fan_override_entity` | Matching helper entities | Fan auto state sync |
| Fan speed slider | `_handleFanSelect` | May turn off auto → `input_select.select_option` | `fan_override_entity`, `fan_options` / attribute | `input_select` shim | Manual speed not satisfied by `auto` alone on physical |
| Dry “Switch mode” | `_handleSwitchMode` | `switch.turn_off` / domain of `dry_entity` | `dry_entity` | `SwitchEntity` shim | Dry off, UI returns to thermostat |
| Dry start | *(not a card button)* | User/automation turns `dry_entity` **on** | `dry_entity` | Switch + internal dry cycle | Physical `dry` when supported |
| Power off (with Dry) | `_togglePower` | `cancelDry` + `climate.set_hvac_mode` off | `dry_entity` | Same | |
| Operating label | `buildCardViewState` | *(read)* `operating_state_entity` state | `operating_state_entity` | `SensorEntity` with Kitchen-compatible strings | States: Boost/Maintain heat/cool, Idle, Off, Dry, Fan |
| Control temperature | dial display | *(read)* `temperature_entity` | `temperature_entity` | `SensorEntity` computed average | Matches FR-02 |
| Humidity | dial display | *(read)* `humidity_entity` | `humidity_entity` | Optional sensor | |
| Boost countdown | dial | *(read)* `boost_timer_entity`, `boost_active_entity` | `boost_timer_entity`, `boost_active_entity` | `timer` + `input_boolean` | `getBoostState`: active if boolean **or** timer active |
| Effective / recommended fan | fan UI | *(read)* `effective_fan_entity`, `recommended_fan_entity` | attribute pointers | Sensors | Optional for simplified fan UI |

Climate attributes for discovery (card README + `src/config.ts`): `two_state_thermostat`, `temperature_entity`, `operating_state_entity`, `fan_auto_entity`, `fan_override_entity`, `effective_fan_entity`, `recommended_fan_entity`, `boost_*`, `dry_entity`, `humidity_entity`, `power_on_mode`, `fan_options`, `target_step`, `minimum_target_separation`.

### 7.2 Transition plan

1. **M1–M3:** Headless integration; shims may be stubbed or internal-only tests — **no card parity claim**.
2. **M4:** Register shims on integration device; point attributes at shim entity IDs; run row-by-row acceptance tests above.
3. **M5:** Optionally change card to call `integrated_split_system.*` when attribute `integrated_split_system_entry_id` present; keep shims for legacy dashboards.

## 8. Architectural risks

| Risk | Impact | Mitigation (design) |
|------|--------|---------------------|
| Boost semantics (card arc ±2°C vs backend ±1°C / 28/18) | UX confusion | Documented in D01; optional M5 card arc tweak |
| Incomplete card contract | Broken dashboard | §7 shims + M4 acceptance matrix |
| Ack vs external conflict | False positives / storms | D04 phase model + Kitchen throttle constants |
| Unverified Sensibo capabilities per room | Fan Only / Dry / fan speeds fail at runtime | Capability probe at setup; gate features; repair issues |
| External automations writing same physical entity | Beeping, oscillation, safety | Best-effort conflict detection; operator inventory; shadow mode |
| Restart mid Boost / mid min-cycle | Duplicate or missing physical commands | Persist deadlines/timestamps; resume deferred actions like reference |
| Card still expects YAML helpers | Broken UX if attributes missing | Compatibility attribute phase; M5 feature detection in card |
| Dual HACS packages loading two card JS copies | Frontend conflicts | M5 install tests; keep card repo separate until pinned bundle proven |
| Olivia / Alice / main bedroom unknown | Wrong entity binding | Block config templates; require export before entries |
| Over-eager reconciliation | Command storms | Zero-chatter acceptance test (PRD §10) |
| HA API drift | Break on upgrade | Pin minimum version in M1; CI against HA version matrix |

## 9. Milestone map (implementation after M0 approval)

| Milestone | Delivers |
|-----------|----------|
| M1 | Skeleton: manifest, flows, entity registration, no physical writes |
| M2 | Read-only controller + temperature + shadow mode |
| M3 | Actuator safety layer |
| M4 | Full mode parity (Fan Only, Boost, Dry, persistence) |
| M5 | Card packaging / resource registration |
| M6–M7 | Pilot and additional rooms with human approval |

## 10. M0 exit criteria

- [x] PRD reviewed against two-state-thermostat reference
- [x] Architecture + decisions (incl. Boost golden examples, card contract §7, D04 ack policy)
- [x] GPT-6 blockers #1–#3 addressed in docs (PR #1 revision)
- [x] Repository hygiene: single `docs/PRD.md`; default branch `main`
- [ ] User + GPT-6 re-approval before M1 code

**No Python under `custom_components/` until the review gate passes.**
