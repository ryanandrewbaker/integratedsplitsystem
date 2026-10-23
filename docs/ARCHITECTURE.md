# Integrated Split System — architecture (M0)

**Status:** M0 correction — native integration API + M5 card contract ([GPT-6 re-review](https://github.com/ryanandrewbaker/integratedsplitsystem/pull/1#issuecomment-6374685858)). No runtime code yet.  
**Domain (proposed):** `integrated_split_system`  
**Behavioural reference (read-only):** [two-state-thermostat](https://github.com/ryanandrewbaker/two-state-thermostat) — `homeassistant/packages/kitchen_auto_climate.yaml`, `homeassistant/lib/kitchen-climate-state-machine.ts`, `homeassistant/lib/kitchen-climate-actuator.ts`, `src/services.ts`, `src/state.ts`

## 1. Purpose

Replace per-room Home Assistant YAML packages (Dual Smart Thermostat virtual entity, helpers, scripts, automations, and actuator chains) with a **single HACS custom integration** that:

- Exposes one native `ClimateEntity` per configured room under **Settings → Devices & services**.
- Owns control logic, mode state, Boost/Dry/Fan Only semantics, and **serialized** physical `climate.*` service calls to an existing underlying climate entity (initially Sensibo).
- Works with `custom:two-state-thermostat` via a **native integration API** (M5 card update); legacy YAML installations keep the existing helper/script contract unchanged.

The Sensibo (or other) integration remains the hardware adapter. This integration never stores vendor credentials.

## 2. PRD alignment review (vs two-state-thermostat)

| PRD theme | Legacy repo reality | Gap / integration response |
|-----------|---------------------|------------------------------|
| Native HA install | Card is HACS Dashboard; logic lives in `homeassistant/packages/*_auto_climate.yaml` (+ generator for Family Room) | Config/options flow + `ClimateEntity` replace YAML surface area |
| Multi-room | One package per room; Kitchen hand-maintained, others generated from `rooms/*.json` | One config entry per physical climate; shared Python modules |
| Dual setpoint + min gap | Virtual climate + card enforce `minimum_target_separation` (default 2°C) | `ClimateEntity` `TARGET_TEMPERATURE_RANGE` + backend enforcement on all writers |
| Operating states | Template sensors (`*_auto_operating_state`) derived from controller | Expose via climate attributes and/or diagnostic entities for card discovery |
| Boost / timer | YAML boolean + timer (no virtual target shift) | Persist `boost_active` + `boost_expires_at` only (FR-08 / D01) |
| Fan Only | Virtual `fan_only` on virtual climate; actuator maps to physical `fan` / `fan_only` | Virtual `HVACMode.FAN_ONLY` + capability-gated physical mapping |
| Dry | Separate `switch.*_dry_mode`, not climate HVAC mode | Integration-internal Dry flag + physical `dry` when supported |
| Safe actuator | `kitchen-climate-actuator.ts` mirrors YAML: intent counter, min-cycle deferral, convergence checks | Python `Actuator` with same invariants; shadow mode for migration |
| Diagnostics | Debug log prefix, command counters in YAML | Native diagnostics + repair issues |
| Card | Legacy: helpers + `climate.*` (`src/services.ts`) | M5: integration mode uses `ClimateEntity` + `integrated_split_system.*` + integration `switch`/`sensor`; **no** fake `script`/`input_*`/`timer` entities |

**Verified from repo (not live HA):** Kitchen and Family Room entity IDs and temperature source definitions in `homeassistant/rooms/kitchen.json` and `family_room.json`. Olivia, Alice, and main bedroom are **blocked** in repo audit (`audit_status: blocked`). Live `hvac_modes` / `fan_modes` for any room are **unverified** until operator export.

## 3. System context

```text
┌──────────────────────────────────────────────────────────────────┐
│  Lovelace: custom:two-state-thermostat                           │
│  Legacy mode → YAML helpers/scripts  |  M5 integration mode → §7 │
└────────────────────────────┬─────────────────────────────────────┘
                             │ climate.* + integrated_split_system.*
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
| `climate.py` | `ClimateEntity`: dual setpoints, `off`/`heat_cool`/`fan_only`, `fan_mode` (auto + device speeds), integration marker attributes |
| `switch.py` | Dry mode `SwitchEntity` (integration-owned; not `input_boolean`) |
| `sensor.py` | Control temperature, operating state, humidity, boost countdown, fan diagnostics |
| `button.py` | Optional Boost cancel / resume (if not service-only) |
| `services.yaml` | `boost_start`, `boost_cancel`, `resume_control`, shadow toggles |
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

#### 4.4.1 Acknowledgement, unconfirmed device, and external conflict

See **DECISIONS.md §D04**. Three **distinct** outcomes after a physical command:

1. **`pending_ack` / `reconciling`** — waiting or retrying until our **command fingerprint** matches physical state (Kitchen 25s throttle, bounded bursts).
2. **`unconfirmed_device`** — retries exhausted; physical never matched **our** last fingerprint (slow Sensibo, unsupported fan step, device fault). **Not** an external writer. Stop sending; repair names device/ack failure.
3. **`external_conflict_paused`** — sustained mismatch where observed physical state is **inconsistent with any recent integration-issued fingerprint** (manual AC UI, second HA automation). Stop sending; repair names conflict.

`integrated_split_system.resume_control` recomputes from **current** physical state + **current** user intent; it must **not** replay superseded queued commands (GPT-6 M3 clarification).

### 4.5 Boost (canonical backend — not card README alone)

**Source of truth:** `script.kitchen_climate_boost` / `kitchen_climate_cancel_boost` + `manual_boost` flag in actuator — **not** a virtual `target_temp_*` shift.

| Concern | Kitchen / TS behaviour | Integration v1 |
|---------|------------------------|----------------|
| Start Boost | Boolean on + 30m timer (YAML) | Internal state + `integrated_split_system.boost_start` / attributes (M4 headless) |
| Virtual setpoints | Unchanged | Same |
| Control bands | ±1°C on active direction when boolean on | Port `computeKitchenClimateController` |
| Physical boost | 28°C heat / 18°C cool when controller `boost` | Port `computePhysicalIntent` |
| Card arc ±2°C | `DEFAULT_BOOST_TEMPERATURE_OFFSET = 2` display only | Unchanged card; optional M5 alignment |

Golden scenarios **B1–B7:** `docs/DECISIONS.md` §D01.

#### 4.5.1 Persisted Boost and runtime state (FR-05 / FR-08)

| Persisted field | Purpose | On cancel / expiry | On restart |
|-----------------|---------|-------------------|------------|
| `boost_active` | Manual boost equivalent to Kitchen boolean | Set `false` | Restore `true` only if `boost_expires_at` still valid (D09) |
| `boost_expires_at` | UTC deadline for countdown / extend | Cleared or ignored when inactive | If past → clear boost |
| `target_temp_low` / `target_temp_high` | User comfort band on `ClimateEntity` | **Unchanged** by Boost | Loaded from entity state; not a separate boost copy |
| User `fan_mode` / auto preference | Stored on virtual climate | **Unchanged** by Boost; high fan is staging while boost active | Reconcile actuator from current preference |
| Actuator intent generation, fingerprints, pause flags, min-cycle timestamps | Safety (FR-07) | N/A | Read-only reconcile first |

**Explicit non-goals:** No persisted “original setpoint snapshot” for Boost; cancel does not call `climate.set_temperature` to undo Boost.

### 4.6 Public integration surface (no helper-domain shims)

Custom integrations **cannot** register `script`, `input_boolean`, `input_select`, or `timer` platforms. This project uses only supported entity platforms (`climate`, `switch`, `sensor`, `button`, …) plus the integration’s own service namespace.

- **M1–M4:** Headless validation of controller + actuator + services/entities; dashboards may use Developer Tools — **no production card requirement**.
- **M5:** Card **integration mode** implements §7; mandatory before **M6** pilot.
- **Legacy dashboards:** Unchanged card behaviour when the selected entity lacks `integrated_split_system` (see §7.4).

## 5. Behavior that must be preserved

Derived from card README, package docs, and reference TypeScript (production YAML is authoritative for Kitchen once live version confirmed).

### 5.1 User-facing (card contract)

- Dual heat/cool range with **minimum** separation (default 2°C); wider bands unchanged; opposite target moves only when needed to satisfy minimum gap.
- Operating state feedback: Off, Idle, Boost/Maintain heating/cooling.
- Boost: 30-minute timer + boolean (Kitchen); extend restarts timer; cancel clears boolean/timer; setpoint change cancels Boost via card; high fan while Boost active; fan controls locked on card while Boost active (`readOnly: boostActive`).
- Card boost arc ±2°C is **display-only**; backend parity uses ±1°C bands + 28/18 physical boost (DECISIONS D01).
- Dry: separate manual cycle; suspends normal heat/cool UI semantics; humidity informational.
- Fan Only: virtual `fan_only` via `climate.set_hvac_mode` (legacy + integration mode).
- Integration mode fan speeds: `climate.set_fan_mode` on the **virtual** climate (M5 removes legacy card ban for integration targets only).
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
| Entity | `ClimateEntity`, `SwitchEntity`, `SensorEntity`, `ButtonEntity` | Fan via climate `fan_mode`; Dry via integration switch; diagnostics via sensors |
| Integration services | `integrated_split_system.boost_start`, `boost_cancel`, `resume_control`, … | `services.yaml`; M5 card + automations |
| Physical writes | `hass.services.async_call("climate", ...)` on **underlying** entity only | Actuator only; never from frontend to Sensibo |
| Subscriptions | `async_track_state_change_event` / `entity_component` helpers | Avoid Jinja templates for control temperature |
| Persistence | ConfigEntry `data` / `options`; per-entry `Store` for boost flags, actuator safety state, min-cycle timestamps | No boost setpoint snapshot (FR-08) |
| Entity services | Register Boost/resume as **entity-targeted** services on virtual climates | HA [entity services](https://developers.home-assistant.io/docs/dev_101_services/) / 2025+ entity-service APIs |
| Diagnostics | `async_get_config_entry_diagnostics` | Redact tokens; include command stats |
| Repairs | `RepairsFlow` / `issue_registry` | Missing sources, unsupported modes, conflict detection |
| Unload | Cancel listeners, drain actuator | Must not turn off physical AC on removal (FR-08) |
| Testing | `pytest-homeassistant-custom-component` | Fake climate entities; service call assertions |

**Minimum HA / Python versions:** Deferred to M1 (D07). M0 assumes current stable HA APIs (`ClimateEntity`, config flow, diagnostics) without pinning a version number.

**Entity registry:** Use `unique_id` and device registry entries; do not rely on `friendly_name` for logic.

## 7. Dashboard card ↔ integration contract (M5 integration mode)

**Detection (M5 card):** `state_attr(climate, 'integrated_split_system') === true` on the selected entity → **integration mode**. Otherwise → **legacy mode** (today’s `src/services.ts` helper/script calls).

**Marker attributes on virtual `ClimateEntity`:**

| Attribute | Purpose |
|-----------|---------|
| `integrated_split_system` | `true` — enable integration mode |
| `integrated_split_system_entry_id` | Diagnostics / UI only — **not** a service target |
| `two_state_thermostat` | `true` — card compatibility / suggestions |
| `minimum_target_separation`, `target_step`, `power_on_mode`, `fan_options` | Same semantics as legacy card README |
| `operating_state` | String: `off`, `idle`, `boost_heating`, `maintain_heating`, `boost_cooling`, `maintain_cooling`, `fan`, `dry` |
| `boost_active`, `boost_remaining_seconds` | Boost UI (replaces timer/boolean reads) |
| `control_temperature` | Optional inline; else read `sensor.*_control_temperature` |
| `dry_entity_id`, `humidity_entity_id` | Entity ids for integration-owned helpers on same device |

### 7.1 Integration-owned entities (per config entry)

| Entity | Platform | Role |
|--------|----------|------|
| `climate.<room>_integrated_split_system` | `climate` | Primary UI anchor; dual setpoints; HVAC + fan |
| `sensor.<room>_iss_control_temperature` | `sensor` | Averaged control temp (FR-02) |
| `sensor.<room>_iss_operating_state` | `sensor` | Mirror of `operating_state` (for automations) |
| `sensor.<room>_iss_humidity` | `sensor` | Optional display |
| `switch.<room>_iss_dry_mode` | `switch` | Manual Dry cycle (replaces `switch.*_dry_mode` YAML) |
| `sensor.<room>_iss_effective_fan` | `sensor` | Reported vs requested fan (diagnostics) |
| `sensor.<room>_iss_recommended_fan` | `sensor` | Auto-staging recommendation |

Exact entity_id patterns are implementation details; the card reads ids from climate attributes or device registry links.

### 7.2 Integration services (entity-targeted contract)

Services are registered for the integration domain with **`target.entity` restricted to `climate` entities owned by `integrated_split_system`** (see [dev_101_services](https://developers.home-assistant.io/docs/dev_101_services/) and [entity services API changes](https://developers.home-assistant.io/blog/2025/09/25/entity-services-api-changes/)). Callers must supply a **single virtual climate** in `target`; there is **no** config-entry-level Boost service in v1.

**Validation (all services):**

| Check | On failure |
|-------|------------|
| `target.entity_id` present exactly once | `service_validation_error`; no state change |
| Entity exists and `domain == climate` | Same |
| Entity `integration == integrated_split_system` | Same |
| Entity belongs to one config entry coordinator | Same |
| Optional: climate not `off` for `boost_start` (Kitchen script condition) | Reject or no-op with log (implement one behaviour in M4; test in AT-05) |

#### `integrated_split_system.boost_start`

Start or extend Boost (D01 B1/B2). **Does not** write `target_temp_low` / `target_temp_high`.

```yaml
# Example (UI / automation)
action: integrated_split_system.boost_start
target:
  entity_id: climate.kitchen_integrated_split_system
data:
  duration_minutes: 30   # optional; default 30; extend resets expiry to now + duration
```

| Field | Type | Required | Default | Effect |
|-------|------|----------|---------|--------|
| `duration_minutes` | number | no | `30` | Sets `boost_expires_at = now + duration` |

**Side effects:** `boost_active = true`; update `boost_remaining_seconds` attribute; apply manual-boost control bands; may stage high fan via actuator (not by mutating stored setpoints).

#### `integrated_split_system.boost_cancel`

Cancel Boost (D01 B3). **Does not** restore virtual setpoints.

```yaml
action: integrated_split_system.boost_cancel
target:
  entity_id: climate.kitchen_integrated_split_system
data: {}
```

**Side effects:** `boost_active = false`; clear expiry; controller/actuator reconcile from current virtual targets and fan preference.

#### `integrated_split_system.resume_control`

Clear `external_conflict_paused` or operator-cleared `unconfirmed_device` (D04). **Does not** replay superseded command queue.

```yaml
action: integrated_split_system.resume_control
target:
  entity_id: climate.kitchen_integrated_split_system
data: {}
```

**Side effects:** increment intent generation; read current physical + user state; compute fresh intent; may resume physical writes if not in shadow mode.

#### `integrated_split_system.set_shadow_mode`

```yaml
action: integrated_split_system.set_shadow_mode
target:
  entity_id: climate.kitchen_integrated_split_system
data:
  enabled: true
```

### 7.3 Per-control contract and acceptance tests (integration mode)

Legacy reference handlers: `src/two-state-thermostat.ts`. M5 implements a parallel code path.

| ID | UI control | Integration mode action | Read path | Acceptance test |
|----|------------|-------------------------|-----------|-----------------|
| AT-01 | Power on | `climate.set_hvac_mode` → `heat_cool` (or `power_on_mode`) on virtual climate | `climate.hvac_mode` | HA fixture: mode changes; physical writer not called in shadow |
| AT-02 | Power off | If Dry on: `switch.turn_off` dry → `climate.set_hvac_mode` `off` | climate + dry switch | Dry cleared then climate off |
| AT-03 | Heat knob | If `boost_active`: `boost_cancel` → `climate.set_temperature` low/high | `target_temp_*` | Min gap enforced; boost cleared |
| AT-04 | Cool knob | Same as AT-03 | same | same |
| AT-05 | Boost start | `boost_start` with `target.entity_id` = virtual climate; optional `duration_minutes: 30` | `boost_active`, `boost_remaining_seconds`; `target_temp_*` unchanged | D01 B1; reject if climate `off` (Kitchen parity) |
| AT-06 | Boost extend | `boost_start` again on same `entity_id` | expiry reset ~30m; setpoints still unchanged | D01 B2 |
| AT-07 | Boost cancel | `boost_cancel` with same `entity_id`; `data: {}` | `boost_active` false; setpoints unchanged | D01 B3 |
| AT-19 | Multi-room isolation | `boost_start` on climate **A** only | climate **B** `boost_active` remains false | Two config entries in one HA instance |
| AT-20 | Service validation | `boost_start` without target; wrong domain; non-integration climate | hard fail; no boost flags set on any entry | FR §10.18 |
| AT-08 | Boost countdown display | *(read)* `boost_remaining_seconds` | attribute | Matches timer semantics ±1s |
| AT-09 | Fan only on | If boost: `boost_cancel` → `climate.set_hvac_mode` `fan_only` | `operating_state` → `fan` | No `set_fan_mode` required for mode |
| AT-10 | Fan only off | `climate.set_hvac_mode` `heat_cool` (power_on_mode) | state leaves `fan` | |
| AT-11 | Fan Auto toggle | `climate.set_fan_mode` → `auto` (or off-auto → first manual speed) | `fan_mode` attribute | Virtual climate reflects auto |
| AT-12 | Fan speed select | `climate.set_fan_mode` → selected speed | `fan_mode` | Manual high ≠ satisfied by physical `auto` alone (actuator) |
| AT-13 | Dry “Switch mode” off | `switch.turn_off` on `dry_entity_id` | dry switch state | UI returns to thermostat |
| AT-14 | Dry on | *(not card button)* `switch.turn_on` dry or automation | `operating_state` `dry` | Physical `dry` when supported |
| AT-15 | Operating label | *(read)* `operating_state` or operating sensor | matches controller | Boost/Maintain/Idle/Off/Dry/Fan strings |
| AT-16 | Control temp display | climate attr or control sensor | numeric | Matches FR-02 averaging |
| AT-17 | Humidity display | humidity sensor | optional % | |
| AT-18 | Fan locked during Boost | UI readOnly | fan controls ignored | Matches legacy `readOnly: boostActive` |

**Test layers:** M4 — HA Python tests for AT-01–AT-07, AT-09–AT-12, **AT-19–AT-20** (headless). M5 — Vitest card tests + HA e2e for AT-01–AT-20.

### 7.4 Legacy mode (YAML package, unchanged)

When `integrated_split_system` is absent, the card keeps calling `script.turn_on`, `input_boolean.*`, `input_select.*`, and legacy `switch.*` per `src/services.ts`. No regression tests required in this repo beyond documenting the fork.

### 7.5 Milestone gating

| Milestone | Card |
|-----------|------|
| M1–M4 | Not required; backend-only |
| **M5** | **Required** — integration mode + AT-* |
| M6+ | Production migration **blocked** until M5 merged/released |

## 8. Architectural risks

| Risk | Impact | Mitigation (design) |
|------|--------|---------------------|
| Boost semantics (card arc ±2°C vs backend ±1°C / 28/18) | UX confusion | Documented in D01; optional M5 card arc tweak |
| Card/API mismatch | Broken dashboard after cutover | M5 mandatory; no helper shims |
| Ack vs external conflict | False positives / storms | D04 phase model + Kitchen throttle constants |
| Unverified Sensibo capabilities per room | Fan Only / Dry / fan speeds fail at runtime | Capability probe at setup; gate features; repair issues |
| External automations writing same physical entity | Beeping, oscillation, safety | Best-effort conflict detection; operator inventory; shadow mode |
| Restart mid Boost / mid min-cycle | Duplicate or missing physical commands | Persist deadlines/timestamps; resume deferred actions like reference |
| Legacy vs integration mode fork | Dual code paths in card | Feature flag `integrated_split_system`; legacy path frozen |
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
| M4 | Headless mode parity (entities + services; no card) |
| M5 | Card integration mode + AT-* tests (**blocks M6**) |
| M6–M7 | Pilot and rollout (**after M5**) |

## 10. M0 exit criteria

- [x] PRD reviewed against two-state-thermostat reference
- [x] Architecture + decisions (incl. Boost golden examples, card contract §7, D04 ack policy)
- [x] GPT-6 Boost + D04 ack policy (PR #1)
- [x] Native API contract; **no** helper-domain shims; M5 before M6 (this revision)
- [ ] User + GPT-6 approval before M1 code

**No Python under `custom_components/` until the review gate passes.**
