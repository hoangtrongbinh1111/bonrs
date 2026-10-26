# Third-party software

bonrs itself is released under the MIT License (see `LICENSE`). It ships or installs the following software, each under its own license.

## Included in this repository

| Component | Version | License | Where |
|---|---|---|---|
| marked | 12.0.2 | MIT | `web/vendor/marked-12.0.2.min.js` |
| Lucide icons | 0.454.0 | ISC | `web/vendor/lucide-0.454.0.min.js` |

## Python packages (installed from PyPI, `requirements.txt`)

| Package | License |
|---|---|
| FastAPI | MIT |
| Starlette | BSD-3-Clause |
| Uvicorn | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| Requests | Apache-2.0 |
| PyYAML | MIT |

## Installed into the Docker image (not part of this repository)

| Software | License |
|---|---|
| Claude Code (`@anthropic-ai/claude-code`) | Proprietary: Anthropic's terms (commercial terms for API keys, consumer terms for Claude Pro/Max plans). bonrs runs it; it does not redistribute it. |
| Python 3.12, Node.js 22 | PSF License, MIT |
| Debian packages: git, OpenSSH, rsync, zip, poppler-utils, pandoc, sudo, tini, TeX Live | GPL, BSD, MIT and other free licenses (see each package's `/usr/share/doc/*/copyright` in the image) |
| Fonts loaded from Google Fonts: Plus Jakarta Sans, Source Serif 4, JetBrains Mono | SIL Open Font License 1.1 |

## Data services used at run time

OpenAlex (CC0 data), Crossref, Unpaywall, Semantic Scholar (its own API terms), Europe PMC and arXiv are called over their public APIs. Respect each service's terms and rate limits. Papers you upload remain under their publishers' licenses; bonrs only keeps them inside your run.
