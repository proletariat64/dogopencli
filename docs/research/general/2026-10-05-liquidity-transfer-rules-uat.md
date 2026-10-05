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

Standards/Spec review and remote CI are separate gates. Local Kimi review remains
blocked by automatic approval review of external source/spec transfer; no Kimi
confidence is claimed. This branch does not merge, publish or close #72; rules
monitoring remains HOLD.
