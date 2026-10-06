from pathlib import Path

from src.email_send_cli import main as cli_main


ROOT = Path(__file__).resolve().parent.parent


def test_primary_windows_launcher_runs_real_report_batch() -> None:
    text = (ROOT / "run_windows.bat").read_text(encoding="utf-8")
    assert "-m src.batch_processor" in text
    assert "-m src.main" not in text
    assert 'cd /d "%~dp0"' in text


def test_primary_mac_launcher_runs_real_report_batch_with_relative_root() -> None:
    text = (ROOT / "run_mac.command").read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh")
    assert "-m src.batch_processor" in text
    assert "-m src.main" not in text
    assert 'cd "$SCRIPT_DIR"' in text


def test_email_launchers_use_project_relative_paths_and_separate_modes() -> None:
    authorize = (ROOT / "Authorize Google Email.bat").read_text(encoding="utf-8")
    test = (ROOT / "Send Test Email.bat").read_text(encoding="utf-8")
    assert 'cd /d "%~dp0"' in authorize and "--authorize" in authorize
    assert 'cd /d "%~dp0"' in test and "--test-send" in test
    assert "google_credentials.json" in authorize
    assert "google_token.json" in test
    assert "is_valid_email" in test and "missing_test_recipient" in test
    assert "--live-send" not in authorize + test


def test_mac_test_launcher_blocks_missing_or_invalid_test_recipient() -> None:
    text = (ROOT / "Send Test Email.command").read_text(encoding="utf-8")
    assert 'cd "$SCRIPT_DIR"' in text
    assert "google_token.json" in text
    assert "is_valid_email" in text
    assert "--test-send" in text and "--live-send" not in text


def test_test_send_cli_rejects_invalid_recipient_without_authentication(
    test_workspace: Path, monkeypatch, capsys,
) -> None:
    from unittest.mock import Mock

    monkeypatch.setattr("src.email_send_cli._load_settings", lambda _: {
        "live_send_enabled": False,
        "test_recipient": "",
        "google_credentials_path": "credentials.json",
        "google_token_path": "token.json",
    })
    auth = Mock(side_effect=AssertionError("invalid recipient must block auth"))
    monkeypatch.setattr("src.email_send_cli.get_gmail_service", auth)
    assert cli_main(["--test-send", "--project-root", str(test_workspace)]) == 2
    auth.assert_not_called()
    assert "valid test_recipient" in capsys.readouterr().out


def test_authorization_cli_never_loads_plans_or_sends_and_preserves_live_setting(
    test_workspace: Path, monkeypatch, capsys,
) -> None:
    from unittest.mock import Mock

    service = Mock()
    monkeypatch.setattr("src.email_send_cli._load_settings", lambda _: {
        "live_send_enabled": False,
        "google_credentials_path": "credentials.json",
        "google_token_path": "config/google_token.json",
    })
    auth = Mock(return_value=service)
    monkeypatch.setattr("src.email_send_cli.get_gmail_service", auth)
    monkeypatch.setattr("src.email_send_cli._load_plans",
                        Mock(side_effect=AssertionError("authorization must not load plans")))
    token_path = test_workspace / "config/google_token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text('{"token": "fixture"}', encoding="utf-8")
    assert cli_main(["--authorize", "--project-root", str(test_workspace)]) == 0
    auth.assert_called_once_with(test_workspace / "credentials.json",
                                 test_workspace / "config/google_token.json")
    service.users.assert_not_called()
    assert "No email was sent." in capsys.readouterr().out
