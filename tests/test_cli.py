from deeplens.cli import main, parser


def test_cli_parses_research() -> None:
    args = parser().parse_args(
        ["research", "Is policy effective?", "--non-interactive", "--max-perspectives", "3"]
    )
    assert args.question == "Is policy effective?"
    assert args.max_perspectives == 3


def test_config_command(capsys) -> None:
    assert main(["config"]) == 0
    assert "model=" in capsys.readouterr().out
