"""Unit tests for HireHands. Stdlib only; no Hermes install needed."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "hirehands" / "scripts" / "hirehands.py"
EXAMPLES = ROOT / "examples"

FAKE_ENV = {
    "profile_home": "/tmp/none", "provider": "anthropic", "current_model": "claude-opus-5-5",
    "billing": "subscription",
    "available_models": ["claude-fable-5-2", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
    "picks": {"brain": "claude-fable-5-2", "heavy": "claude-opus-5-5",
              "standard": "claude-sonnet-5-5", "light": "claude-haiku-5-5"},
}


def load_module(tmp: Path):
    os.environ["HERMES_ROOT"] = str(tmp / "root")
    os.environ["HIREHANDS_TEAMS_DIR"] = str(tmp / "teams")
    os.environ.pop("HERMES_HOME", None)
    spec = importlib.util.spec_from_file_location("hirehands_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class HireHandsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        (self.tmp / "root").mkdir()
        self.hh = load_module(self.tmp)
        self.hh.detect = lambda: dict(FAKE_ENV)

    def tearDown(self):
        self._tmp.cleanup()

    def test_slugify_handles_turkish_and_symbols(self):
        self.assertEqual(self.hh.slugify("Güvenlik Denetimi: Şifre!"), "guvenlik-denetimi-sifre")
        self.assertEqual(self.hh.slugify("???"), "team")

    def test_picks_follow_ladder_and_skip_unlisted_models(self):
        picks = self.hh._picks("anthropic", ["claude-opus-5-5", "claude-haiku-5-5"], "claude-opus-5-5")
        self.assertEqual(picks["brain"], "claude-opus-5-5")  # fable not listed, falls to opus
        self.assertEqual(picks["light"], "claude-haiku-5-5")
        unknown = self.hh._picks("some-provider", [], "local-model")
        self.assertEqual(set(unknown.values()), {"local-model"})

    def test_load_team_assigns_profiles_tiers_and_models(self):
        team = self.hh.load_team(EXAMPLES / "security-audit.team.json")
        by_key = {m["key"]: m for m in team["members"]}
        self.assertEqual(by_key["lead"]["tier"], "brain")
        self.assertEqual(by_key["lead"]["model"], "claude-fable-5-2")
        self.assertEqual(by_key["sec"]["model"], "claude-opus-5-5")
        self.assertEqual(by_key["deps"]["model"], "claude-haiku-5-5")
        self.assertEqual(by_key["sec"]["profile"], "security-audit-sec")

    def test_setup_screen_models_override_tier_picks(self):
        src = json.loads((EXAMPLES / "security-audit.team.json").read_text())
        src["models"] = {"brain": "claude-opus-5-5", "light": "claude-sonnet-5-5"}
        path = self.tmp / "team.json"
        path.write_text(json.dumps(src))
        by_key = {m["key"]: m for m in self.hh.load_team(path)["members"]}
        self.assertEqual(by_key["lead"]["model"], "claude-opus-5-5")
        self.assertEqual(by_key["deps"]["model"], "claude-sonnet-5-5")
        self.assertEqual(by_key["sec"]["model"], "claude-opus-5-5")

    def test_brain_soul_lists_only_hired_crew_and_forbids_coding(self):
        team = self.hh.load_team(EXAMPLES / "security-audit.team.json")
        brain = team["members"][0]
        soul = self.hh.brain_soul(team, brain, crew={"sec"})
        self.assertIn("security-audit-sec", soul)
        self.assertNotIn("security-audit-deps", soul)
        self.assertIn("NEVER read the codebase", soul)
        self.assertIn("message_agent", soul)

    def test_empty_selection_creates_only_a_lead_in_dry_run(self):
        from argparse import Namespace
        from contextlib import redirect_stdout
        from io import StringIO
        out = StringIO()
        with redirect_stdout(out):
            self.hh.cmd_hire(Namespace(team=EXAMPLES / "security-audit.team.json", only="", dry_run=True))
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertIn("security-audit-lead", out.getvalue())

    def test_unavailable_model_is_rejected(self):
        src = json.loads((EXAMPLES / "security-audit.team.json").read_text())
        src["models"] = {"brain": "not-in-catalog"}
        path = self.tmp / "team.json"
        path.write_text(json.dumps(src))
        with self.assertRaisesRegex(SystemExit, "not listed"):
            self.hh.load_team(path)

    def test_worker_soul_points_at_lead_and_brief_format(self):
        team = self.hh.load_team(EXAMPLES / "security-audit.team.json")
        soul = self.hh.worker_soul(team, team["members"][1])
        self.assertIn("`security-audit-lead`", soul)
        self.assertIn("BRIEF ·", soul)

    def test_board_embeds_team_json(self):
        team = self.hh.load_team(EXAMPLES / "security-audit.team.json")
        page = self.hh.write_board(team).read_text()
        self.assertNotIn("/*__DATA_JSON__*/", page)
        self.assertIn('"slug": "security-audit"', page)

    def test_setup_screen_embeds_job_and_catalog(self):
        self.hh.models = lambda: {"active_provider": "anthropic", "current_model": "claude-opus-5-5",
                                  "providers": {"anthropic": {"billing": "subscription", "models": [
                                      {"id": "claude-fable-5-2", "hint": "x"}], "picks": FAKE_ENV["picks"]}},
                                  "tiers": [{"id": "brain", "label": "Brain", "hint": "h"}]}

        class Args:
            job = str(EXAMPLES / "security-audit.job.json")

        self.hh.cmd_setup(Args())
        page = (self.tmp / "teams" / "security-audit" / "setup.html").read_text()
        self.assertIn("inferred_from", page)
        self.assertIn("claude-fable-5-2", page)


if __name__ == "__main__":
    unittest.main()
