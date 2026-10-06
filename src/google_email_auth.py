"""OAuth 2.0 foundation for a future Gmail sender; never used by dry runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final


GMAIL_SEND_SCOPE: Final[tuple[str, ...]] = ("https://www.googleapis.com/auth/gmail.send",)


class GoogleEmailAuthError(RuntimeError):
    """Actionable authentication/setup failure safe to show to a client."""


def get_gmail_service(credentials_path: Path, token_path: Path):
    """Authorize and return a Gmail API client with send-only permission.

    This function is deliberately not called by email planning or dry-run code.
    """
    credentials_file, token_file = Path(credentials_path), Path(token_path)
    if not credentials_file.is_file():
        raise GoogleEmailAuthError(
            f"Google OAuth client credentials were not found at {credentials_file}. "
            "Download a Desktop app OAuth file from Google Cloud and place it there."
        )
    try:
        payload = json.loads(credentials_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoogleEmailAuthError(
            "Google OAuth client credentials are unreadable or malformed. Download a new "
            "Desktop app credentials JSON file from Google Cloud."
        ) from exc
    if not isinstance(payload, dict) or "installed" not in payload:
        raise GoogleEmailAuthError(
            "Google OAuth credentials must be for an installed/desktop application."
        )
    try:
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GoogleEmailAuthError(
            "Google email libraries are unavailable. Install the project requirements "
            "before authorizing Gmail."
        ) from exc

    credentials = None
    if token_file.is_file():
        try:
            credentials = Credentials.from_authorized_user_file(str(token_file), GMAIL_SEND_SCOPE)
        except (ValueError, OSError) as exc:
            raise GoogleEmailAuthError(
                f"The saved Google token at {token_file} is invalid. Remove it and authorize again."
            ) from exc
    try:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        elif not credentials or not credentials.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), GMAIL_SEND_SCOPE)
            credentials = flow.run_local_server(port=0)
            if credentials is None:
                raise GoogleEmailAuthError("Google authorization was cancelled; no token was created.")
    except RefreshError as exc:
        raise GoogleEmailAuthError(
            "Google authorization has expired or was revoked. Remove the saved token and authorize again."
        ) from exc
    except GoogleEmailAuthError:
        raise
    except Exception as exc:
        raise GoogleEmailAuthError(
            "Google authorization did not complete. Check the OAuth configuration and try again."
        ) from exc

    token_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        token_file.write_text(credentials.to_json(), encoding="utf-8")
    except OSError as exc:
        raise GoogleEmailAuthError(f"Could not securely save the Google token at {token_file}.") from exc
    try:
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)
    except Exception as exc:
        raise GoogleEmailAuthError("Could not initialize the Gmail API client.") from exc
