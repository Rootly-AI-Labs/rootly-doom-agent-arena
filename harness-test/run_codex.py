#!/usr/bin/env python3

from pathlib import Path
import subprocess


WORKSPACE = Path(__file__).resolve().parent
OUTPUT_FILE = WORKSPACE / "toronto.txt"
PROMPT = (
    "Tell me about Toronto in exactly 3 non-empty lines. "
    "Use one concise factual sentence per line, with no heading or bullet points."
)


def main() -> None:
    result = subprocess.run(
        [
            "codex",
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--output-last-message",
            str(OUTPUT_FILE),
            PROMPT,
        ],
        cwd=WORKSPACE,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Codex failed with exit code {result.returncode}\n{result.stderr}"
        )

    if not OUTPUT_FILE.is_file():
        raise RuntimeError(f"Codex did not create {OUTPUT_FILE}")

    lines = [line for line in OUTPUT_FILE.read_text().splitlines() if line.strip()]
    if len(lines) != 3:
        raise RuntimeError(
            f"Expected exactly 3 non-empty lines, but Codex returned {len(lines)}"
        )

    print(f"Saved Codex response to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
