# Liquidity batch A implementation

Specification: [#87](https://github.com/proletariat64/dogopencli/issues/87).
Baseline: `f8ada67`, version 0.2.5; 69 supported and 64 unsupported query leaves.

## Task graph

- [#90](https://github.com/proletariat64/dogopencli/issues/90): decisions list contract and implementation.
- [#91](https://github.com/proletariat64/dogopencli/issues/91): transfers list contract and implementation.
- [#92](https://github.com/proletariat64/dogopencli/issues/92): quote-group completeness investigation; optional implementation only after all gates pass.
- [#93](https://github.com/proletariat64/dogopencli/issues/93): acceptance, blocked by the three preceding tickets.

Both required lists depend on current native contract investigation. First enablement
requires nonempty typed identity, verified native scope, complete representative
acquisition and registered production CLI UAT. Local CI and Kimi review are separate
evidence. Mandatory delivery is 2/2 lists plus the quote investigation conclusion;
an optional quote list has its own 1/1 denominator.

Reuse the existing inquiry transport, liquidity registry, capture store and public
CLI test seam. List captures remain independent of existing native detail/history
captures. No new getter, mutation, other batch or release bump belongs to this PR.

Kimi CI and Standards/Spec review use the locally installed CLI with JSON output.
Each result must report `confidence: ?/5` (0 means no confidence; 5 is full confidence).
