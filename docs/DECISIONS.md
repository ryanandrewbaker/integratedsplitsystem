# Design decisions — Integrated Split System (M0)

**Status:** Proposed resolutions for review. Not approved for implementation until the M0 PR is accepted.  
**Date:** 24 October 2026

Decisions D01–D10 correspond to PRD §11. Each entry lists the question, **proposed resolution**, evidence, and **residual risk / owner action**.

---

## Summary table

| ID | Topic | Proposed resolution (M0) | Gate to finalize |
|----|--------|---------------------------|------------------|
| D01 | Boost semantics | Three-layer model: card ±2°C user semantics; reference band narrowing + hysteresis for control; physical mapping configurable with **migration default = reference actuator** | User approves table below |
| D02 | Physical hvac/fan modes | Probe at setup from underlying entity; hide/disable unsupported features | Live HA export before M4/M6 |
| D03 | Unverified rooms | No config presets; entries only via UI after operator inventory | Export before each room migration |
| D04 | External physical writes | Observe, warn, pause reconciliation; no infinite fight | M3 actuator design |
| D05 | Card source repo | Keep canonical source in `two-state-thermostat` until M5 | M5 packaging |
| D06 | Auto frontend resource | Attempt in M5; document manual fallback | M5 install tests |
| D07 | HA/Python minimum | Choose in M1 from operator HA version + CI matrix | M1 |
| D08 | Room-specific thresholds | Per-room options + baseline capture before cutover | Each M6 room |
| D09 | Restart policy | Read-only reconcile first; no blind physical overwrite; restore Boost if timer valid | M2/M3 |
| D10 | Fan without compressor | Use native `fan`/`fan_only` when advertised; exempt from compressor min-cycle per reference | Per-entity capability check M2/M4 |

---

## D01 — Boost semantics (card vs controller vs physical)

**Conflict:** Card README documents a **±2°C** shift on the active heating/cooling target, 30-minute timer, snapshot restore, and High fan lock. Reference TypeScript also narrows control bands by **±1°C** when `manualBoost` is true (`baseLow + 1` / `baseHigh - 1`). Reference actuator commands **fixed** physical targets in boost: **28°C heat**, **18°C cool**, while maintain uses `low + 1` / `high - 1` clamped.

**Proposed resolution:**

1. **User-visible Boost (card parity):** Implement exactly as card README §Boost: ±2°C on the active direction’s setpoint for display and virtual target bookkeeping; 30-minute timer; snapshot of heat/cool targets + fan auto/manual + manual fan selection; extend restarts timer without compounding; cancel/expiry/setpoint change restores snapshot; High fan forced while Boost active.
2. **Control demand (state machine):** Port `computeKitchenClimateController` hysteresis and band logic, including `manualBoost` band adjustment and transition thresholds (1.0°C / 1.5°C), as the default controller profile named `kitchen_reference`.
3. **Physical mapping (actuator):** Default profile `kitchen_reference` uses `computePhysicalIntent` rules (boost → 28/18, maintain → offset targets). Add options flow key `physical_boost_strategy`: `reference_fixed` (default for migration) | `virtual_offset` (map from virtual boosted setpoints) for future tuning without card changes.

**Approval needed:** Confirm migration default `reference_fixed` for Kitchen/Family Room pilot.

### Boost behavior layers (reference vs intended)

| Layer | Documented / card intended | Reference TS/YAML observed | Integration intended (if approved) |
|-------|---------------------------|----------------------------|-----------------------------------|
| Timer duration | 30 minutes | 30 minutes (YAML timer) | 30 minutes configurable default |
| Extend Boost | Restart timer; keep snapshot; no compound offset | Same (package scripts) | Same |
| Cancel Boost | Restore snapshot | Same | Same |
| Setpoint change while Boost | Cancels Boost | Package behavior | Same |
| Active arc visual | ±2°C past live setpoint | Card UI | Card unchanged |
| Virtual target shift | ±2°C active direction | Band narrowing ±1°C in state machine only | Both: card shift for entity targets; state machine uses reference bands |
| Physical boost heat target | Not specified in card | 28°C when `controllerState === boost` | Default `reference_fixed` → 28°C |
| Physical boost cool target | Not specified in card | 18°C when boost cool | Default `reference_fixed` → 18°C |
| Physical maintain targets | Not user-visible | `min(low+1,30)` / `max(high-1,10)` | Same under default profile |
| Fan during Boost | High; lock auto/speed on card | High + `applyAutomaticFanStage` | High; match card lock semantics |

---

## D02 — Physical `hvac_modes` / `fan_modes` unverified

**Proposed resolution:** At config entry setup and on underlying entity capability changes, read `hvac_modes`, `fan_modes`, and supported features from the physical entity. Cache on coordinator. If `dry`, `fan`, or `fan_only` is absent, set feature flags off on virtual entity and raise repair issue “mode not supported by device.” Do not send unsupported service calls.

**Owner action:** Run `export-climate-audit.sh` (card repo) per room before M4 and M6.

---

## D03 — Olivia, Alice, main bedroom entity IDs unknown

**Proposed resolution:** No bundled room templates in integration. Config flow only allows user-selected entities. Document blocked status from card repo `rooms/olivia.json`, `alice.json`, `main_bedroom.json` (`audit_status: blocked`). Migration checklist requires registry export before creating entries.

---

## D04 — External physical change vs controller intent

**Proposed resolution:** **Warn and pause**, do not auto-retaliate indefinitely.

- On unexpected physical state change while converged: increment mismatch counter, set controller flag `external_divergence`, surface repair/warning with last known intent vs observed state.
- Reconciliation pauses until user clears issue, underlying entity returns to expected state, or user explicitly resumes (options or service).
- Do not implement “always reclaim immediately” as default (avoids beeping wars; aligns with PRD FR-07 and Kitchen competing-control incident).

Alternative `aggressive_reclaim` deferred; not recommended for v1.

---

## D05 — Canonical Lit card source repository

**Proposed resolution:** Keep **canonical frontend source** in `ryanandrewbaker/two-state-thermostat` through M4. This repo ships **integration only** until M5. M5 may vendor a **pinned release artifact** (`two-state-thermostat.js`) under `custom_components/integrated_split_system/frontend/` after install tests. No silent fork of card TypeScript into this repo before approval.

---

## D06 — Automatic Lovelace resource registration

**Proposed resolution:** Treat as **unproven** at M0. M5 deliverable: spike using supported `frontend` APIs for the target HA minimum version. Acceptance: fresh HACS install registers resource OR documented one-line manual step with detection of duplicate resources. Failure mode: integration installs without bundling card; user keeps existing HACS Dashboard card.

---

## D07 — Minimum Home Assistant and Python versions

**Proposed resolution:** Defer numeric pin to **M1**. M1 PR must record operator’s installed HA version, run CI against that version and latest stable, and set `manifest.json` `requirements` / `homeassistant` key accordingly. M0 assumption: Config Entry flows, `ClimateEntity` range targets, config entry diagnostics, and `runtime_data` are required.

---

## D08 — Room-specific temperature sources and thresholds

**Proposed resolution:** All per-room variation lives in **config entry data/options**, not code forks. Migration imports Kitchen/Family Room sources from repo audit as **examples only** (not auto-created). Before each room cutover, capture baseline: control temperature formula, targets, boost state, disabled competing automations.

Known examples (repo-confirmed, live unverified):

| Room | Physical (repo) | Control temperature sources (repo) |
|------|-----------------|--------------------------------------|
| Kitchen | `climate.kitchen_ac` | `sensor.livingroom_soil_temperature` + `sensor.kitchen_temperature_feels_like` (equal average) |
| Family Room | `climate.family_room_ac` | `sensor.familyroom_temperature_couch_temperature` + `climate.family_room_ac.current_temperature` (equal average) |
| Olivia / Alice / Main bedroom | Unknown | Unknown — blocked |

---

## D09 — Restart and failure policy

**Proposed resolution:**

1. **On HA start / entry load:** Read physical state; read persisted Boost deadline and snapshot; read compressor/min-cycle timestamps from store.
2. **First evaluation cycle:** Read-only reconcile — compute desired intent but do not write unless user intent or safety policy requires (e.g. explicit “resume control” after valid Boost restore).
3. **Boost after restart:** Restore only if deadline not expired and temperature sources valid; else exit Boost safely and log outcome.
4. **Min-cycle:** Restore deferred hold duration from timestamps like reference `minCycleHoldSecondsFromTimestamps`.
5. **Never** blindly push 28/18 or user targets on startup solely because virtual entity persisted state differs from physical.

Shadow mode skips step 2 writes entirely.

---

## D10 — Fan circulation without compressor

**Proposed resolution:** Fan Only uses virtual `HVACMode.FAN_ONLY`. Physical mapping uses `resolvePhysicalFanHvacMode` order: `fan`, then `fan_only`. If neither advertised, Fan Only is **unsupported** (repair issue). Min-cycle deferral for start/stop applies to heat/cool; fan/dry paths follow reference exemptions (no deferral when engaging fan-only from off if reference allows). **Per-room proof** required in M2/M4 with live entity state.

---

## Legacy YAML vs intended integration behavior

This table contrasts **observed reference behavior** (card repo TypeScript + docs; Kitchen YAML intended to match) with **intended integration behavior** after approval. Live production YAML version may drift until operator confirms package version ≥ reference actuator v0.6.5+.

| Concern | Legacy YAML / reference observed | Intended integration behavior |
|---------|-----------------------------------|------------------------------|
| Installation | Copy package YAML; many helpers | HACS integration + UI config flow |
| Virtual climate | Dual Smart Thermostat + templates | Native `ClimateEntity` (`heat_cool` + range) |
| Control temperature | Template sensors, equal average | Python subscriptions, equal average default |
| Min heat/cool gap | Enforced in package + card | Enforced in `ClimateEntity` set_temperature handlers |
| Operating state | `sensor.*_auto_operating_state` | Attribute and/or diagnostic entity on virtual climate |
| Boost | Scripts, timer, input_boolean | Internal state + persisted snapshot/deadline |
| Dry | `switch.*_dry_mode` + script | Internal Dry flag; physical `dry` when supported |
| Fan Only | Virtual climate `fan_only` | Same; gated physical fan mode |
| Fan manual/auto | Helpers + `mapSelectedFanToSensibo` | Options + same mapping table in Python |
| Physical commands | `script.*_actuator_apply` automation | Serialized actuator service calls |
| Intent coalescing | `input_number.*_actuator_intent` + restart mode | Single asyncio owner / intent generation counter |
| Min cycle 300s | Timer + deferred action select | Persisted timestamps + scheduled reconcile |
| User off | Bypass deferred shutdown | Same bypass rule |
| Competing writers | Operator disabled Kitchen legacy automation | Detection + warning; operator must disable extras |
| Card integration | Many entity attributes on virtual climate | Phase 1: compatible attributes; Phase 2: slim surface |
| Diagnostics | Debug log prefix, command counter helpers | Native diagnostics + optional entities |
| Shadow / migration | Manual comparison | Built-in shadow mode on config entry |
| Multi-room | Separate YAML per room | Multiple config entries, shared code |
| Sensibo credentials | Via existing integration | Unchanged; no new tokens |

---

## Open questions for reviewers (M0)

1. Approve **D01** migration default `physical_boost_strategy = reference_fixed` (28/18 boost targets)?
2. Approve **D04** “warn and pause” as the only default for external divergence?
3. Freeze HA domain **`integrated_split_system`** before any config entry is created in the wild (see `docs/NAMING.md`)?

---

## Decision log

| Date | ID | Outcome |
|------|-----|---------|
| 2026-10-24 | D01–D10 | Proposed in M0 PR — pending user / GPT-6 approval |
