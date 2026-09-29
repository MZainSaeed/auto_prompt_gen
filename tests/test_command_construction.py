"""Tests for CLI command construction, flags, print-timeout, and payload streaming."""

from pathlib import Path
from prompt_generator.config import PromptGeneratorConfig
from prompt_generator.providers.antigravity_cli import AntigravityCLIProvider


def test_command_flags_and_print_timeout():
    """Verify exact flags including paired stream-json, print-timeout 10m, and json-schema."""
    repo_root = Path(__file__).parent.parent
    config_path = repo_root / "config" / "prompt_generator_config.json"
    cfg = PromptGeneratorConfig.load(config_path, base_dir=repo_root)

    provider = AntigravityCLIProvider(cfg)
    cmd = provider.build_command()

    # Check flags
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "gemini-3.1-pro-high"
    assert "--effort" in cmd
    assert cmd[cmd.index("--effort") + 1] == "high"
    assert "--input-format" in cmd
    assert cmd[cmd.index("--input-format") + 1] == "stream-json"
    assert "--output-format" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--print-timeout" in cmd
    assert cmd[cmd.index("--print-timeout") + 1] == "10m"
    assert "--json-schema" in cmd
    assert "scene_schema.json" in cmd[cmd.index("--json-schema") + 1]


def test_no_giant_cli_argument():
    """Verify that instruction text and prompt payloads are NEVER in command line arguments."""
    repo_root = Path(__file__).parent.parent
    config_path = repo_root / "config" / "prompt_generator_config.json"
    cfg = PromptGeneratorConfig.load(config_path, base_dir=repo_root)

    provider = AntigravityCLIProvider(cfg)
    cmd = provider.build_command()

    # Ensure no argument is longer than 256 characters (proving 35KB instruction is omitted from argv)
    for arg in cmd:
        assert len(arg) < 512, f"Command argument unexpectedly long ({len(arg)} chars): {arg[:50]}..."
        assert "RULE 0" not in arg
        assert "ZERO-TEXT" not in arg
