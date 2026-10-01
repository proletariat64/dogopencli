"""Liquidity peer domain plugin (issue #72, ADR 0015).

Payment, collection and liquidity are peer built-in domain plugins sharing
the core CDP transport, OAuth/SSO lifecycle, cache and output. This plugin
declares the liquidity origin and application entry, the verified inquiry
contracts of every shipped business leaf, their mandatory kind metadata,
and the deferred leaves with their evidence reasons. Registration is wired
by the shared plugin registry (``plugins._load_builtins``) from
``leaves.LIST_LEAVES``, ``leaves.DETAIL_LEAVES`` and ``leaves.DEFERRED``.
"""
