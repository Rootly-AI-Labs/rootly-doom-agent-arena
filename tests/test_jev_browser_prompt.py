"""Exercise the actual browser copy-prompt function without starting a match."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("mode", ["jev_only", "jev_hybrid"])
@pytest.mark.parametrize("participant", ["player_1", "player_2"])
def test_copied_jev_prompt_matches_current_tools(mode, participant):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for browser prompt regression")
    html = (Path(__file__).resolve().parents[1] / "src/index.html").read_text(encoding="utf-8")
    start = html.index("function buildJevPlayerPrompt(")
    end = html.index("function baseDuelPromptForParticipant(", start)
    script = ("function selectedNumberValue() { return 25; }\n" + html[start:end]
              + f"console.log(JSON.stringify(buildJevPlayerPrompt({json.dumps(participant)}, {json.dumps(mode)})));")
    completed = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True)
    prompt = json.loads(completed.stdout)
    assert "strategic_directive" not in prompt
    assert "directive" not in prompt.lower()
    assert "only max_run_ms=45000" in prompt
    assert "shared game prompt" in prompt
    assert "25" in prompt
    assert participant in prompt
