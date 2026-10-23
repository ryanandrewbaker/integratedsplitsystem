# Integrated Split System — architecture (M0)

**Status:** Design draft for review gate M0. No runtime code in this repository yet.  
**Domain (proposed):** `integrated_split_system`  
**Reference implementation:** [two-state-thermostat](https://github.com/ryanandrewbaker/two-state-thermostat) (Lit card + YAML/TypeScript controller reference)

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
| Card | Discovers helpers via climate attributes (`two_state_thermostat`, `boost_*`, etc.) | Phase 1: emit compatible attributes; Phase 2 (M5): reduce helper surface |

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

### 4.5 Card compatibility layer

Until M5, the virtual climate entity should expose the attribute contract documented in the card README (`two_state_thermostat`, `operating_state_entity` or embedded operating state, boost entities/scripts replaced by native behavior where possible).

**Target end state (M5+):** Card uses primarily native climate state/attributes; legacy helper entity IDs become optional.

## 5. Behavior that must be preserved

Derived from card README, package docs, and reference TypeScript (production YAML is authoritative for Kitchen once live version confirmed).

### 5.1 User-facing (card contract)

- Dual heat/cool range with **minimum** separation (default 2°C); wider bands unchanged; opposite target moves only when needed to satisfy minimum gap.
- Operating state feedback: Off, Idle, Boost/Maintain heating/cooling.
- Boost: 30-minute default; extend restarts timer without compounding snapshot; cancel restores snapshot; setpoint change cancels Boost; high fan while Boost active; fan controls locked during Boost.
- Dry: separate manual cycle; suspends normal heat/cool UI semantics; humidity informational.
- Fan Only: virtual `fan_only`; does not use `climate.set_fan_mode` from card; cancels Boost when entering fan only.
- Power off intent preserved across restarts (no silent re-enable).

### 5.2 Control / actuator (reference implementation)

- Equal-average control temperature for Kitchen and Family Room source lists (repo-confirmed).
- Controller state machine hysteresis and fan staging rules as in `computeKitchenClimateController`.
- Physical mapping for maintain/boost states as in `computePhysicalIntent` (including fixed 28°C / 18°C boost targets in reference actuator — **see D01 for canonical vs physical policy**).
- Sensibo fan mapping preference order (`mapSelectedFanToSensibo`).
- Manual fan confirmation: do not treat `auto` as satisfying manual high (reference `evaluateFanConfirmation`).
- Min-cycle deferral with timer-based reconcile after HA restart (`minCycleHoldSecondsFromTimestamps` pattern).
- Competing writer awareness: warn / pause; never infinite retaliation.

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

## 7. Architectural risks

| Risk | Impact | Mitigation (design) |
|------|--------|---------------------|
| Boost semantics split (card ±2°C vs actuator 28/18) | User surprise, migration mismatch | Behavior table + explicit policy in DECISIONS D01; tests with golden tables |
| Unverified Sensibo capabilities per room | Fan Only / Dry / fan speeds fail at runtime | Capability probe at setup; gate features; repair issues |
| External automations writing same physical entity | Beeping, oscillation, safety | Best-effort conflict detection; operator inventory; shadow mode |
| Restart mid Boost / mid min-cycle | Duplicate or missing physical commands | Persist deadlines/timestamps; resume deferred actions like reference |
| Card still expects YAML helpers | Broken UX if attributes missing | Compatibility attribute phase; M5 feature detection in card |
| Dual HACS packages loading two card JS copies | Frontend conflicts | M5 install tests; keep card repo separate until pinned bundle proven |
| Olivia / Alice / main bedroom unknown | Wrong entity binding | Block config templates; require export before entries |
| Over-eager reconciliation | Command storms | Zero-chatter acceptance test (PRD §10) |
| HA API drift | Break on upgrade | Pin minimum version in M1; CI against HA version matrix |

## 8. Milestone map (implementation after M0 approval)

| Milestone | Delivers |
|-----------|----------|
| M1 | Skeleton: manifest, flows, entity registration, no physical writes |
| M2 | Read-only controller + temperature + shadow mode |
| M3 | Actuator safety layer |
| M4 | Full mode parity (Fan Only, Boost, Dry, persistence) |
| M5 | Card packaging / resource registration |
| M6–M7 | Pilot and additional rooms with human approval |

## 9. M0 exit criteria

- [x] PRD reviewed against two-state-thermostat reference
- [x] This architecture document
- [x] `DECISIONS.md` with D01–D10 proposals and legacy vs intended behavior table
- [ ] User + GPT-6 approval before M1 code

**No Python under `custom_components/` until the review gate passes.**
