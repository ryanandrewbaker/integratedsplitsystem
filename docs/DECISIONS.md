# Design decisions — Integrated Split System (M0)

**Status:** Revised per GPT-6 review on PR #1 (24 Oct 2026). Pending re-review.  
**Behavioural reference:** `ryanandrewbaker/two-state-thermostat` — `homeassistant/packages/kitchen_auto_climate.yaml`, `homeassistant/lib/kitchen-climate-*.ts`, `src/services.ts`, `src/state.ts`, `src/constants.ts`.

Decisions D01–D10 correspond to PRD §11.

---

## Summary table

| ID | Topic | Proposed resolution (M0) | Gate to finalize |
|----|--------|---------------------------|------------------|
| D01 | Boost semantics | **Single canonical backend model** = Kitchen package + TS (no ±2°C virtual setpoint shift); card ±2°C arc is display-only | User approves golden examples |
| D02 | Physical hvac/fan modes | Probe at setup from underlying entity; hide/disable unsupported features | Live HA export before M4/M6 |
| D03 | Unverified rooms | No config presets; entries only via UI after operator inventory | Export before each room migration |
| D04 | External physical writes | **pending_ack** vs **external_conflict_paused** (see §D04); bounded reconcile from Kitchen YAML | M3 actuator tests |
| D05 | Card source repo | Keep canonical source in `two-state-thermostat` until M5 | M5 packaging |
| D06 | Auto frontend resource | Attempt in M5; document manual fallback | M5 install tests |
| D07 | HA/Python minimum | Choose in M1 from operator HA version + CI matrix | M1 |
| D08 | Room-specific thresholds | Per-room options + baseline capture before cutover | Each M6 room |
| D09 | Restart policy | Read-only reconcile first; no blind physical overwrite; restore Boost if timer valid | M2/M3 |
| D10 | Fan without compressor | Use native `fan`/`fan_only` when advertised; exempt from compressor min-cycle per reference | Per-entity capability check M2/M4 |

---

## D01 — Boost semantics (canonical v1 model)

**GPT-6 blocker addressed:** Do not stack card ±2°C virtual setpoint changes on top of Kitchen ±1°C control bands and 28/18 physical boost targets.

### What the reference system actually does

| Layer | Observed behaviour (Kitchen package + card TS) | Source |
|-------|--------------------------------------------------|--------|
| Boost start script | If virtual climate not `off`: `input_boolean.kitchen_climate_boost` **on** + `timer.kitchen_climate_boost` **30:00** | `script.kitchen_climate_boost` |
| Virtual heat/cool targets | **Unchanged** on `climate.kitchen_auto_climate` during Boost | Package + card `set_temperature` only on user dial edits |
| Manual boost flag | Drives `manual_boost` in controller + actuator (`input_boolean.kitchen_climate_boost`) | Actuator variables |
| Control band adjustment | When `manual_boost` and direction **heat**: effective low = `base_low + 1.0`; when **cool**: effective high = `base_high - 1.0` | YAML templates, `computeKitchenClimateController` |
| Effective target sensors | Same ±1°C on active direction for display helpers | `sensor.kitchen_effective_*_target` templates |
| Physical boost targets | When `controller_state == boost`: heat → **28°C**, cool → **18°C** | `computePhysicalIntent`, `kitchen_actuator_apply` |
| Physical maintain targets | heat → `min(low + 1, 30)`, cool → `max(high - 1, 10)` with boosted `low`/`high` | Same |
| Cancel / expiry | `kitchen_climate_cancel_boost` and boost lifecycle: timer cancel + boolean **off** — **no** separate snapshot helpers in Kitchen YAML | Scripts + `kitchen_auto_climate_boost_lifecycle` |
| Card dial arc | **±2°C** overlay only (`DEFAULT_BOOST_TEMPERATURE_OFFSET = 2` in `getBoostArcOverlay`) | `src/constants.ts`, `src/state.ts` — **does not** change climate attributes |
| Card README “±2°C / snapshot” | Documents UX intent; Kitchen YAML does **not** shift virtual setpoints ±2°C or restore a multi-field snapshot on cancel | Treat README as **card UX spec**; backend parity = package |

**Canonical v1 integration model (proposed):** Port the **Kitchen backend** exactly: boolean + timer, ±1°C band narrowing when manual boost active, state machine + 28/18 physical boost, high fan staging while manual boost and boost/maintain. Do **not** mutate virtual `target_temp_low`/`target_temp_high` when Boost starts.

**Intentional non-parity (documented):** Card boost arc uses **2°C**; backend effective targets use **1°C**. Keeping the unchanged card is acceptable for M4; aligning arc to 1°C is an optional **M5 card** change, not an integration change.

### Golden Boost examples (Kitchen reference, targets 20.0 / 24.5 °C heat/cool)

Assumptions: climate on `heat_cool`, direction **heat**, control temp drives controller state, fan automatic unless noted.

| ID | Scenario | User action | Virtual targets | `manual_boost` | Band used (heat) | Controller → physical (when applicable) |
|----|----------|-------------|-----------------|----------------|------------------|----------------------------------------|
| B1 | Start Boost (idle/maintain) | Card → `script.turn_on` boost | 20.0 / 24.5 unchanged | on, timer 30m | low **21.0** (20+1) | If state → `boost`: physical heat **28°C** + high fan |
| B2 | Extend Boost | Card → boost again (timer restart) | unchanged | stays on, timer reset | unchanged | No compounding: boolean was already on; timer only restarts |
| B3 | Cancel Boost | Card → cancel script | unchanged | off, timer cancelled | low **20.0** | Reconcile toward maintain/idle intent; no “undo math” on targets |
| B4 | Timer expiry | Timer finished → lifecycle | unchanged | off | back to base | Same as B3 |
| B5 | Setpoint edit while Boost | Card → `cancelBoost` then `climate.set_temperature` | user new values | off after cancel | per new targets | Card already cancels Boost first (`two-state-thermostat.ts`) |
| B6 | Boost while cooling | Boost on, direction **cool** | unchanged | on | high **23.5** (24.5−1) | If `boost` cool: physical **18°C** |
| B7 | HA restart | Timer `restore: true` | unchanged | lifecycle clears boolean if timer not active | — | On startup: do not force physical 28/18 until controller evaluates (see D09) |

**User approval:** Confirm canonical v1 = Kitchen backend (not card README ±2°C virtual shift).

---

## D02 — Physical `hvac_modes` / `fan_modes` unverified

**Proposed resolution:** At config entry setup and on underlying entity capability changes, read `hvac_modes`, `fan_modes`, and supported features from the physical entity. Cache on coordinator. If `dry`, `fan`, or `fan_only` is absent, set feature flags off on virtual entity and raise repair issue “mode not supported by device.” Do not send unsupported service calls.

**Owner action:** Run `export-climate-audit.sh` (card repo) per room before M4 and M6.

---

## D03 — Olivia, Alice, main bedroom entity IDs unknown

**Proposed resolution:** No bundled room templates in integration. Config flow only allows user-selected entities. Document blocked status from card repo `rooms/olivia.json`, `alice.json`, `main_bedroom.json` (`audit_status: blocked`). Migration checklist requires registry export before creating entries.

---

## D04 — Physical acknowledgement delay vs external conflict

**GPT-6 blocker addressed:** Slow Sensibo updates are not competing writers. Policy must separate **pending acknowledgement** from **external conflict**.

### Reference behaviour (Kitchen actuator)

- Each apply run compares desired vs actual mode, target (±0.1°C), and fan (`evaluateFanConfirmation` / YAML equivalent). If not converged, issues minimal `climate.*` calls once per run.
- `input_number.kitchen_actuator_intent` increments; stale script runs exit when `run_intent != current intent`.
- Mismatch automations re-trigger apply after **60s** (active heat/cool) or **90s** (idle/fan/dry expected off) sustained divergence.
- Reconcile path **throttles** if `kitchen_ac_last_apply` was **&lt; 25s** ago (`stop=reconcile_throttled` — physical may still be converging).

### Integration actuator phases (proposed)

| Phase | Meaning | Physical writes | User-visible |
|-------|---------|-----------------|--------------|
| `converged` | Desired matches reported within tolerance | None | Normal |
| `pending_ack` | We issued a command; waiting for physical state | None additional until grace elapses | Optional “syncing” diagnostic |
| `reconciling` | Not converged after grace; bounded apply retries | At most one apply burst per throttle window | Diagnostics show attempt count |
| `unconfirmed` | Fan/target still wrong after max attempts per intent | **Stop** retrying this intent | Repair: fan not confirmed |
| `external_conflict_paused` | Sustained mismatch **not** explained by our last command + grace; pattern consistent with second writer or manual AC UI | **Paused** until cleared | Repair issue + log |

### Rules

1. **ACK grace window:** After any physical service call, enter `pending_ack` for **`ACK_GRACE_SECONDS = 25`** (match Kitchen reconcile throttle). Physical changes in this window **do not** set external conflict.
2. **Convergence tolerance:** Mode match rules + **0.1°C** target + fan rules from `kitchen-climate-yaml-templates.ts` (manual high ≠ satisfied by `auto` alone).
3. **Bounded reconcile:** While not converged and not paused, retry at most **`MAX_RECONCILE_BURST = 3`** apply cycles per mismatch episode, respecting 25s throttle (extends Kitchen counter `kitchen_ac_reconcile_attempts` concept).
4. **External conflict detection:** If mismatch persists **> 60s** (active) or **> 90s** (idle path) **and** grace/reconcile bursts exhausted **and** observed physical state does not match last **integration-issued** command fingerprint → `external_conflict_paused`. Do not issue further physical commands (prevents Kitchen-style beeping wars).
5. **Legitimate manual override:** User changes AC from Sensibo app/remote → treated as external conflict once sustained; virtual climate and card keep showing **requested** state; diagnostics show observed vs requested.
6. **While paused:** Virtual controller continues to compute demand for UI; **no** physical heat/cool/fan/dry commands until user **Resume control** (options/service) after resolving competing automation or accepting observed state.
7. **Competing HA writer:** Same as manual override; operator must disable extra automations (`COMPETING_CONTROLS.md`).

**M3 tests:** delayed ack within 25s → no conflict; slow ack → bounded reconcile then `unconfirmed`; injected parallel `climate.set_*` → `external_conflict_paused` without unbounded calls.

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
| Boost | Boolean + timer; no virtual target shift; ±1°C bands; 28/18 physical boost | Same; optional timer restore like Kitchen |
| Dry | `switch.*_dry_mode` + script | Internal Dry flag; physical `dry` when supported |
| Fan Only | Virtual climate `fan_only` | Same; gated physical fan mode |
| Fan manual/auto | Helpers + `mapSelectedFanToSensibo` | Options + same mapping table in Python |
| Physical commands | `script.*_actuator_apply` automation | Serialized actuator service calls |
| Intent coalescing | `input_number.*_actuator_intent` + restart mode | Single asyncio owner / intent generation counter |
| Min cycle 300s | Timer + deferred action select | Persisted timestamps + scheduled reconcile |
| User off | Bypass deferred shutdown | Same bypass rule |
| Competing writers | Operator disabled Kitchen legacy automation | Detection + warning; operator must disable extras |
| Card integration | Card calls climate + helpers (see ARCHITECTURE §7) | Phase 1: **companion shims** + attributes; Phase 2 (M5): native card services |
| Diagnostics | Debug log prefix, command counter helpers | Native diagnostics + optional entities |
| Shadow / migration | Manual comparison | Built-in shadow mode on config entry |
| Multi-room | Separate YAML per room | Multiple config entries, shared code |
| Sensibo credentials | Via existing integration | Unchanged; no new tokens |

---

## Card compatibility decision (M0, addresses GPT-6 blocker #2)

**Problem:** `custom:two-state-thermostat` calls helper domains (`src/services.ts`, `ALLOWED_SERVICE_DOMAINS`). Attributes alone are insufficient.

**Proposed transition:**

| Phase | Card | Integration |
|-------|------|-------------|
| M1–M4 | **Unchanged** (`two-state-thermostat` repo) | Exposes native `ClimateEntity` **plus** companion entities/services matching attribute IDs (`boost_script_entity`, `fan_auto_entity`, …) |
| M5+ | Optional: detect `integrated_split_system` and call integration services | May slim shims after card update |

Full per-control contract: **ARCHITECTURE.md §7**. Card parity is **not claimed** until M4/M5 acceptance tests pass.

---

## Open questions for reviewers (M0 re-review)

1. Approve **D01** canonical backend (= Kitchen package, no ±2°C virtual shift)?
2. Approve **D04** phase model and constants (25s ACK grace, bounded reconcile, external pause)?
3. Approve **companion shim** strategy for unchanged card through M4?
4. Freeze HA domain **`integrated_split_system`** (see `docs/NAMING.md`)?

---

## Decision log

| Date | ID | Outcome |
|------|-----|---------|
| 2026-10-24 | D01–D10 | Initial M0 proposal |
| 2026-10-24 | D01, D04, card contract | Revised per GPT-6 PR #1 review — pending re-review |
