# M1 supported runtime versions

Minimum versions for the **Integrated Split System** custom integration (Milestone M1). Pin sources: [Home Assistant 2026.10 release](https://www.home-assistant.io/blog/) and the project's `requirements-dev.txt` test harness.

| Component | Minimum version | Notes |
|-----------|-----------------|-------|
| Home Assistant | **2026.10.2** | Declared in `hacs.json` (`homeassistant` key) and exercised by CI/dev via `pytest-homeassistant-custom-component`. |
| Python | **3.13.2+** | Matches Home Assistant 2026.10 core requirement; use the Python version shipped with your HA installation (Container, OS, or venv). |

M1 uses Config Entry, Options Flow, `ClimateEntity`, entity/device registry, and `Store` APIs available in current core. Do not install this integration on older HA releases without retesting.
