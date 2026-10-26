"""Offline tests: python3 test_bonrs.py"""
import json, os, tempfile, unittest
from pathlib import Path
from unittest import mock
import yaml
os.environ["BONRS_DATA"] = tempfile.mkdtemp(prefix="bonrs-test-")  # never touch the real data folder
from bonrs import audit, registry, kb, journal, lit, pipeline

PRE = "\\newcommand{\\ph}[1]{#1}\\newcommand{\\phm}[2][]{#2}\\newcommand{\\prov}[2]{#2}\n"


def make_run(tmp: Path, tex: str, claims=None, bib='@article{smith2020,\n title={Deep learning for batteries},\n doi={10.1/x},\n}\n'):
    (tmp / "exp/results").mkdir(parents=True); (tmp / "paper").mkdir(); (tmp / "lit/uploads").mkdir(parents=True)
    (tmp / "exp/results/main.json").write_text(json.dumps({"acc": 0.873, "runs": [{"rmse": 1.25}]}))
    registry.build(tmp)
    (tmp / "paper/main.tex").write_text(PRE + tex); (tmp / "paper/refs.bib").write_text(bib)
    (tmp / "paper/main.log").write_text("ok")
    (tmp / "lit/papers.jsonl").write_text(json.dumps({"title": "Deep learning for batteries"}))
    if claims is not None: (tmp / "paper/claims.yaml").write_text(yaml.safe_dump(claims))
    return tmp


class Audit(unittest.TestCase):
    def run_audit(self, tex, **kw):
        with tempfile.TemporaryDirectory() as d: return audit.audit(make_run(Path(d), tex, **kw), final=kw.pop("final", False) if False else False)

    def test_clean(self):
        tex = "\\section{Results}\nAccuracy reached \\phm[exp/results/main.json:acc]{87.3}\\% \\citep{smith2020}.\n"
        self.assertEqual(self.run_audit(tex), [])

    def test_phm_mismatch(self):
        f = self.run_audit("\\section{Results}\nAcc \\phm[exp/results/main.json:acc]{91.0}.\n")
        self.assertTrue(any("!=" in x for x in f), f)

    def test_unregistered_number_in_results(self):
        f = self.run_audit("\\section{Results}\nRMSE dropped to 3.47 on the test set.\n")
        self.assertTrue(any("3.47" in x for x in f), f)

    def test_registered_bare_number_ok(self):
        f = self.run_audit("\\section{Results}\nRMSE was 1.25 on the test set.\n")
        self.assertFalse(any("1.25" in x for x in f), f)

    def test_missing_cite_and_overclaim(self):
        f = self.run_audit("\\section{Introduction}\nOur novel method is state-of-the-art \\citep{ghost2021}.\n")
        self.assertTrue(any("ghost2021" in x for x in f)); self.assertTrue(any("overclaim" in x for x in f))

    def test_hallucinated_bib(self):
        bib = '@article{fake,\n title={A paper nobody wrote},\n doi={10.9/y},\n}\n'
        f = self.run_audit("\\section{Intro}\nText \\citep{fake}.\n", bib=bib)
        self.assertTrue(any("possible hallucination" in x for x in f), f)

    def test_claim_strength(self):
        tex = "\\section{Discussion}\n\\prov{c1}{The model shows better generalisation.}\n"
        f = self.run_audit(tex, claims=[{"id": "c1", "text": "The model shows better generalisation.", "evidence": "exp/results/main.json:acc", "strength": "suggests"}])
        self.assertTrue(any("stronger than allowed" in x for x in f), f)

    def test_prov_without_claim(self):
        f = self.run_audit("\\section{Discussion}\n\\prov{c9}{Something.}\n", claims=[])
        self.assertTrue(any("c9" in x for x in f), f)


class Registry(unittest.TestCase):
    def test_matches(self):
        v = [0.873, 1.25]
        self.assertTrue(registry.matches("87.3", v)); self.assertTrue(registry.matches("1.3", v)); self.assertFalse(registry.matches("2.5", v))


class KB(unittest.TestCase):
    def test_select_tiers(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            def w(rel, meta, body):
                p = r / rel; p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("---\n" + yaml.safe_dump(meta) + "---\n" + body)
            w("00-general/a.md", {"level": "general"}, "GENERAL")
            w("10-domain/ml/x.md", {"level": "domain", "domain": "ml"}, "ML-RULE")
            w("10-domain/biomed/y.md", {"level": "domain", "domain": "biomed"}, "BIO-RULE")
            w("00-general/draft.md", {"level": "general", "status": "draft"}, "DRAFT")
            w("30-journal/applied-energy.md", {"level": "journal", "journal": "Applied Energy"}, "AE-RULE")
            w("40-experience/old.md", {"level": "experience", "added": "2020-01-01"}, "OLD-LESSON")
            out = kb.select({"domain": "ml", "target_journal": "Applied Energy"}, root=r)
            for s in ("GENERAL", "ML-RULE", "AE-RULE", "OLD-LESSON"): self.assertIn(s, out)
            for s in ("BIO-RULE", "DRAFT"): self.assertNotIn(s, out)
            self.assertLess(out.index("AE-RULE"), out.index("OLD-LESSON"))

    def test_learn_writes_draft_proposal(self):
        with tempfile.TemporaryDirectory() as d:
            p = kb.learn("Always state the baseline budget.", out=Path(d), journal=None)
            meta, body = kb.parse(p)
            self.assertEqual(meta["level"], "experience"); self.assertEqual(meta["status"], "draft"); self.assertIn("baseline", body)


class Journal(unittest.TestCase):
    def test_shape(self):
        txt = "Abstract\n" + "We study things. " * 40 + "\n\n1. Introduction\nText — here. Moreover we delve.\n2. Methods\nFig. 1 and Table 2.\nReferences\n[1] A. (2020).\n"
        s = journal.shape(txt)
        self.assertIn("Introduction", s["sections"]); self.assertEqual(s["n_figures"], 1); self.assertGreater(s["markers"]["delve"], 0)


class Lit(unittest.TestCase):
    def test_dedupe(self):
        p = {"id": "a", "title": "Same Title", "pdf": None, "doi": None}
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(lit, "arxiv", return_value=[dict(p, id="arxiv:1")]), mock.patch.object(lit, "openalex", return_value=[dict(p, id="W1")]), \
             mock.patch.object(lit, "crossref", return_value=[dict(p, id="doi:1", title="Other")]), mock.patch.object(lit, "s2_recommend", return_value=[]):
            out = Path(lit.search(Path(d), ["q"])).read_text().splitlines()
            self.assertEqual(len(out), 2)


class Pipeline(unittest.TestCase):
    def test_new_run_and_gate(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pipeline, "RUNS", Path(d)):
            rd = pipeline.new_run("test idea", "Applied Energy", "t1")
            self.assertTrue((rd / ".git").exists()); cfg = yaml.safe_load((rd / "bonrs.yaml").read_text())
            self.assertEqual(cfg["model"], "claude-opus-5-5")
            pipeline._open_gate(rd, cfg, "00_scope")
            with self.assertRaises(SystemExit) as e: pipeline._gate_check(rd, cfg, {})
            self.assertEqual(e.exception.code, pipeline.WAITING)
            pipeline.approve("t1", "guide", "focus on cold climates")
            self.assertIn("cold climates", pipeline._gate_check(rd, cfg, {}))
            self.assertFalse((rd / "hitl/waiting.json").exists())


    def test_gate_timeout_and_double_answer(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pipeline, "RUNS", Path(d)):
            rd = pipeline.new_run("idea", "J", "t2"); cfg = yaml.safe_load((rd / "bonrs.yaml").read_text())
            pipeline._open_gate(rd, cfg, "00_scope"); self.assertFalse(pipeline.gate_due(rd))
            (rd / "hitl/waiting.json").write_text(json.dumps({"gate": "after_scope", "stage": "00_scope", "since": "2000-01-01T00:00:00"}))
            self.assertFalse(pipeline.gate_due(rd))  # go/no-go on hypotheses never auto-continues
            (rd / "hitl/waiting.json").write_text(json.dumps({"gate": "after_plan", "stage": "03_plan", "since": "2000-01-01T00:00:00"}))
            self.assertTrue(pipeline.gate_due(rd))
            cfg["gate_timeout_hours"] = 0; (rd / "bonrs.yaml").write_text(yaml.safe_dump(cfg)); self.assertFalse(pipeline.gate_due(rd))  # 0 = wait forever
            pipeline.approve("t2", "approve"); self.assertFalse(pipeline.gate_due(rd))
            with self.assertRaises(FileExistsError): pipeline.approve("t2", "reject")

    def test_safe_path_sibling_prefix(self):
        from fastapi import HTTPException
        from bonrs.web import safe_path
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "foo").mkdir(); (Path(d) / "foo2").mkdir(); (Path(d) / "foo/x").symlink_to(Path(d) / "foo2")
            with self.assertRaises(HTTPException): safe_path(Path(d) / "foo", "x/secret.md")
            self.assertTrue(str(safe_path(Path(d) / "foo", "a.md")).endswith("a.md"))

    def test_done_review_not_rerun_unless_forced(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pipeline, "RUNS", Path(d)):
            rd = pipeline.new_run("idea", "J", "t3"); st = json.loads((rd / "state.json").read_text())
            st["done"] = list(pipeline.ORDER); (rd / "state.json").write_text(json.dumps(st))
            (rd / "reviews/round_1.json").write_text(json.dumps({"score": 9, "decision": "accept", "open_major": 0}))
            calls = []
            def fake(rd_, stage, cfg, extra=""):
                calls.append(stage)
                if stage == "06_review":
                    k = len(list((rd_ / "reviews").glob("round_*.json"))) + 1
                    (rd_ / f"reviews/round_{k}.json").write_text(json.dumps({"score": 9, "decision": "accept", "open_major": 0}))
                return {"total_cost_usd": 0, "result": "ok"}
            with mock.patch.object(pipeline, "run_stage", fake):
                pipeline.run("t3", "06_review"); self.assertEqual(calls, [])  # resuming a finished run must not buy another review round
                pipeline.run("t3", "06_review", "06_review", force=True); self.assertEqual(calls, ["06_review"])

class Security(unittest.TestCase):
    def test_safeio_refuses_links_and_fifos(self):
        import os
        from bonrs import safeio
        with tempfile.TemporaryDirectory() as d:
            base, out = Path(d) / "run", Path(d) / "secret"; base.mkdir(); out.mkdir(); (out / "db").write_text("SECRET")
            (base / "lnk").symlink_to(out); (base / "f.json").symlink_to(out / "db"); os.mkfifo(base / "pipe")
            os.link(out / "db", base / "hard")
            for rel in ("lnk/db", "f.json", "pipe", "hard"): self.assertIsNone(safeio.read_text(base, rel), rel)
            with self.assertRaises(OSError): safeio.write_text(base, "lnk/x", "no")
            with self.assertRaises(OSError): safeio.write_text(base, "f.json", "no")
            self.assertEqual((out / "db").read_text(), "SECRET"); self.assertFalse((out / "x").exists())
            with self.assertRaises(ValueError): safeio.read_bytes(base, "../secret/db")
            safeio.write_text(base, "a/b.txt", "ok"); self.assertEqual(safeio.read_text(base, "a/b.txt"), "ok")
            safeio.unlink(base, "lnk"); self.assertTrue(out.exists())  # removing a planted link never touches its target
            self.assertEqual({r for r, _, _ in safeio.listing(base)}, {"a/b.txt", "hard"})

    def test_kb_target_path_cannot_escape(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            for bad in ("../00-general", "/app/prompts", "1/../../x", "", None, True):
                with self.assertRaises(ValueError): kb.target_path({"level": "user", "user_id": bad}, "x.md", r)
            with self.assertRaises(ValueError): kb.target_path({"level": "general"}, "../x.md", r)
            self.assertEqual(kb.target_path({"level": "user", "user_id": 7}, "x.md", r), r / "50-user/7/x.md")
            self.assertEqual(kb.target_path({"level": "domain", "domain": "../../etc"}, "x.md", r), r / "10-domain/etc/x.md")

    def test_queue_draft_sets_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            n = kb.queue_draft({"level": "user", "user_id": "../00-general", "status": "active", "submitted_by": "boss@x", "confidence": "high", "evil": 1},
                               "body", "../../x", "m@x", 5, "promote", r)
            meta, _ = kb.parse(r / "inbox/drafts" / n)
            self.assertEqual((meta["status"], meta["submitted_by"], meta["user_id"], meta["origin"]), ("draft", "m@x", 5, "promote"))
            self.assertNotIn("evil", meta); self.assertEqual(meta["confidence"], 0.5)
            self.assertEqual(kb.approve(n, root=r), r / "50-user/5" / n)

    def test_bad_frontmatter_does_not_break_kb(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d); (r / "00-general").mkdir(); (r / "50-user/9").mkdir(parents=True)
            (r / "00-general/ok.md").write_text("---\nseverity: x\nconfidence: [1]\n---\nGOOD")
            (r / "50-user/9/bad.md").write_text("---\n- a list\n---\nBAD")
            self.assertIn("GOOD", kb.select({"user_id": "9"}, root=r)); self.assertEqual(len(kb.index(r)), 2)

    def test_job_env_has_no_server_secrets(self):
        import os
        from bonrs import sandbox
        with mock.patch.dict(os.environ, {"BONRS_ADMIN_PASSWORD": "pw", "BONRS_ADMIN_EMAIL": "a@x", "ANTHROPIC_API_KEY": "sk-real", "AWS_SECRET_ACCESS_KEY": "s"}):
            env = sandbox.base_env(3)
        for k in ("BONRS_ADMIN_PASSWORD", "BONRS_ADMIN_EMAIL", "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY"): self.assertNotIn(k, env)
        self.assertIn("/tenants/20003/", env["HOME"])

    def test_remote_host_fields_validated(self):
        from bonrs import remote
        for bad in ({"type": "ssh", "ssh": "-oProxyCommand=touch /tmp/x"}, {"type": "ssh", "ssh": "u@h", "workdir": "x; rm -rf ~"},
                    {"type": "slurm", "ssh": "u@h", "sbatch": {"partition": "gpu --wrap=evil"}}, {"type": "docker"}):
            with self.assertRaises(ValueError): remote.check_host(bad)
        self.assertEqual(remote.check_host({"type": "ssh", "ssh": "me@gpu.lab.org", "workdir": "~/bonrs"})["ssh"], "me@gpu.lab.org")

    def test_session_token_versioned(self):
        from bonrs import db
        with mock.patch.object(db, "secret", lambda: b"k"):
            t = db.sign(4, 2); self.assertEqual(db.verify(t), (4, 2))
            for bad in (t[:-1] + ("0" if t[-1] != "0" else "1"), t.replace("4.2.", "5.2.", 1), "4.1.9999999999.x", "é.é.é.é", None, "a.b"):
                self.assertIsNone(db.verify(bad))
            self.assertFalse(db.check_pw("x", "!"))


class Hosts(unittest.TestCase):
    def test_host_fields_port_gpus_and_defaults(self):
        from bonrs import remote
        h = remote.check_host({"type": "ssh", "ssh": "u@gpu", "port": "2222", "gpus": "0, 1"})
        self.assertEqual((h["port"], h["gpus"], h["workdir"], h["setup"]), (2222, "0,1", "~/bonrs-runs", "auto"))
        for bad in ({"type": "ssh", "ssh": "u@h", "port": "70000"}, {"type": "ssh", "ssh": "u@h", "gpus": "0;reboot"}):
            with self.assertRaises(ValueError): remote.check_host(bad)
        self.assertIn("-p", remote.ssh_opts(h)); self.assertIn("CUDA_VISIBLE_DEVICES=0,1", remote.setup_cmd(h))
        self.assertIn("requirements.txt", remote.setup_cmd({"setup": "auto"})); self.assertEqual(remote.setup_cmd({"setup": "true"}), "true")

    def test_probe_parse_and_run_folders(self):
        from bonrs import remote
        i = remote.probe_info("BONRS_OK\nHOST=lab1\nCPU=32\nPY=Python 3.11.4\nGPU=0, NVIDIA A100, 81920, 1024, 7\nGPU=garbage\nEVIL=1")
        self.assertEqual((i["host"], i["cpu"], len(i["gpus"]), i["gpus"][0]["name"]), ("lab1", "32", 1, "NVIDIA A100"))
        self.assertNotIn("evil", i)
        with tempfile.TemporaryDirectory() as t:
            rd = Path(t) / "run-a"; (rd / "exp/logs").mkdir(parents=True)
            cfg = {"remote": {"hosts": [{"name": "a", "type": "ssh", "ssh": "u@a"}, {"name": "b", "type": "ssh", "ssh": "u@b", "workdir": "/scratch/me"}]}}
            self.assertEqual(remote._wd(remote.host(cfg, "b"), rd), "/scratch/me/run-a")  # one folder per run
            (rd / "exp/logs/seed1.host").write_text("b")
            self.assertEqual(remote.host(cfg, None, rd, "seed1")["name"], "b")  # tail/pull find the host a tag was sent to
            self.assertEqual(remote.host(cfg, None, rd, "other")["name"], "a")

    def test_new_run_config_complete(self):
        rd = pipeline.new_run("idea", "J", "cfg-check")
        c = yaml.safe_load((rd / "bonrs.yaml").read_text())
        self.assertEqual((c["paper_format"], c["language"], c["article_type"]), ("auto", "en", "auto"))
        self.assertEqual(c["remote"]["hosts"][0]["setup"], "auto")

    def test_subscription_token_goes_only_to_its_owner_job(self):
        from bonrs import web, db
        a = db.ex("INSERT INTO users(email,pw,role,created,oauth_token) VALUES ('sub@x','!','member',0,'sk-ant-oat01-abcdefghijklmnop')")
        b = db.ex("INSERT INTO users(email,pw,role,created) VALUES ('nosub@x','!','member',0)")
        with mock.patch.dict(os.environ, {"BONRS_SELF_URL": "http://127.0.0.1:1"}):
            ea, eb = web._job_env({"owner": a}), web._job_env({"owner": b})
        self.assertEqual(ea["CLAUDE_CODE_OAUTH_TOKEN"], "sk-ant-oat01-abcdefghijklmnop")
        self.assertNotIn("ANTHROPIC_API_KEY", ea); self.assertNotIn("ANTHROPIC_BASE_URL", ea)  # an API key would override the subscription
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", eb); self.assertTrue(eb["ANTHROPIC_API_KEY"].startswith("bonrs-job-"))
        self.assertIn(a, web._OAUTH_OWNERS); self.assertNotIn(b, web._OAUTH_OWNERS)


class Assist(unittest.TestCase):
    def test_budget_hint_from_past_steps(self):
        from bonrs import web
        pts = [("01_literature", c) for c in (2.0, 3.0, 4.0, 5.0, 6.0, 8.0)]
        with mock.patch.object(web, "_past_costs", lambda: ({"claude-opus-5-5": pts}, {"claude-opus-5-5": [50.0]})):
            h = web.budget_hint("claude-opus-5-5", {"id": 1})
            self.assertEqual((h["recommended"], h["basis"], h["est_run_total"]), (15, "model", 50.0))  # 1.5 x p90 = 12 -> rounded up to 15
            self.assertEqual(web.budget_hint("other-model", {"id": 1})["basis"], "all")
        with mock.patch.object(web, "_past_costs", lambda: ({}, {})):
            self.assertEqual(web.budget_hint("", {"id": 1})["basis"], "default")

    def test_idea_assistant_parses_agent_answer(self):
        from bonrs import web
        with mock.patch.dict(os.environ, {"BONRS_CLAUDE_BIN": str(Path(__file__).parent / "tools/mock_claude"), "BONRS_MOCK_DELAY": "0"}):
            web._ASSIST["t1"] = {"owner": 5, "status": "running", "t": 0}
            web._assist_run("t1", 5, {"idea": "PINN cho SOH pin", "journal": "J", "previous": "", "feedback": ""}, "claude-opus-5-5")
        a = web._ASSIST["t1"]
        self.assertEqual(a["status"], "done", a.get("error")); self.assertEqual(len(a["result"]["debate"]), 4)
        self.assertIn("PINN cho SOH pin", a["result"]["final"]); self.assertTrue(a["result"]["questions"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
