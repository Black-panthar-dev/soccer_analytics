from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from src.email_planner import (
    EmailPlanStatus, build_email_plans, dry_run_email_planning, load_email_template,
    normalize_recipient,
)
from src.google_email_auth import GMAIL_SEND_SCOPE, GoogleEmailAuthError, get_gmail_service


def template_file(path: Path, **updates: str) -> Path:
    data = {
        "subject": "Reports for {athlete_names}", "greeting": "Hello,",
        "single_report_body": "Single report: {athlete_name} on {assessment_date}.",
        "multiple_report_body": "Multiple reports: {athlete_names} ({report_count}).",
        "closing": "Regards,\nSogility",
        "single_report_html": "Single report: {athlete_name}.",
        "multiple_report_html": "Multiple reports: {athlete_names}.",
    }
    data.update(updates)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def report(path: Path, content: bytes = b"%PDF fixture") -> Path:
    path.write_bytes(content)
    return path


def row(name: str, email: object, pdf: Path, roster_row: int = 1) -> dict[str, object]:
    return {"roster_row": roster_row, "athlete_name": name, "recipient_email": email,
            "assessment_date": "2026-08-15", "pdf_path": str(pdf),
            "generation_status": "success"}


def test_single_parent_single_athlete(test_workspace: Path) -> None:
    template = load_email_template(template_file(test_workspace / "template.json"))
    plans = build_email_plans(pd.DataFrame([row("Amelia Loehr", "parent@example.com",
                                                   report(test_workspace / "amelia.pdf"))]), template)
    assert len(plans) == 1 and plans[0].status == EmailPlanStatus.READY
    assert plans[0].athlete_names == ("Amelia Loehr",)
    assert "Single report: Amelia Loehr" in plans[0].plain_body


@pytest.mark.parametrize("count", [2, 3])
def test_shared_parent_groups_all_athletes_and_attachments(test_workspace: Path, count: int) -> None:
    template = load_email_template(template_file(test_workspace / "template.json"))
    rows = [row(f"Athlete {index}", "parent@example.com",
                report(test_workspace / f"athlete{index}.pdf"), index) for index in range(count)]
    plans = build_email_plans(pd.DataFrame(rows), template)
    assert len(plans) == 1
    assert len(plans[0].athlete_names) == len(plans[0].attachment_paths) == count
    assert f"({count})" in plans[0].plain_body


def test_different_parents_remain_separate(test_workspace: Path) -> None:
    template = load_email_template(template_file(test_workspace / "template.json"))
    rows = [row("One", "one@example.com", report(test_workspace / "one.pdf"), 1),
            row("Two", "two@example.com", report(test_workspace / "two.pdf"), 2)]
    assert len(build_email_plans(pd.DataFrame(rows), template)) == 2


def test_case_and_whitespace_normalize_to_one_group(test_workspace: Path) -> None:
    template = load_email_template(template_file(test_workspace / "template.json"))
    rows = [row("One", " Parent@Example.com ", report(test_workspace / "one.pdf"), 1),
            row("Two", "parent@example.COM", report(test_workspace / "two.pdf"), 2)]
    plans = build_email_plans(pd.DataFrame(rows), template)
    assert len(plans) == 1 and plans[0].normalized_recipient == "parent@example.com"
    assert normalize_recipient(" Parent@Example.com ") == ("Parent@Example.com", "parent@example.com")


@pytest.mark.parametrize(("email", "status"), [
    (pd.NA, EmailPlanStatus.SKIPPED_NO_EMAIL), ("", EmailPlanStatus.SKIPPED_NO_EMAIL),
    ("N/A", EmailPlanStatus.SKIPPED_NO_EMAIL), ("parent", EmailPlanStatus.INVALID_EMAIL),
    ("abc@", EmailPlanStatus.INVALID_EMAIL), ("@example.com", EmailPlanStatus.INVALID_EMAIL),
])
def test_missing_or_invalid_recipient_never_ready(test_workspace: Path, email: object, status: str) -> None:
    template = load_email_template(template_file(test_workspace / "template.json"))
    plan = build_email_plans(pd.DataFrame([row("One", email, report(test_workspace / "one.pdf"))]), template)[0]
    assert plan.status == status and plan.attachment_paths == ()


def test_missing_pdf_blocks_plan(test_workspace: Path) -> None:
    template = load_email_template(template_file(test_workspace / "template.json"))
    plan = build_email_plans(pd.DataFrame([row("One", "one@example.com",
                                                   test_workspace / "missing.pdf")]), template)[0]
    assert plan.status == EmailPlanStatus.MISSING_REPORT


def test_duplicate_pdf_is_not_duplicated_and_blocks_ambiguity(test_workspace: Path) -> None:
    template = load_email_template(template_file(test_workspace / "template.json"))
    shared = report(test_workspace / "same.pdf")
    rows = [row("One", "parent@example.com", shared, 1), row("Two", "parent@example.com", shared, 2)]
    plan = build_email_plans(pd.DataFrame(rows), template)[0]
    assert plan.status == EmailPlanStatus.ERROR
    assert plan.attachment_paths == (shared,)


def test_same_athlete_multiple_recipients_is_ambiguous(test_workspace: Path) -> None:
    template = load_email_template(template_file(test_workspace / "template.json"))
    pdf = report(test_workspace / "one.pdf")
    rows = [row("One", "one@example.com", pdf, 1), row("One", "two@example.com", pdf, 1)]
    plans = build_email_plans(pd.DataFrame(rows), template)
    assert plans and all(plan.status == EmailPlanStatus.AMBIGUOUS_RECIPIENT for plan in plans)


def test_editable_templates_and_placeholders_render(test_workspace: Path) -> None:
    path = template_file(test_workspace / "template.json", subject="Custom {report_count}",
                         single_report_body="Edited single {athlete_name}",
                         multiple_report_body="Edited multiple {athlete_names}")
    template = load_email_template(path)
    one = row("One Athlete", "parent@example.com", report(test_workspace / "one.pdf"), 1)
    single = build_email_plans(pd.DataFrame([one]), template)[0]
    assert single.subject == "Custom 1" and "Edited single One Athlete" in single.plain_body
    two = row("Two Athlete", "parent@example.com", report(test_workspace / "two.pdf"), 2)
    multiple = build_email_plans(pd.DataFrame([one, two]), template)[0]
    assert "Edited multiple One Athlete and Two Athlete" in multiple.plain_body


def test_html_single_athlete_preserves_markup_and_renders_shared_closing(test_workspace: Path) -> None:
    path = template_file(
        test_workspace / "template.json",
        closing="Thank you,\n\nJess Semnacher\nGM Sogility STL",
        single_report_html="<p>Report for <strong>{athlete_name}</strong>.</p>",
    )
    template = load_email_template(path)
    plan = build_email_plans(pd.DataFrame([
        row("One Athlete", "parent@example.com", report(test_workspace / "one.pdf"))
    ]), template)[0]

    assert plan.plain_body.endswith("Thank you,\n\nJess Semnacher\nGM Sogility STL")
    assert "<p>Report for <strong>One Athlete</strong>.</p>" in plan.html_body
    assert "<p>Thank you,<br><br>Jess Semnacher<br>GM Sogility STL</p>" in plan.html_body
    assert "\\n" not in plan.html_body
    assert "&lt;p&gt;" not in plan.html_body


def test_html_multiple_athletes_renders_placeholders_and_escapes_values(test_workspace: Path) -> None:
    path = template_file(
        test_workspace / "template.json",
        multiple_report_html="<p>Reports for <strong>{athlete_names}</strong>.</p>",
    )
    template = load_email_template(path)
    rows = [
        row("One & Athlete", "parent@example.com", report(test_workspace / "one.pdf"), 1),
        row("Two Athlete", "parent@example.com", report(test_workspace / "two.pdf"), 2),
    ]
    plan = build_email_plans(pd.DataFrame(rows), template)[0]

    assert "<strong>One &amp; Athlete and Two Athlete</strong>" in plan.html_body
    assert "Multiple reports: One & Athlete and Two Athlete (2)." in plan.plain_body


def test_unsupported_placeholder_fails_safely(test_workspace: Path) -> None:
    path = template_file(test_workspace / "template.json", subject="Secret {parent_name}")
    with pytest.raises(ValueError, match="Unsupported"):
        load_email_template(path)


def test_dry_run_never_calls_google_and_outputs_contain_no_secrets(
    test_workspace: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    google_call = Mock(side_effect=AssertionError("OAuth must not run"))
    monkeypatch.setattr("src.google_email_auth.get_gmail_service", google_call)
    template = load_email_template(template_file(test_workspace / "template.json"))
    manifest = pd.DataFrame([row("One", "one@example.com", report(test_workspace / "one.pdf"))])
    plans, outputs = dry_run_email_planning(manifest, template, test_workspace / "email")
    assert plans[0].status == EmailPlanStatus.READY
    google_call.assert_not_called()
    combined = outputs["csv"].read_text(encoding="utf-8") + outputs["markdown"].read_text(encoding="utf-8")
    combined += next(outputs["previews"].glob("*.txt")).read_text(encoding="utf-8")
    assert "refresh_token" not in combined and "client_secret" not in combined


def test_gmail_scope_is_send_only() -> None:
    assert GMAIL_SEND_SCOPE == ("https://www.googleapis.com/auth/gmail.send",)


def test_google_auth_missing_and_malformed_credentials_are_actionable(test_workspace: Path) -> None:
    missing = test_workspace / "missing.json"
    with pytest.raises(GoogleEmailAuthError, match="not found"):
        get_gmail_service(missing, test_workspace / "token.json")
    malformed = test_workspace / "credentials.json"
    malformed.write_text("not json", encoding="utf-8")
    with pytest.raises(GoogleEmailAuthError, match="malformed"):
        get_gmail_service(malformed, test_workspace / "token.json")


def test_google_auth_missing_dependencies_are_actionable(test_workspace: Path, monkeypatch) -> None:
    import builtins

    credentials = test_workspace / "credentials.json"
    credentials.write_text('{"installed": {}}', encoding="utf-8")
    original_import = builtins.__import__

    def fail_google_import(name, *args, **kwargs):
        if name.startswith("google.auth"):
            raise ImportError("mock missing Google libraries")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_google_import)
    with pytest.raises(GoogleEmailAuthError, match="Google email libraries are unavailable"):
        get_gmail_service(credentials, test_workspace / "token.json")


def test_google_auth_flow_saves_token_and_builds_gmail_without_sending(
    test_workspace: Path, monkeypatch,
) -> None:
    import sys
    import types
    from unittest.mock import Mock

    credentials = test_workspace / "credentials.json"
    token = test_workspace / "config/google_token.json"
    credentials.write_text('{"installed": {}}', encoding="utf-8")

    class FakeCredentials:
        expired = False
        refresh_token = None
        valid = True

        def to_json(self):
            return '{"token": "fake"}'

    fake_credentials = FakeCredentials()
    flow = Mock()
    flow.run_local_server.return_value = fake_credentials
    installed_flow = Mock()
    installed_flow.from_client_secrets_file.return_value = flow
    fake_google = types.ModuleType("google")
    fake_google.__path__ = []
    fake_auth = types.ModuleType("google.auth")
    fake_auth.__path__ = []
    fake_auth_exceptions = types.ModuleType("google.auth.exceptions")
    fake_auth_exceptions.RefreshError = type("RefreshError", (Exception,), {})
    fake_transport = types.ModuleType("google.auth.transport")
    fake_transport.__path__ = []
    fake_requests = types.ModuleType("google.auth.transport.requests")
    fake_requests.Request = type("Request", (), {})
    fake_oauth2 = types.ModuleType("google.oauth2")
    fake_oauth2.__path__ = []
    fake_user = types.ModuleType("google.oauth2.credentials")
    fake_user.Credentials = type("Credentials", (), {
        "from_authorized_user_file": staticmethod(lambda *_args: None),
    })
    fake_oauthlib = types.ModuleType("google_auth_oauthlib")
    fake_oauthlib.__path__ = []
    fake_flow = types.ModuleType("google_auth_oauthlib.flow")
    fake_flow.InstalledAppFlow = installed_flow
    fake_client = types.ModuleType("googleapiclient")
    fake_client.__path__ = []
    fake_discovery = types.ModuleType("googleapiclient.discovery")
    gmail_service = Mock()
    build = Mock(return_value=gmail_service)
    fake_discovery.build = build
    modules = {
        "google": fake_google, "google.auth": fake_auth,
        "google.auth.exceptions": fake_auth_exceptions,
        "google.auth.transport": fake_transport,
        "google.auth.transport.requests": fake_requests,
        "google.oauth2": fake_oauth2, "google.oauth2.credentials": fake_user,
        "google_auth_oauthlib": fake_oauthlib,
        "google_auth_oauthlib.flow": fake_flow,
        "googleapiclient": fake_client,
        "googleapiclient.discovery": fake_discovery,
    }
    monkeypatch.setitem(sys.modules, "google", fake_google)
    for module_name, module in modules.items():
        monkeypatch.setitem(sys.modules, module_name, module)

    service = get_gmail_service(credentials, token)
    assert service is gmail_service
    assert token.is_file() and token.read_text(encoding="utf-8") == '{"token": "fake"}'
    installed_flow.from_client_secrets_file.assert_called_once_with(str(credentials), GMAIL_SEND_SCOPE)
    build.assert_called_once()
    gmail_service.users.assert_not_called()
