# Peer domain plugins with shared CDP and OAuth

Status: accepted
Date: 2026-10-01

Payment, collection and liquidity are peer built-in domain plugins of dogopencli. Each plugin registers its commands, query capabilities, offline descriptions, source origins and exact inquiry contracts; the shared core owns CDP transport, request restrictions, browser lifecycle, OAuth/SSO recovery, cache mechanisms and output. Liquidity uses `https://iliquidity.alipay.com`, while payment and collection use their existing product-operation origins: sharing a core does not require sharing a base URL or copying another domain's endpoint contract.

This updates the plugin grouping described in [ADR 0004](0004-cli-runtime-boundaries.md), which originally grouped channel, cost and SLA as plugins. These capabilities now belong under their peer business domains. Implement liquidity through the existing capability registry and narrow shared seams; do not introduce a second browser/auth stack or a broad external-plugin installation framework. Independent third-party plugin packaging remains deferred.

Root `login`, `auth check` and `logout` manage the dedicated profile through one shared lifecycle. Each plugin supplies its verified application entry and inquiry-only auth check; root controls can select a target domain and must report which domain was checked. A healthy session for one origin does not prove another origin's authorization. Preserve existing payment/collection command behavior and keep business inquiries independent of interactive login or implicit refresh.
