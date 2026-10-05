# HITCON Solve Pack

[Open the synthetic demo](https://nicholas-afk.github.io/hitcon-solve-pack/) · [Stable v0.1.0 release](https://github.com/Nicholas-afk/hitcon-solve-pack/releases/tag/v0.1.0)

Capture a trusted local Python solve, replay it when provenance matches, and review saved evidence in a browser. Exact output bytes, file hashes, runtime, command and before/after snapshots persist as private immutable records. Manual receipts remain separate history. Reproduction never establishes organizer acceptance.

HITCON CTF 2026 scores accepted challenge flags. This is a preparation tool. Registration, competitive AI/tool permission and the actual submission interface remain unresolved. No organizer or mandatory sponsor integration is invented.

## Complete practice journey

Clone the [public repository](https://github.com/Nicholas-afk/hitcon-solve-pack), or download the v0.1.0 release archive and extract it. In a terminal, enter the repository directory. No pip installation or environment variables are required.

```sh
git clone https://github.com/Nicholas-afk/hitcon-solve-pack.git
cd hitcon-solve-pack
git checkout v0.1.0
```

Target: Python 3.11+ on POSIX. Tested: Python 3.14.3/macOS ARM64; Node 22.18.0 for checks. No installed dependencies. From this package:

```sh
mkdir -p ../private-practice-arithmetic
cp examples/arithmetic/* ../private-practice-arithmetic/
python3 -m solvepack capture ../private-practice-arithmetic
```

Replace `CAPTURE_ID` below with the actual capture `id` returned above:

```sh
python3 -m solvepack replay ../private-practice-arithmetic CAPTURE_ID
python3 -m solvepack review ../private-practice-arithmetic
```

Open **http://127.0.0.1:8976/**. Select the matched replay and check the actual current `input.json`. Change one input byte and replay the original capture: a STALE record is saved without launching the solver. **Refresh workspace records** displays it. Restore the input or intentionally recapture after changes. `examples/bytes/` supports the same journey. Keep private workspaces outside published source. Both examples are self-generated and explicitly synthetic.

## Bring a trusted solver

Each challenge has its own directory. Create a new manifest for existing regular files:

```sh
python3 -m solvepack init /absolute/private/challenge --challenge my-challenge --category Crypto --solver solve.py --input input.bin --arg=--mode --arg=decode
```

Repeat `--arg`, `--input` and `--dependency` as needed. `--arg=` passes an empty argument; arguments never become shell expressions. Declared packages must be installed in the selected Python runtime. `init` refuses an existing manifest. Add `--synthetic` for fixtures; the marker is an operator declaration, not an automatic detector of private data.

Manifest fields: `schema_version:1`, `challenge_id`, `solver`, `args`, `inputs`, `dependencies`, optional `category` and `synthetic`. Paths stay relative and cannot traverse, follow symlinks or reference reserved storage. Hashes cover raw manifest, solver and declared inputs. Declare all resources: undeclared files, network state and system libraries are outside the reproduction boundary.

For a solver with packages in a virtual environment, invoke Solve Pack with that environment's Python, for example `/absolute/runtime/bin/python -m solvepack capture /absolute/private/challenge` from this package. Capture and replay retain its launcher so the solver uses the same environment whose declared package versions were recorded. Missing packages fail explicitly. Pre-fix captures that launched the base interpreter from a virtual environment must be recaptured; they cannot establish that the environment's solver was reproduced. The core still needs no third-party package.

## Commands and manual receipts

- `capture ROOT [--timeout SECONDS]`: execute current manifest, snapshot before/after, save new evidence.
- `replay ROOT CAPTURE_ID`: validate baseline/current provenance; block drift or rerun the current command with its captured deadline and compare exact streams.
- `show ROOT RUN_ID [--full]`: validate after restart. Full output includes original snapshots and base64 streams.
- `review ROOT [--port 8976] [--limit 16]`: read-only localhost viewer. Requests 1–64 recent runs plus required captures; shows up to 64 recent receipts/run. Complete history remains in `show`.
- `receipt ROOT RUN_ID --candidate 'hitcon{…}' --state attempted|accepted|rejected`: explicit choice from actual output. Accepted/rejected also require `--official-time '2026-10-24T00:00:00Z' --source 'Actual response source' --evidence response.txt`. Optional `--points INTEGER` records a snapshot, never a score total.

Supply actual evidence for real responses. Synthetic sources/files must clearly describe the fixture. Receipt authenticity is unverified: these operator records cannot replace the official platform. Display rechecks attached hashes; changes/missing files warn without rewriting history. Later rejections preserve earlier entries.

Aware receipt times are normalized to UTC. Existing aware ledger/capsule times are normalized for browser display without rewriting the saved history. Option-like solver names are passed as explicit relative paths; pre-fix capsules that treated such names as Python options must be recaptured and cannot establish reproduction.

Exit codes: **0** candidate capture/reproduced replay/valid display, receipt or init; **2** persisted unsuccessful run; **1** invalid input, dependency or storage failure. Help exits 0. Results are JSON; review prints its URL. Failures explain recovery without a traceback. Retry execution explicitly; every capture/replay gets a new ID. Solvers are never retried automatically.

## Limits and recovery

Default deadline 30s; range 0.1–3600s. Combined retained output ≤1 MiB. FAILED, TIMEOUT and OUTPUT_LIMIT remain diagnostic even with flag-shaped text. Ordinary POSIX process groups are cleaned up, including descendants of an exited parent. This trusted-code runner is not a hostile-code sandbox or CPU/memory limit; escaped children are outside containment.

Serialized capsules/ledgers ≤2 MiB; oversize fails before writing. Preserve unusually large output with ordinary files if needed. Browser candidate display: ≤32 distinct values, each ≤4096 characters. A display limit never establishes a complete single-candidate result. Full CLI candidates have no invented official length cap. Binary output displays as UTF-8 with replacement characters; hashes verify original bytes. Browser comparison checks only the selected file, ≤16 MiB. Manifest/browser text limits count Unicode code points consistently.

Private directories/files use 0700/0600. Mutations acquire an exclusive lock. A remaining lock file contains its owner PID; verify the process before manually removing an abandoned lock. Fix missing packages in the selected runtime. Review/recapture changed provenance. Malformed evidence is rejected without silent rewriting. Viewer errors retain previous verified records and offer retry after repair. Restarting review changes its private token; **Reload local viewer** renews the page’s access. Reports over 2 MiB need a smaller review limit or individual `show --full`; busy ports need another `--port`.

## Private review and static hosting

Local server binds `127.0.0.1`, rejects foreign Host/Origin/cross-site requests, and requires an ephemeral random capability for private reports. Runtime HTML receives the token; source/Git/public bundles never do. Routes are fixed: no CORS, uploads, execution, writes or arbitrary private-file access. Child environment variables are allowlisted and inherited API credentials excluded. Trusted solvers still have your local account's privileges.

The private viewer shows its workspace path (very long paths are explicitly abbreviated), the selected run's time in UTC and short ID, and each run's time beside selection. Narrow selectors start with the result. Refresh preserves the selected record when it remains in the report. Errors retain its verified identity and evidence. These times describe local recording, not organizer submissions.

Synthetic-only static preview:

```sh
python3 -m http.server 8973 --bind 127.0.0.1 --directory docs
```

`docs/` supports GitHub Pages project subpaths under `nicholas-afk`. Static imports accept only explicitly synthetic reports ≤2 MiB. Pages hosts the public synthetic demo; real capture/replay/private review run locally. Pages cannot run Python or protect secrets. Keep live/private records and the surrounding entrant record out of public trees. No external assets, analytics, uploads or persistent browser storage. Imported content renders as text; hashes establish consistency, not authenticated authorship.

## Verification

```sh
python3 tools/check.py
python3 -m solvepack.demo_report
```

Checks cover processing, binary/literal execution, real virtual-environment package execution, limits/cleanup, before/after drift, persistence/tamper/atomic failures, receipt integrity, private HTTP boundaries, browser verification and actual event handlers. Desktop/mobile/320px inspections supplement them. Two selected HITCON 2022 crypto problems were reproduced privately using consulted author methods; automated checks preserved their output through capture/replay. This is guided historical reproduction, not blind solving, entrant performance or official acceptance. Other runtimes, full accessibility, human speed and competitive throughput remain unverified. Use `QUEUE_TEMPLATE.md` for honest timed evaluation. Rebuilding the public report updates observed synthetic times, not real contest evidence.

## Release documentation

[Architecture and data boundaries](ARCHITECTURE.md), [free hosting and restore](DEPLOYMENT.md), [attribution](ATTRIBUTION.md) and [release notes](RELEASE_NOTES.md) describe the completed capabilities and known limits. This repository's source, own icon and synthetic fixtures are [MIT licensed](LICENSE). No private evidence, historical challenge source/data or personal entrant record is distributed.
