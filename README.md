# bonrs

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![GitHub stars](https://img.shields.io/github/stars/hoangtrongbinh1111/bonrs?style=social)](https://github.com/hoangtrongbinh1111/bonrs/stargazers) [![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**English** · [Tiếng Việt](README.vi.md) · [Full guide](docs/GUIDE.en.md) · [Contributing](CONTRIBUTING.md) · License: [MIT](LICENSE)

> ⭐ If bonrs is useful to you, please **[star the repo](https://github.com/hoangtrongbinh1111/bonrs)** to support it and follow new releases.

bonrs is a self-hosted, multi-user web app. You give it a research idea and a target journal. It uses Claude (Claude Code) to work through 10 stages on its own: scoping, finding and reading the literature, profiling the journal, planning, running experiments, drafting, multi-round peer review, revision, packaging the submission, and a retrospective.

You only approve a few key checkpoints, upload paywalled PDFs when asked, and read the final draft.

The interface is available in English and Vietnamese (switch **VI / EN**), with light and dark themes.

## Install on a server (Docker)

Requirements: Docker and Docker Compose, about 4 GB of disk for the image (includes TeX Live).

```bash
git clone https://github.com/hoangtrongbinh1111/bonrs.git bonrs && cd bonrs
cp .env.example .env          # set the admin email and password
docker compose up -d --build
```

Open `http://<server>:8765` and sign in with the admin account from `.env`. In **Admin**:

- enter a shared Anthropic API key (for people without their own connection, and for automatic knowledge-base updates);
- enter a contact email (Crossref, Unpaywall) and OpenAlex / Semantic Scholar keys if you have them;
- create accounts for members.

**Admin → Operations** comes with sensible defaults (2 parallel jobs, 24 hours per job, 30 USD per stage, model claude-opus-5-5); change them only when needed.

### Claude connection

Each user picks one in **Account → Claude connection**:

- **Their own Claude Pro/Max plan**: run `claude setup-token` on their own computer and paste the `sk-ant-oat…` token. Usage counts against their plan. Plans are personal: everyone uses their own token and never puts it anywhere shared.
- **Their own API key** (console.anthropic.com), pay as you go.
- **The server's shared key** (default), entered by the admin.

### Running in the background

`docker compose up -d` runs the server in the background and restarts it at boot (`restart: unless-stopped`). All work happens on the server: closing the browser or turning off your laptop changes nothing. If the server restarts mid-run (update, power cut), running sessions resume from the unfinished stage. With Docker Desktop on Mac/Windows, turn on **Start Docker Desktop when you sign in**.

All data lives in `./data`: research sessions (each one a git repo), the knowledge base, the database and SSH keys. Backing up that folder is enough.

When exposing it to the Internet, put it behind an HTTPS reverse proxy (Caddy, Nginx) and set `BONRS_SECURE_COOKIE=1`.

## Usage

1. **New idea**: write a few lines, then click **AI writes & debates for you**. The AI expands it into a complete brief (problem, hypotheses, data, method, contribution, scope), runs a debate between 4 roles (proposer, critic, journal editor, implementer), settles on a final version and asks about anything unclear. Answer to run another round, or click **Use this version**. Pick the journal (suggestions from OpenAlex), base papers, field and machines. Section 6 sets the model (from a list), the cost cap per stage (pre-filled from the cost of past stages on the server) and whether to continue automatically when nobody approves (hours and minutes).
2. **Overview**: follow the 10 stages, cost and review scores. When the agent stops at a checkpoint, choose Approve, Continue with guidance, or Stop. If nobody answers within the set time, the agent continues on its own.
3. **Files**: see every output (scope, literature review, journal style guide, experiment code and results, PDF/DOCX draft). Select text to comment, or edit directly. Upload paywalled PDFs when the "The agent needs you to upload documents" banner appears.
4. **Review & handover**: a one-page editor's letter (read this first), review rounds, response letter, submission checklist and AI-use declaration.
5. **Comments**: every open comment is handed to the agent in the next revision round, then distilled into lessons for next time.
6. **History**: every stage, review round, edit and upload is a checkpoint. Click one to see which files changed (+/− lines); click a file to see added (green) and removed (red) lines. **Compare two checkpoints**: click A, then B. Click a stage in the progress bar to see that stage's own history and trace. Download the whole session as a zip, git history included.

## Experiment machines

By default experiments run on the bonrs server itself, in each session's `exp/` folder (with GPU if you enable the `deploy` block in `docker-compose.yml`). Nothing to configure. To add your own GPU machine, go to **Machines → Add your own machine**:

1. Enter `user@address` (and the port if not 22), exactly as you would `ssh` into it.
2. Log in to that machine and run the one-line command the page shows (it adds your bonrs account's SSH key to `~/.ssh/authorized_keys`).
3. Click **Test connection**: bonrs reads CPU, RAM, GPU, Python and disk, then suggests a name, a folder (`~/bonrs-runs`, one subfolder per session) and how to prepare the environment (by default it creates `.venv` and installs `requirements.txt`; it uses conda if present).
4. When creating a session (or in its Configuration tab), tick the machines to use. With several machines the agent sends each independent run (seed, fold, ablation) to the least busy one; a single training run is never split.

SSH keys belong to each person's bonrs account, not to a machine. Slurm clusters still work through `bonrs.yaml` (`type: slurm`) but are not in the UI yet.

## Knowledge base

One shared base for everyone, organised from general to specific:

| Tier | Contents |
|---|---|
| `00-general` | Fixed rules and writing skills for every field |
| `10-domain/<field>` | Field reporting standards, statistics, experiment types |
| `20-article-type` | By article type: research, review, bibliometric, case |
| `30-journal` | Rules of each journal, extended after every session |
| `40-experience` | Accumulated lessons, weighted down over time |
| `50-user/<id>` | Each person's preferences and writing voice |

Each skill is a markdown file with frontmatter (`level`, `domain`, `journal`, `tags`, `source`, `confidence`, `status`). The agent loads only `active` skills that match the session.

Adding knowledge:

- **Contribute documents**: upload PDF/DOCX/MD/HTML or paste a URL. The agent turns it into draft skills.
- **Automatic sources**: 7 built in (Taylor & Francis, Elsevier, Springer, Wiley, PLOS, IEEE, EQUATOR). Admins add, disable or remove sources in **Knowledge base → Automatic sources** (name, URL, tier, field) and pick a schedule: weekly by default, or daily / monthly / off. Unchanged pages are skipped at no cost; new or changed pages become draft skills awaiting review (or are auto-approved above 0.8/0.9 confidence if the admin enables it). The schedule needs the server's shared key.
- **Pending review**: admins read, edit, approve or reject each draft skill.
- Members create personal or session-only skills, then click "Propose to the shared base" for admin review.

## Quality guarantees

- Every number in the paper must exist in `exp/results/registry.json`; every Results/Discussion sentence maps to an entry in `paper/claims.yaml` with an allowed claim strength.
- Every citation needs a DOI/arXiv ID and must be in the downloaded literature; retracted papers are removed.
- `bonrs audit` defines "done": clean compile, no placeholders, numbers match their source, no overclaiming words.
- A 5-seat independent review panel, including a "killer reviewer" and an Area Chair, compares the paper with work published in the target journal; at most 3 rounds.
- The AI-use declaration follows the publisher's template. bonrs never removes or hides traces of AI use.

## Command line (development)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
python3 test_bonrs.py                                    # offline tests
python3 bonrs.py new "<idea>" --journal "<journal>" --domain ml
python3 bonrs.py run <slug> [--from 03_plan] [--to 05_draft]
python3 bonrs.py approve <slug> --note "guidance"
python3 bonrs.py audit <slug> --final
BONRS_ADMIN_EMAIL=a@b BONRS_ADMIN_PASSWORD=x .venv/bin/uvicorn bonrs.web:app --port 8765
```

Detailed plan and next milestones (Vietnamese): `PLAN.md`.

## Contributing

Bug reports, ideas, docs, translations, knowledge skills and pull requests are all welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to run everything with a mock Claude (no cost) and the code conventions. Please report security issues privately as described in [SECURITY.md](SECURITY.md). Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

If you find the project useful, a ⭐ on [GitHub](https://github.com/hoangtrongbinh1111/bonrs) is the simplest way to support it.

## Sponsorship

bonrs is free and open source. If you or your organisation would like to sponsor it (server, GPU or API costs) or collaborate, please contact **[binhht99@lqdtu.edu.vn](mailto:binhht99@lqdtu.edu.vn)**.

## License

bonrs is released under the MIT license (see [LICENSE](LICENSE)). Third-party components: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Claude Code is distributed by Anthropic under its own terms.
