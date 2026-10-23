# Product naming and compatibility

| Concept | Identifier |
|---|---|
| Product / integration display name | Integrated Split System |
| Local Cursor workspace | `integratedsplitsystem/` |
| Proposed GitHub repository | `ryanandrewbaker/integratedsplitsystem` |
| Proposed HA integration domain | `integrated_split_system` |
| Python integration package | `custom_components/integrated_split_system/` |
| Current card repository (unchanged) | `ryanandrewbaker/two-state-thermostat` |
| Existing Lovelace card type (unchanged initially) | `custom:two-state-thermostat` |

The existing card and YAML entities remain in production during development. Do not rename or modify them outside an explicitly approved compatibility/migration milestone.

The HA domain is a proposed implementation decision for M0; freeze it before creating persisted config entries.
