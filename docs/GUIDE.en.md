# bonrs installation and user guide

bonrs is a web app that runs on your own server and is shared by several users. You give it a research idea and a target journal; an agent (Claude Code) works through 10 stages, from reading base papers and scoring hypotheses to writing the paper, running several review rounds and packaging the submission. You only approve at a few key points.

## 1. What bonrs does

| Stage | What the agent does | Approval gate |
|---|---|---|
| 0. Hypotheses | Reads the base papers, runs a 4-role discussion of improvements, scores each hypothesis for chance of success and chance of acceptance | Always stops for you to choose |
| 1. Literature | Searches, reads and synthesises the literature; checks novelty; asks you for paywalled PDFs if needed | Yes |
| 2. Journal | Reads the author guidelines and published papers; decides article type, format and style | |
| 3. Plan | Designs the experiments and fixes the success criteria before running anything | Yes |
| 4. Experiment | Writes code, runs it on the experiment machines, reads logs, records results | |
| 5. Draft | Writes the paper in the journal's style; every number comes from real results | |
| 6. Review | 6 anonymous reviewers and one editor who summarises | |
| 7. Revision | Revises according to the reviews and your comments, until the score is reached | Yes, after each round |
| 8. Submission | Cover letter, checklist, AI-use declaration, editor letter | Yes |
| 9. Retrospective | Records lessons in the knowledge base (an admin approves them) | |

Everything about a run is kept: files, the history of every attempt, comments, costs.

## 2. Installation

### 2.1. Requirements

- A Linux server (Ubuntu 22.04/24.04 recommended) or a Mac/Windows machine with Docker Desktop.
- 4 CPU cores, 8 GB RAM or more (16 GB to run 2 runs at once), 20 GB free disk. The image with TeX Live takes about 4 GB.
- Docker 24+ and Docker Compose v2.
- Internet access to api.anthropic.com and the scholarly sources (OpenAlex, Crossref, arXiv…).
- A way to connect to Claude: an Anthropic API key, or each user's own Claude Pro/Max plan (see section 4).

### 2.2. Install on a Linux server

1. Install Docker:
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER   # log out and back in
   ```
2. Get the code:
   ```bash
   git clone https://github.com/hoangtrongbinh1111/bonrs.git bonrs && cd bonrs
   ```
3. Create the settings file and set the admin account:
   ```bash
   cp .env.example .env
   nano .env      # set BONRS_ADMIN_EMAIL and BONRS_ADMIN_PASSWORD (a long password)
   ```
   The password in `.env` is only used on the first start; change it later on the Account page.
4. Start it (runs in the background and restarts when the machine boots):
   ```bash
   docker compose up -d --build
   ```
5. Open `http://<server-address>:8765` and sign in with the admin account.

Logs: `docker compose logs -f`. Stop: `docker compose down` (your data stays).

### 2.3. Install on a Mac or Windows

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/), open it and wait until it is running.
2. In Docker Desktop → Settings → General, turn on **Start Docker Desktop when you sign in** so bonrs comes back after a reboot.
3. Open Terminal (Windows: PowerShell) and follow steps 2–5 above.

### 2.4. Expose it safely on the Internet (HTTPS)

Put bonrs behind a reverse proxy with HTTPS. Example with Caddy (gets a Let's Encrypt certificate automatically):

```
bonrs.your-domain.org {
    reverse_proxy 127.0.0.1:8765
}
```

Then change `docker-compose.yml` so the port only listens locally: `ports: ["127.0.0.1:8765:8765"]`, and add `BONRS_SECURE_COOKIE=1` to `.env`.

### 2.5. Use the GPU of the bonrs server itself

Install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html), uncomment the `deploy:` line in `docker-compose.yml` and run `docker compose up -d` again. Experiments on the "bonrs server" machine will see the GPU.

### 2.6. Environment variables

| Variable | Meaning | Default |
|---|---|---|
| `BONRS_ADMIN_EMAIL`, `BONRS_ADMIN_PASSWORD` | Admin account created on first start | required |
| `BONRS_PORT` | Web port on the host | 8765 |
| `BONRS_SECURE_COOKIE` | `1` when served over HTTPS | detected |
| `ANTHROPIC_API_KEY` | Shared key (can be entered in the UI instead) | empty |

### 2.7. Backup, update, uninstall

- **Backup:** all data lives in `./data` (runs, knowledge base, database, each user's SSH key). Copying this folder is enough, e.g. `tar czf bonrs-backup-$(date +%F).tgz data`.
- **Update:** `git pull && docker compose up -d --build`. Runs that were in progress continue from the unfinished stage once the server is back.
- **Uninstall:** `docker compose down`, then delete the folder if you no longer need the data.

## 3. First-time setup (admin)

1. **Admin → API keys & data sources:** enter the shared Anthropic API key (console.anthropic.com → API Keys). It is used by people without their own connection and for automatic knowledge-base updates. The agent never sees the key: the server adds it when forwarding requests. Also enter a contact email (Crossref/Unpaywall) and OpenAlex / Semantic Scholar keys if you have them.
2. **Admin → Users:** add accounts for members (email, temporary password). They change it on their Account page.
3. **Admin → Operations:** sensible defaults are already filled in (Claude Opus 5.5, a budget cap suggested from real run costs, auto-continue after 12 hours, 2 runs at once, 24 hours per job). Change them only when you have a reason; there is a button to restore the defaults.
4. **Knowledge base → Automatic sources:** review the 7 built-in sources, add your own, choose the update schedule (weekly by default).

## 4. Connecting to Claude

Each user chooses under **Account → Claude connection**:

| Option | When to use it | Cost |
|---|---|---|
| My Claude Pro/Max plan | You already have a Pro or Max plan | Counts against your plan's usage limits |
| My API key | You want to pay per use yourself | API pricing |
| Server's shared key | Default | Billed to the key the admin manages |

To use a Pro/Max plan:

1. On your own computer, install Claude Code: `npm install -g @anthropic-ai/claude-code`.
2. Run `claude setup-token` and sign in to your Claude account in the browser.
3. Paste the code starting with `sk-ant-oat` and click Save.

A Claude plan is personal: each user uses their own code, never gives it to anyone else and never enters it in a shared place. The code is valid for about a year. Long runs may have to wait for the plan's usage limit to reset.

## 5. Creating a research run

Go to **New idea**.

1. **Idea.** Write a few lines, then click the AI write-and-debate button. The AI rewrites it as a complete brief (problem, hypothesis, data, method and baselines, contribution, scope), runs a 4-role debate (proposer, reviewer, journal editor, implementer), finalises the brief and asks about what is still unclear. Answer and debate one more round, or use the version to fill in the idea. Anything the AI guessed is marked as an assumption to confirm.
2. **Base papers.** Drag in PDF/DOCX/MD files of papers you want to build on, or paste DOIs, links or titles. With none, the agent picks the 3–5 closest papers itself and says so.
3. **Journal.** Type the target journal (suggestions from OpenAlex) and backup journals. Article type, format and style follow this journal.
4. **Field & format.** Follow the journal by default.
5. **Experiment machines.** The bonrs server is always available. Add your own GPU machines if you have them (section 8).
6. **Model, cost, approval wait.** Pick the model from the list. The per-stage budget cap is suggested from what stages have cost on this server; the agent only spends what it uses and a stage that hits the cap stops. Turn on auto-continue and set hours and minutes; with it off the agent always waits for you.

On the right is the 10-stage route: turn on the switch at a stage to make the agent wait for you after it. Then create the run.

## 6. Following and approving

### 6.1. Overview

The run page shows the 10-stage progress bar, costs, review scores over the rounds and recent activity. Click a stage in the progress bar to open its **stage page**: every attempt of that stage (the agent's step-by-step trace, cost, time), the timeline (gates, comments) and saved checkpoints with a button to view the changes.

### 6.2. Approval gates

When the agent stops, a yellow banner appears:

- **Approve and continue** (optionally with a comment that goes to the next stage).
- **Redo this stage with my comment.**
- **Pause here.** Click Continue any time to resume.

At the hypothesis gate you see each hypothesis with its chance of success, chance of acceptance if it succeeds, effort and risks. Choose one to pursue, or stop if none is worth it. This gate always waits for you.

### 6.3. Files & drafts

See every output (literature review, journal rules, code and results, PDF/DOCX draft). Select a passage to comment on it, or click Edit to change it directly. Upload paywalled PDFs when the agent asks for them.

### 6.4. Review & hand-off

The one-page editor letter (read it first), the review rounds with each seat's score, the response letter, the submission checklist, the cover letter and the AI-use declaration.

### 6.5. Comments

Open comments go to the agent in the next revision round, and are later distilled into lessons for future runs.

### 6.6. History

Every stage, review round, edit and upload is a checkpoint.

- **One checkpoint:** click it to see which files changed (added/edited/deleted, +/− lines); click a file to see each line, green added and red removed.
- **Compare two checkpoints:** click the older one (A), then the newer one (B).

### 6.7. Run settings

Change the idea, journal, field, review rounds, gates, machines, model and budget with a form. The save bar at the bottom tells you when there are unsaved changes. YAML users can edit `bonrs.yaml` directly under Advanced.

### 6.8. Download

The download button at the top saves the whole run (zip, with git history).

## 7. Running in the background

All work runs on the server: closing the browser or turning off your own computer has no effect. If the server restarts (update, power cut), runs in progress continue from the unfinished stage (up to 3 times in a row). Experiments on SSH machines run under `nohup`, so they are not interrupted either.

## 8. Experiment machines

### 8.1. The bonrs server

Always available, nothing to install. Each run has its own `exp/` folder. The automatic environment option creates a private Python environment (`.venv`) and installs the `requirements.txt` the agent writes.

### 8.2. Adding your own GPU machine over SSH

Go to **Machines** and add your own machine:

1. Enter `user@address` (and the port if it is not 22), exactly as you would `ssh` into it.
2. Sign in to that machine and run, once, the command the page shows. It adds the SSH key of **your bonrs account** to `~/.ssh/authorized_keys`. To revoke access, delete the `bonrs-user-…` line from that file.
3. Test the connection: bonrs reads CPU, RAM, GPUs, Python and disk, then suggests a machine name, a folder (`~/bonrs-runs/<run name>`) and how to prepare the environment (automatic, existing conda, or your own command).
4. Save the machine, then select it when you create a run or on the Settings tab.

The bonrs server must be able to reach that machine over SSH (same LAN, same VPN such as WireGuard/Tailscale, or an open SSH port).

### 8.3. Several machines

Select several machines for a run: the agent sends each independent job (seed, fold, ablation, baseline) to the least busy machine, measured on GPU/CPU at the moment it sends. A single training job is never split across machines.

## 9. Knowledge base

Rules and experience the agent loads into every run, from general to specific: general, by field, by article type, by journal, accumulated experience, personal.

- **Browse & edit:** read and edit skills (members edit their own personal skills).
- **Contribute documents:** send PDF/DOCX/links; the agent turns them into draft skills.
- **Pending review:** admins read, edit, approve or reject draft skills.
- **Automatic sources:** admins add, disable and delete sources and pick a schedule (daily/weekly/monthly/off). Unchanged pages are skipped at no cost. The schedule needs the shared key.

## 10. Appearance

At the bottom of the sidebar (or on the Account page on phones): choose **VI / EN** to switch the interface language and **Light / Dark** to switch the colour mode. The choice is saved in your browser. Content written by you and the agent (ideas, drafts, logs) stays in its original language.

## 11. Troubleshooting

| Symptom | What to do |
|---|---|
| A run shows "Failed" | Open the stage page or the agent log tab to see why, fix the settings if needed, then click Continue |
| "no Anthropic API key configured" | Enter the shared key under Admin, or connect your own Claude on the Account page |
| SSH machine test says login was refused | Run the step 2 command again, as the same user you entered in step 1 |
| SSH machine test says it cannot reach the machine | Check that it is on, the SSH port, and the VPN/network between the two machines |
| A stage stopped at the budget cap | Raise the cap on the Settings tab, then click Continue |
| The page does not open | `docker compose ps` and `docker compose logs --tail 100` on the server |
| Forgotten password | An admin resets it under Admin → Users |

## 12. Security and data

- In Docker, each user's agent runs as its own operating-system account: it cannot read other users' data, SSH keys or runs.
- API keys never enter the agent's process; the server adds them when forwarding. A Pro/Max plan code stays inside that user's own sandbox.
- Every user has their own SSH key for experiment machines.
- Your data stays on your server, in `./data`.

## 13. Responsible use of AI

bonrs records the origin of everything the agent writes and drafts an **AI-use declaration** following the publisher's policy at the Submission stage. Read it carefully, check the numbers and citations, and take responsibility for the paper before you submit. bonrs has no feature to hide the use of AI, and will not add one.

## 14. License

bonrs is released under the **MIT** license (`LICENSE`): you may use, modify and distribute it, including commercially, as long as you keep the copyright notice. Third-party components and their licenses are listed in `THIRD_PARTY_NOTICES.md`. Claude Code is published by Anthropic under Anthropic's own terms.
