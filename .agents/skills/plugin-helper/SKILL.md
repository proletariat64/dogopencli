---
name: plugin-helper
description: Verify a local dogopencli leaf package or pack a leaf directory into a portable ZIP using the host static validator.
---

# Plugin helper

Use the single [leaf development tool](../../../tools/leaf-dev/README.md).
Run `leaf.py verify` for static validation or `leaf.py pack` for a new delivery
directory. Read each command's `--help`. Do not implement another packer or wrapper.

For architectural review, assess every applicable optional capability using the
[SDK review requirements](../../../docs/agents/list-collection-sdk.md#assess-applicable-sdk-capabilities):
standard independent sources and assembly, qualified latest document selection,
existing temporal parsers, and persisted acquisition evidence. Record why custom
orchestration is needed when standard SDK mechanisms cannot express the behavior.
Static verify/pack validates declarations and rejects malformed metadata; it does
not establish business applicability or prove architectural compliance. Field names
alone do not qualify latest_by, and not every leaf needs version selection.
