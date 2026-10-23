# Design decisions — Integrated Split System (M0)

**Status:** Revised per GPT-6 PR #1 re-review (native API; no helper shims). Pending approval.  
**Behavioural reference:** `ryanandrewbaker/two-state-thermostat` — Kitchen YAML/TS for **control semantics**; **API shape** is integration-native (§ARCHITECTURE.md §7).

Decisions D01–D10 correspond to PRD §11. **D11** records the card/API resolution from the second GPT-6 review.

---

## Summary table

| ID | Topic | Proposed resolution (M0) | Gate to finalize |
|----|--------|---------------------------|------------------|
| D01 | Boost semantics | Kitchen backend model (no virtual ±2°C shift) | User approves golden examples |
| D02 | Capabilities + equipment profiles | Entity attrs + optional read-only Sensibo discovery; user-defined reusable profiles | M1–M2 EP-* tests; live export before M6 |
| D03 | Unverified rooms | No presets; UI-only config after inventory | Export before each room |
| D04 | Ack / failure / conflict | `pending_ack` → `unconfirmed_device` vs `external_conflict_paused`; safe `resume_control` | M3 actuator tests |
| D05 | Card source repo | Canonical TS in `two-state-thermostat`; **M5 integration mode** required before M6 | M5 release |
| D06 | Auto frontend resource | M5 spike + fallback manual resource step | M5 install tests |
| D07 | HA/Python minimum | Pin in M1 from operator + CI | M1 |
| D08 | Room-specific thresholds | Per entry options + baseline before cutover | Each M6 room |
| D09 | Restart policy | Read-only reconcile first; no blind physical overwrite | M2/M3 |
| D10 | Fan without compressor | Native `fan`/`fan_only` when advertised | M2/M4 per entity |
| D11 | Card API (no shims) | Native climate + integration services/entities; legacy card path unchanged | M0 doc approval |

---

## D01 — Boost semantics (canonical v1 model)

Kitchen boolean + 30m timer semantics, ±1°C bands, 28/18 physical boost, card ±2°C arc display-only. **Virtual setpoints are never mutated** for Boost start/extend/cancel/expiry.

### Persisted state (FR-05 / FR-08 — single contract)

| State | Persist? | Notes |
|-------|----------|-------|
| `boost_active` | Yes (`Store`) | Cleared on cancel/expiry |
| `boost_expires_at` | Yes | Absolute **UTC wall-clock** end time (not a monotonic timestamp); compare with `now()` after restart |
| `target_temp_low` / `target_temp_high` | On `ClimateEntity` only | **Not** copied to a boost snapshot |
| User fan preference (`fan_mode`, auto vs manual) | On `ClimateEntity` | High fan while boost is **staging**, not a separate saved snapshot |
| Pre-boost setpoint “restore” on cancel | **No** | Cancel clears boost flags; reconcile from current entity state |

Legacy card README “snapshot” describes YAML-era UX; Kitchen `kitchen_climate_cancel_boost` only clears boolean + timer — it does **not** write virtual setpoints back.

**M5 services:** `boost_start` / `boost_cancel` with required `target.entity_id` on the virtual climate — §ARCHITECTURE.md §7.2.

Golden table **B1–B7** (authoritative):

| ID | Scenario | User action (integration mode) | Virtual targets | Boost internal | Band (heat example) | Physical when `boost` |
|----|----------|-------------------------------|-----------------|----------------|---------------------|------------------------|
| B1 | Start Boost | `boost_start` | 20.0 / 24.5 unchanged | active, 30m | low **21.0** | heat **28°C** |
| B2 | Extend | `boost_start` again | unchanged | timer reset | unchanged | no compounding |
| B3 | Cancel | `boost_cancel` | unchanged | off | low **20.0** | reconcile |
| B4 | Expiry | internal timer | unchanged | off | base | reconcile |
| B5 | Setpoint edit | `boost_cancel` + `climate.set_temperature` | user values | off | per targets | card order preserved |
| B6 | Cool boost | `boost_start` | unchanged | active | high **23.5** | cool **18°C** |
| B7 | HA restart | — | unchanged | restore if timer valid (D09) | — | no blind 28/18 push |

---

## D02 — Capabilities, Sensibo controller type, and connected AC profiles

**Problem:** Each room has a Sensibo controller (**Air** or **Sky**) and a **connected split type** that may be shared across rooms. Capability varies by **device + mode**, not by profile name alone.

### Controller type (`sensibo_controller_type`)

- Values: `air` | `sky` | `unknown`.
- **Auto-detect** from Sensibo device/registry attributes when the physical entity is Sensibo-backed; operator may override in options (informational/diagnostics).
- Controller type **does not** by itself enable modes or fan speeds — it is not a substitute for capability discovery.

### Connected AC profile (`connected_ac_profile`)

Lightweight, **user-defined**, **reusable** records stored by the integration (e.g. in a `Store`), **not** a manufacturer catalogue and **not** three household-specific HACS presets.

| Profile field (examples) | Purpose |
|--------------------------|---------|
| `profile_id` / display name | Stable reference from multiple config entries |
| Optional `label` | Operator text (“Mitsubishi kids rooms”, “Daikin upstairs”) |
| Fan preference hints | e.g. map UI “high” → `strong` when capabilities allow |
| Swing preference hints | vertical / horizontal values **only if** later supported by actuator |
| Notes | Free text |

**Household planning examples (unverified, operator-created after install):**

| Profile (example name) | Rooms (intent) | Notes |
|------------------------|----------------|-------|
| `kitchen` (dedicated) | Kitchen | Independent equipment |
| `upstairs` (shared) | Family Room, main bedroom | Shared connected AC type when verified |
| `mitsubishi-kids` (shared) | Olivia, Alice | Historical YAML cited `strong` fan, swing `rangefull` / `fixedleftright` — **not** live proof |

Multiple config entries may reference the same `profile_id`. Each entry still has its **own** physical binding, virtual climate, boost state, and actuator — profile only shares **preference hints**.

### Capability discovery (what actually permits a command)

1. **Always (any `climate` source):** read `hvac_modes`, `fan_modes`, `supported_features`, temperature limits from the physical entity state/attributes.
2. **When physical entity is Sensibo and action is available:** optional **read-only** call to [`sensibo.get_device_capabilities`](https://www.home-assistant.io/integrations/sensibo/) per HVAC mode to obtain permitted fan speeds, swing modes, horizontal swing, and target temperatures (values are **case-sensitive**).
3. **Merge rule:** effective permitted set = intersection of entity attributes and per-mode Sensibo capabilities when present; otherwise entity attributes only.
4. **Profile rule:** a profile preference may **suggest** a mapping (e.g. prefer `strong` over `high`) but **never** enables a value absent from the permitted set. Unsupported → repair/diagnostic, **zero physical writes** for that intent.

### Swing and airflow

- Any future swing/airflow command goes through the **single serialized actuator** (FR-07), with the same ack/conflict policy (D04).
- **No swing write commands in M1/M2.** Design and validate read-only discovery and gating first.

### M1/M2 fixture criteria (EP-*)

| ID | Scenario |
|----|----------|
| EP-01 | Entry A: Sensibo Air + profile P; Entry B: Sensibo Sky + profile Q — types stored independently |
| EP-02 | Entries A and B share profile P; boost/setpoints on A do not change B |
| EP-03 | Profile prefers `strong` fan; capabilities for current mode include `strong` → mapping allowed |
| EP-04 | Profile prefers `strong`; capabilities omit `strong` → diagnostic, no physical `set_fan_mode` |
| EP-05 | Generic non-Sensibo climate — no `get_device_capabilities`; generic attrs only |
| EP-06 | Mock Sensibo capabilities differ per HVAC mode; validation refreshes on mode change |

Live entity IDs and deployed capabilities for all five rooms remain **unverified** until operator export.

---

## D03 — Olivia, Alice, main bedroom entity IDs unknown

No bundled room templates. Config flow only after operator registry export (`rooms/*.json` `audit_status: blocked`).

---

## D04 — Acknowledgement, unconfirmed device, and external conflict

### Reference (Kitchen)

Convergence checks, 25s reconcile throttle, 60s/90s mismatch triggers — see prior M0 text and `kitchen_auto_climate.yaml` actuator automation.

### Actuator phases (integration)

| Phase | Meaning | Physical writes | Diagnostic / repair |
|-------|---------|-----------------|---------------------|
| `converged` | Matches our fingerprint | None | — |
| `pending_ack` | Within **25s** after our command | None extra | `syncing` optional |
| `reconciling` | Post-grace bounded retries (max **3** bursts, 25s apart) | Minimal necessary | `reconcile_attempts` |
| `unconfirmed_device` | Retries exhausted; physical ≠ **our** last fingerprint | **Stopped** | Repair: slow/unsupported device — **not** external writer |
| `external_conflict_paused` | Sustained mismatch **incompatible** with our command history (manual AC, second automation) | **Stopped** | Repair: competing control |

### Distinguishing `unconfirmed_device` vs `external_conflict_paused`

| Signal | `unconfirmed_device` | `external_conflict_paused` |
|--------|----------------------|----------------------------|
| Typical cause | Sensibo lag, fan step unsupported, partial ack | Sensibo app edit, alien `climate.set_*` automation |
| Fingerprint | Physical state **near** expected (mode right, fan/temp wrong) or stuck after **our** command | Physical state **far** from any recent integration command or **oscillates** between two patterns |
| After max retries | Stop; show last **requested** vs **observed** | Stop; flag conflict; require operator action |
| GPT-6 note | Late ACK failure ≠ proof of second writer | Requires evidence inconsistent with our issued commands |

### `resume_control` (safe)

When operator clears `external_conflict_paused` or `unconfirmed_device` (where applicable):

1. Increment intent generation (supersede stale work).
2. Read **current** physical state and **current** user/virtual settings.
3. Compute **fresh** physical intent; do **not** replay queued or historical service call list.
4. Optional: first cycle read-only if D09 startup policy applies.

**M3 tests:** slow ack → `unconfirmed_device` not `external_conflict`; injected second writer → `external_conflict_paused`; resume does not re-send stale 28/18 after user changed setpoints.

---

## D05 — Canonical card repository and M5 gate

- Frontend source remains `ryanandrewbaker/two-state-thermostat`.
- **M5** adds integration mode (§ARCHITECTURE.md §7) with Vitest + HA tests AT-01–AT-18.
- **M6 production migration is blocked until M5 is complete** (PRD §8–§9).
- Optional: pin `two-state-thermostat.js` in integration HACS package after install tests (FR-10).

---

## D06 — Automatic Lovelace resource registration

Unchanged: prove in M5 or document manual resource URL.

---

## D07 — Minimum Home Assistant and Python versions

Defer numeric pin to M1.

---

## D08 — Room-specific temperature sources

Unchanged examples table (Kitchen / Family Room confirmed in repo only).

---

## D09 — Restart and failure policy

Unchanged: read-only first reconcile; Boost restore only if timer valid; no blind physical overwrite.

---

## D10 — Fan without compressor

Unchanged: virtual `FAN_ONLY`; physical `fan`/`fan_only`; min-cycle exemptions per reference.

---

## D11 — Native integration API (replaces helper shims) — **GPT-6 blocker**

**Rejected approach:** M4 “companion shims” registering `script`, `input_boolean`, `input_select`, or `timer` inside this integration so the **unchanged** card keeps working. Those domains are not generic platforms for third-party integrations.

**Approved approach:**

| Concern | Mechanism |
|---------|-----------|
| Dual setpoints, Off / heat_cool / fan_only | Native virtual `ClimateEntity` |
| Fan auto + speeds | `climate.set_fan_mode` on virtual climate (M5 card; actuator maps to Sensibo) |
| Boost start/extend/cancel | `integrated_split_system.boost_start` / `boost_cancel` |
| Dry | Integration `SwitchEntity` + physical `dry` when supported |
| Operating state, control temp, humidity, boost countdown | Climate attributes + `SensorEntity` where needed |
| Conflict resume | `integrated_split_system.resume_control` |
| Legacy YAML dashboards | Card **legacy mode** — existing helper/script calls |

**M1–M4:** Headless — no working card required. **M5:** Card + AT-* required before **M6**.

Full contract: **ARCHITECTURE.md §7**.

---

## Legacy YAML vs intended integration behavior

| Concern | Legacy YAML / card today | Integration + M5 card |
|---------|--------------------------|------------------------|
| Boost UI | `script.*_climate_boost` | `integrated_split_system.boost_start` |
| Fan auto/speed | `input_boolean` / `input_select` | `climate.set_fan_mode` on virtual climate |
| Dry | `switch.*_dry_mode` (YAML) | `switch.*_iss_dry_mode` (integration) |
| Operating state | Template sensor | `operating_state` attribute + sensor |
| Physical writes | Package actuator script | Integration actuator only |
| Card detection | `two_state_thermostat` | + `integrated_split_system: true` |

---

## Open questions for reviewers

1. Approve **D01** Kitchen-equivalent Boost backend?
2. Approve **D04** three-way failure model + safe `resume_control`?
3. Approve **D11** (no shims; M5 mandatory before M6)?
4. Freeze domain **`integrated_split_system`**?

---

## Decision log

| Date | ID | Outcome |
|------|-----|---------|
| 2026-10-24 | D01–D10 | Initial + first GPT-6 revision (merged PR #1) |
| 2026-10-24 | D11, §7 contract | Native API; drop M4 shims — pending GPT-6 review |
| 2026-10-24 | FR-05/FR-08, §7.2 services | Boost persistence + entity-targeted service payloads (GPT-6 PR #2 follow-up) |
| 2026-10-24 | FR-01, D02 | Equipment profiles + Sensibo Air/Sky; capability discovery (GPT-6 PR #2 final amendment) |
