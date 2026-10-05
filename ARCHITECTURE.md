# Architecture and boundaries

## One complete workflow

A local operator places a trusted Python solver, inputs and a manifest in a private challenge directory. `capture` records a solve. `replay` compares declared provenance with that capture before launching; a changed input saves STALE/NOT_RUN. A matching launch compares exact stdout/stderr bytes. `review` displays verified records on localhost. Optional operator-entered receipts attach actual response evidence separately. A reproducible candidate is never labelled organizer acceptance.

The public [synthetic demo](https://nicholas-afk.github.io/hitcon-solve-pack/) demonstrates this evidence-review interaction with self-generated records. Open the worked example, choose a matched replay, download `input.json`, and select it for local SHA-256 comparison. Selecting `input-changed.json` shows a mismatch without changing the saved replay's verdict. A saved STALE record explains why execution was blocked. The public browser does not launch a solver or accept private reports. To capture real solves, clone this repository and follow [README.md](README.md).

## Small components

| Component | Responsibility | Boundary |
| --- | --- | --- |
| `solvepack/model.py`, `provenance.py` | Strict relative manifest paths, runtime/package metadata and before/after SHA-256 snapshots | Only declared resources; package versions, not all package bytes |
| `runner.py` | Literal Python argument execution, deadline, combined output bound, ordinary POSIX group cleanup | Trusted code with the operator's privileges; no hostile-code sandbox |
| `capsules.py`, `store.py`, `workflow.py` | Immutable IDs, exact base64 streams, validation, private permissions, exclusive lock and atomic persistence | Private challenge directory; malformed evidence fails explicitly |
| `receipts.py` | Append separate operator-entered history; recheck attached evidence hash on reading | Does not authenticate the organizer or compute live standings |
| `report.py`, `review.py` | Validated projection and read-only capability-protected loopback HTTP | Fixed routes; no upload, execution, write or public server |
| `docs/model.mjs`, `app.mjs` | Validate report/byte evidence, render text, browser-local file SHA-256, feedback and recovery | Synthetic imports only on public hosting; 2 MiB reports, 16 MiB comparison files |
| `docs/` on GitHub Pages | Static HTML, CSS, modules, own SVG and synthetic fixture data | No backend, environment secrets, authentication or private evidence |

## Data, dependencies and integrations

The core uses Python 3.11+ standard-library modules; it is tested on Python 3.14.3/macOS ARM64. Node 22.18.0 runs the browser-model tests and is unnecessary for normal use. A trusted solver may need its own packages: declare them in the manifest and run Solve Pack with that virtual environment's Python. Capture retains the virtual-environment launcher, while recording executable hash and declared package versions. There are no package installs, database, paid API, sponsor SDK or external service calls in the public workflow.

Local capsules and ledgers are private (0700 directories, 0600 files). Private viewer HTML receives an ephemeral random capability at runtime; source HTML has an empty token. Loopback requests check Host, Origin and cross-site metadata, require the capability and expose fixed read-only routes. Restarting the local server requires **Reload local viewer** to renew access. Allowlisted solver environment excludes inherited API credentials; a trusted solver can still read local files with the user's privileges.

Pages serves public synthetic reports over HTTPS. The browser reads chosen files in memory and does not upload them. There is no app analytics, cookie, localStorage, external asset or background service worker. GitHub itself operates the hosting service and [logs visitor IP addresses](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages). Do not publish private challenge directories, receipts, API credentials or the surrounding entrant record.

## Proven behavior and limits

The 61-case suite covers real runner/CLI/storage/HTTP boundaries and browser validation/event handlers, including a real isolated virtual environment. Negative outcomes (failure, timeout, output limit, ambiguous candidate, changed provenance and differing streams) remain distinct. Actual browser checks complement the suite. `docs/demo.json` contains observed synthetic fixture results, not invented benchmark or official acceptance evidence.

Reproduction covers only declared files, runtime identity, literal arguments and declared package-version metadata. Undeclared inputs, network, system libraries, escaped child processes, hostile-code containment, full accessibility and other runtime/platform behavior are unverified. Manual receipt authenticity is unverified. Neither cryptographic consistency nor this release establishes competition points, a blind-solve benefit or a speed improvement. Live AI/tool terms and registration were still unpublished at release preparation.
