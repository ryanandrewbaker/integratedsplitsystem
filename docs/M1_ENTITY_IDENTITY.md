# M1 entity and device identity

## Config entry unique id

The config flow sets `unique_id` from the **physical climate entity registry record** when available:

- Preferred: `{platform}.{entity_registry.unique_id}` (stable across entity id renames).
- Fallback: `entity_id:{physical_entity_id}` when the physical entity is not in the registry.

Rebinding a room to a different physical climate is a **reconfigure** flow (future milestone); M1 does not migrate unique ids automatically.

## Virtual climate entity unique id

Each virtual thermostat uses `{config_entry_id}_climate`. This is stable across HA restarts and independent of the physical entity id string.

## Device registry

M1 registers one **Integrated Split System** device per config entry (`identifiers={(DOMAIN, entry_id)}`).

We intentionally **do not** set `via_device_id` to the Sensibo device. In Home Assistant, `via_device` means connectivity through a parent hub, not “this virtual entity wraps that climate entity.” The physical binding is exposed read-only in state attributes as `physical_climate_entity_id` until M2+ topology is modelled explicitly.
