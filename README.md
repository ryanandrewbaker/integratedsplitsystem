# Integrated Split System

**Status: PRD/design only. Not an installable Home Assistant integration.**

An upcoming native Home Assistant custom integration that wraps an existing physical climate entity (initially Sensibo), presents a first-class two-target thermostat entity under Devices & services, and works with the [existing Two State Thermostat dashboard card](https://github.com/ryanandrewbaker/two-state-thermostat).

## Start here

- [Product Requirements Document](docs/PRD.md)
- [Architecture (M0)](docs/ARCHITECTURE.md)
- [Design decisions D01–D10 (M0)](docs/DECISIONS.md)
- [Composer / GPT-6 review gates](docs/REVIEW_PROCESS.md)
- [Agent implementation rules](AGENTS.md)

There is deliberately **no Python implementation yet**. Architecture uses a **native integration API** and an **M5 card update** (no `script`/`input_*` shims). **M5 is required before any production room migration (M6).** Do not deploy to HA from this repo without explicit approval.

Proposed repository: `ryanandrewbaker/integratedsplitsystem`.

Naming: **Integrated Split System** is the product name; `integratedsplitsystem` is the GitHub/folder name; `integrated_split_system` is the proposed Home Assistant integration domain. The existing `custom:two-state-thermostat` card remains a separate compatibility contract during migration.
