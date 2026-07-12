# Dataset Forge -- Archived Plugin Development Notes

> **Historical design record. Not a supported v1.9.2 product surface.**

The repository contains dormant plugin-oriented modules from an earlier
architecture. Dataset Forge v1.9.2 does not expose plugin discovery, plugin
installation, user-authored providers, transforms, exporters, captioners, or
execution hooks through its public CLI.

Do not use this file as an implementation guide or product commitment. Current
extension metadata is deliberately narrow:

- analyzer metadata lives in `analyzer_descriptors.py`;
- effective analyzer policy lives in `review_signal_policy.py`;
- preview provider metadata lives in `preview_provider_contract.py`;
- LOCAL_CLASSICAL is implemented directly as a built-in preview generator;
- ComfyUI and Krea remain static descriptors only.

Any future decision to expose third-party code would require an explicit
security, compatibility, lifecycle, and product-scope review. No such system
is part of the current roadmap.

See [docs/developer-guide.md](docs/developer-guide.md) for current development
guidance.
