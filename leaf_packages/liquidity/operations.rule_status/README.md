# Transfer-rule run overview

One native summary response through the List SDK, never expanded detail or execution.

Use required `--from-time` / `--to-time` explicit UTC instants (Z or numeric offsets). Both bounds are inclusive: equal bounds select an entire second and the upper second includes .999ms. Native trigger milliseconds and nullable actual trigger time remain unchanged.

Only the assigned ten summary fields are retained. One qualified width5000 response must match native total and unique positive integer IDs; narrow the scope if coverage fails. Width5000 is not a measured maximum. No Get or with-detail. Bare offline reads the saved trigger scope; help lists flags and interpretation limits.

The instant history axis is expectTriggerTime. Public --from-time/--to-time
remain explicit-offset whole seconds. The effective upper includes the final
second through .999; history codecs preserve that boundary and reject narrower
millisecond windows that would otherwise change the original native query.
