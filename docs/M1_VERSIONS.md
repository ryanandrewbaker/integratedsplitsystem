# M1 supported runtime versions

Minimum versions for the **Integrated Split System** custom integration (Milestone M1). Sources: [Home Assistant 2026.10.2 on PyPI](https://pypi.org/project/homeassistant/2026.10.2/) and [pytest-homeassistant-custom-component 0.13.373](https://pypi.org/project/pytest-homeassistant-custom-component/0.13.373/).

| Component | Minimum version | Notes |
|-----------|-----------------|-------|
| Home Assistant | **2026.10.2** | Declared in `hacs.json` (`homeassistant` key) and exercised by CI/dev via `pytest-homeassistant-custom-component`. |
| Python | **3.14.2+** | Required by Home Assistant 2026.10.2 and the pinned test harness; use the Python version bundled with your HA installation. |

M1 uses Config Entry, Options Flow, `ClimateEntity`, entity/device registry, and `Store` APIs available in current core. Do not install this integration on older HA/Python releases without retesting.

## Local validation commands

```bash
python --version
python -m pip install -r requirements-dev.txt
python -m pip show homeassistant pytest-homeassistant-custom-component
python -m pytest tests/ -q
```

Record the exact output in PR test plans when validating M1 gates.
