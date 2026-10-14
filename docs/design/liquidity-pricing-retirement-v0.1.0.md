# Liquidity pricing retirement implementation

Authoritative specification: [#172](https://github.com/proletariat64/dogopencli/issues/172).
Implementation tracker: [B01 #164](https://github.com/proletariat64/dogopencli/issues/164).

## Scope and compatibility

The business decision retires pricing factors, factor-values, cost-prices,
strategies, client-prices, and fee-orders. Retired list and refresh commands remain
recognizable refusal entries. They return `UNSUPPORTED_CAPABILITY` rather than
successful cached or empty data. Existing get deferrals remain deferrals; no get
path is added to resources that never had one. R01 retains its separate scope.

No backend endpoint shutdown, pricing calculation, dataset deletion, or migration
is part of this change. The retirement is a business decision even when historical
source endpoints still respond. Shared source contracts must be assessed by caller.

## External import owner

The installed `duckdog-import` helper is external to this checkout. Its active
registry previously contained `liquidity/pricing/factors` (identity `code`) and
`liquidity/pricing/strategies` (identity `id`). Its saved `--input` mode bypasses
dogopencli, so a CLI-only change cannot stop publication.

The [external owner patch](../../scripts/patches/b01-duckdog-import.patch) removes
these active registrations and rejects all six retired selectors at CLI input
selection and direct validation/publication. Rejection precedes reading an input
file, launching a live command, importing DuckDB, creating storage, or replacing
datasets. Existing views, registry rows, and Parquet generations remain intact.
Read-only historical analysis is unaffected.

The patch also adds two tests to the owner's existing verification suite and
updates its skill and import contract. It is a patch to the existing helper,
not another importer. For an installation with the original owner files, apply
it from that owner's repository root using `git apply --check` before `git apply`.
The owner files are untracked local support material; they are not introduced as
a runtime dependency of dogopencli. The patch is retained here for review and
reproduction. An already updated installation can verify it with
`git apply --reverse --check`.

Local installation was updated after hash-checking the originals. The existing
owner verification suite passes nine synthetic tests, including all six selectors
in both live and saved-input modes and direct publication preserving an existing
dataset. These checks use temporary storage and no production queries.

## Historical evidence and storage

All three referenced Dima tickets were read in full before implementation. The
reorganization item controls scope; original closed/cancelled items are superseded,
not evidence of implementation completion.

The existing dated FTP research in PDKB received an applicability annotation:
business retirement does not erase historical formulas or observations, and those
observations do not prove current business use. No knowledge graph was rebuilt.
The private research document and its production samples are not copied into Git.

Read-only inventory covered the configured CLI SQLite cache and the known local
duckdog catalog and Parquet root. Neither reported stored pricing slots/datasets
at inventory time. File hashes were recorded privately for preservation checks.
This is a bounded inventory, not proof that no other saved JSON or external stores
exist. Any additional storage or independent importer requires separate inventory;
no automatic cleanup or production import is performed.

## Verification boundary

Repository CLI tests use the confirmed public CLI, fake CDP/transport spy, and
temporary SQLite seam. External import checks run against the installed helper
independently. Local gates, code review, production-configured refusal smoke,
and hosted PR checks are reported separately in the implementation PR.

The local production-configured smoke exercised all six resources in offline,
live, and refresh modes: 18 explicit retirement refusals. Linux `strace` recorded
no connect/send operations. All 20 known store files retained their baseline
hashes. This proves local retirement behavior with production configuration;
it is not a fresh read of production source data or an authenticated browser UAT.

The sampled-field builder cannot reconstruct the current baseline's later
contracts from its historical report inputs. Retired entries were therefore
removed from the active field catalog directly; no new field evidence is inferred.

Retired-command production acceptance requires no browser session: refusal must
occur before CDP access even with the user's normal production configuration.
No retired source endpoint is queried to prove retirement. No other browser
session, profile, authentication state, or production configuration is changed.
