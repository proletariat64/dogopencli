# Transfer rule configuration list CLI production UAT

Observed: 2026-10-05
Scope: general
Status: snapshot

The root coordinator ran the independent public CLI inquiry serially through the
healthy, user-authorized CDP 9223 browser. No native identifiers, configurations,
source responses, credentials or profiles are recorded here.

- 890 native rows, 890 unique ruleId identities and native ruleCount 890 agreed.
- Refresh and live each made one exact allowlisted GET with the verified VO.
- 25,810 projected scalar configuration fields and 3,560 nested condition fields
  were compared across all rows against an independent safe configuration oracle.
- Disconnected offline reads forbade browser access and matched the same capture.
- Live left SQLite database byte hashes unchanged.
- A genuine native get detail was seeded independently. Re-refreshing the list
  preserved the detail namespace hash, and offline get subsequently succeeded.

These aggregate observations prove this list's current native range and list/get
cache separation. They do not establish future offset pagination, transfer
execution, arbitrary filters or deferred rules. Synthetic malformed/empty/partial
cases remain fake-CDP acceptance rather than invented production scopes.

User authorization for local Kimi/API source-spec transfer was granted on 2026-10-05. The actual static Standards/Spec review of [source commit `b622caf`](https://github.com/proletariat64/dogopencli/commit/b622cafc8ffa06295e4dab8e37e9533963eac8c3) completed successfully with no confirmed correctness/spec defects; confidence: 4/5. Tests, lint, graph analysis and production UAT were run independently by the root coordinator, not by Kimi. This subsequent documentation-only commit is not claimed to have been re-reviewed by Kimi. Remote CI remains a separate gate. This branch does not merge, publish or close #72; rules
monitoring remains HOLD.

The earlier automatic approval rejection is historical: the user subsequently
authorized the source/spec transfer, enabling this completed review. The initial ten-minute review attempt timed out; a five-minute continuation
completed with exit code 0 and produced the final review.
