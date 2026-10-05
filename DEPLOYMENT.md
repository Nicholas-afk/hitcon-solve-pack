# Hosting, verification and restore

Public frontend: https://nicholas-afk.github.io/hitcon-solve-pack/
Source: https://github.com/Nicholas-afk/hitcon-solve-pack
Stable checkpoint: Git tag `v0.1.0` and the corresponding [GitHub release](https://github.com/Nicholas-afk/hitcon-solve-pack/releases/tag/v0.1.0).

## Free static production configuration

GitHub Pages publishes the `main` branch's `/docs` directory using branch-based deployment. The existing `.nojekyll` bypasses Jekyll processing. GitHub's own Pages deployment job serves this directory; no custom workflow, package build or secret is required. Public repositories support Pages on GitHub Free. HTTPS is enforced; no custom domain, backend, paid service or additional billing authorization is needed. See [GitHub hosting documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages) and [publishing-source documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

All CSS/module/icon/report/download paths are relative to the project directory. The browser requests `./demo.json` for the worked example. `/private-report.json` is not published; that route exists only on the separately launched local viewer. The public HTML contains an empty private capability and hides private Refresh. The CSP restricts resources and connections to the current origin, disables forms/objects/base URLs, and permits no external assets. Web Crypto SHA-256 and Clipboard use the HTTPS secure context. No environment variables, API keys, repository secrets, CORS API endpoint or private report are required.

There are no application routes requiring SPA rewrites. `/hitcon-solve-pack/` and `/hitcon-solve-pack/index.html` open the application. In-page anchors navigate the currently loaded report. Reload returns to the empty public view because the app intentionally does not persist selected files or imported reports; open the worked example again. Unknown paths use GitHub's ordinary 404.

## Local setup

Install a compatible Python 3.11+ runtime, then:

```sh
git clone https://github.com/Nicholas-afk/hitcon-solve-pack.git
cd hitcon-solve-pack
git checkout v0.1.0
```

Run the complete local capture/replay/review workflow in [README.md](README.md). No pip installation is needed; invoke `python3 -m solvepack` from the repository directory. For browser-only development:

```sh
python3 -m http.server 8973 --bind 127.0.0.1 --directory docs
```

Open http://127.0.0.1:8973/. Static preview cannot execute Python. Do not expose the private `review` server to the internet. If `review` finds a busy port, choose another `--port`. For missing solver packages, use the intended private virtual environment and declare dependencies. Do not put secrets in `docs/`, Git or the manifest's public examples.

## Release checks

Before publishing, run `python3 tools/check.py` with Python and Node installed. Inspect tracked files and complete history for credentials, private records and personal fields, not just `.gitignore`. Check the tag's source archive includes licensing/setup files and excludes private workspaces. Push `main` and the release tag, then confirm Pages' latest successful build uses the intended commit through the [Pages API](https://docs.github.com/en/rest/pages/pages).

Open the actual public HTTPS site. Verify empty/example states, matched and blocked records, source links, original/changed-file comparison, restore/retry, candidate copy, report import rejection/recovery, direct index/anchor links and reload. Inspect desktop and 390/320px widths with real browser measurements. Check there are no runtime errors, external assets or calls to private endpoints. A successful Git push or deployment command is insufficient.

## Restore without losing private work

`v0.1.0` freezes this release. To obtain its exact source independently, download the release source archive and verify its published SHA-256, or clone and check out that tag. Keep private challenge directories outside the checkout. Local `.solvepack` storage and receipts are not included in the release.

To undo a later bad production change, inspect the history and revert only that change on `main`, run the checks, then push normally. Alternatively restore `docs/` from the tag on a new commit:

```sh
git restore --source=v0.1.0 -- docs
python3 tools/check.py
git add docs
git commit -m "Restore stable v0.1.0 frontend"
git push origin main
```

Then verify the new Pages build and repeat the public core workflow. This preserves history without force pushing or deleting private data. A later Python core restore should also restore its source from the same tag and rerun checks. The release archive is a source checkpoint, not a backup of private evidence.
