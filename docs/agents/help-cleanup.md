# Help architecture cleanup (#248)

The public entry remains `dogopencli.cli:main`. Current core and installed leaf
declarations generate one current-node document; diagnostics enter before format
selection. `command_model.emit_help` selects terminal width and sends the same
document to JSON serialization or `helpspec.render_text(document, width)`.
The renderer does not discover declarations, load adapters or inspect the terminal.

## Removal inventory

The pre-edit reference audit used source/test graph coverage and literal caller
checks at `d059ad0018e434eb9c497a192ee25d9c57380664`. It distinguished direct
packaged entry points, internal consumers and test fixtures.

| Candidate | Consumers and reachability | Decision and replacement |
| --- | --- | --- |
| `helptree.py` static help routes | Public main imported only `leading_command`; `help_main` and `business_entry` had no active callers. Five historical fixtures patched its unused `NODES`. | Remove the module and obsolete fixture patches. Move `leading_command` unchanged to `command_model` for auth error classification. Current CLI traversal and rejected-syntax tests cover navigation. |
| `auth/spec.py` document/rendering helpers | Only the old help router and auth shell help branch consumed them. The catalog still consumes auth declarations. | Remove `_describe`, `document` and `render_text`; route the auth shell through current help. Keep declarations and execution parsers. |
| `helpspec.py` old node renderer and help parser | Old router and domain shell consumed the renderer; only old router used `HelpParser` and `validate_help_options`. | Replace the renderer with document/width input; remove the obsolete help parser. Current `parse_options` retains validation. |
| Domain and GUI shell help branches | Root normally intercepts help, but direct module callers can still reach these branches. | Forward to current resolve/emit instead of static catalog or bespoke documents. Keep domain execution and GUI server behavior. |
| Leaf shell help branch | Public root and direct leaf shell callers share resolution. | Forward the resolved invocation to the single help output boundary. Keep generic result/error `emit` and `_text`. |
| Static catalog, business declarations and describe renderers | Legacy business modules, tests, describe and GUI preview still consume them. | Keep. This cleanup does not perform the separate #218 business migration. |

No business tests were deleted. Five historical fixture imports and monkeypatches
were removed because they only targeted the discarded help router. Existing
progressive public CLI tests already cover their replacement navigation.

## Verification contract

Before structural edits, a public CLI breadth-first traversal captured all 54
advertised nodes with bundled declarations in an isolated configuration. The
comparison preserves complete envelope keys and values, document keys, every old
option field and old contract field, error spelling and existing error order.
Only added `argument_contract.modes` (with its version wrapper on newly annotated
host controls) and additional known errors are allowed. No type names, argument
requirements, summaries, examples, paths or output meanings are rewritten.

Public CLI regressions cover all advertised children, both help flags, explicit
JSON and default JSON, operation isolation, rejected old syntax, no runtime
activation, broken peers and invalid configuration contents. Width tests cover
36/88/140 columns, CJK prose, intact long tokens and Unicode command paths,
redirected output independent of `COLUMNS`, meaningful defaults and empty choices.
Cache-miss/stale/contract-change execution tests check declared errors while
preserving runtime codes. FX unmapped parameters and payment local filters check
mode metadata against actual cached execution. Synthetic declarations exercise
required, repeated and get-specific acquisition parameters.

Runtime error groups are documented next to their shared rule projections in
`leaves/operation_rules.py`: declaration/activation, state/cache storage, inquiry
transport, completeness policy and cache replay. They are known sets; third-party
adapter errors can add codes and consumers must remain tolerant.
