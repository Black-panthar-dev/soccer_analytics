# Sogility GO Google email setup

Extract the ZIP before opening a launcher. Use the instructions for your
computer below.

## Google authorization

### Windows

1. Open the **Sogility GO Report Generator** folder.
2. Double-click **Authorize Google Email.bat**.
3. Google will open in your browser.
4. Sign in using the approved Google Workspace account and approve the Gmail send permission.
5. Wait for the launcher to confirm success before closing its window.

### Mac

1. Open the **Sogility GO Report Generator** folder.
2. Double-click **Authorize Google Email.command**.
3. Google will open in your browser.
4. Sign in using the approved Google Workspace account and approve the Gmail send permission.
5. Wait for the launcher to confirm success before closing the Terminal window.

The password is entered only on Google's website. The application does not see
or store it. Authorization sends no email. The application requests only Gmail's
send scope. That scope does not provide the account's email address, so the
application cannot verify the authorized account's identity without requesting
broader access. Check the account shown by Google before approving.

On macOS, the first launch may be blocked by Gatekeeper. Control-click or
right-click **Authorize Google Email.command**, choose **Open**, then choose
**Open** again when macOS asks. Keep the Terminal window open until it displays
the result. If ZIP extraction removed the launch permission, open Terminal in
the extracted folder and run:

```text
chmod +x "Authorize Google Email.command" "Send Test Email.command"
```

Then double-click the launcher again. If macOS still blocks it, contact the
developer; The recipient does not need to install Python packages or enter Python
commands.

## Test email

Only when requested by the developer, use the test launcher:

- **Windows:** double-click **Send Test Email.bat**.
- **Mac:** double-click **Send Test Email.command**.

It sends exactly one test report to the explicitly configured test recipient.
It never falls back to a production parent address. The distributed client
package leaves `test_recipient` blank, so a developer must configure and verify
a controlled test address before this launcher can send. Keep
`live_send_enabled` set to `false`.

## Setup requirements

The launchers use the project's Python environment when present, or `python3`
on macOS. The Phase II package expects the developer to install Python and the
dependencies in `requirements.txt` before delivery. The launchers check for
required components and display a friendly message if they are missing. They do
not install software or change system settings. Contact the developer if that
message appears.

## Developer/administrator preparation

Use an approved organizational Google account. The authenticated account becomes
the sender, and the application requests only the Gmail send scope.

1. Create or select a Google Cloud project and enable the Gmail API.
2. Configure the OAuth consent screen. If the app remains in Testing mode, add
   the intended sender account under **Test users**.
3. Create an OAuth client with application type **Desktop app**.
4. Save its JSON file locally as `config/google_credentials.json`.
5. For a requested test, put a controlled address in `test_recipient` in
   `config/email_settings.json`; keep `live_send_enabled` set to `false`.
6. Give the authorized user the platform-specific instructions above.
7. Confirm locally that `config/google_token.json` was created. This token is
   refreshed when possible; a normal Google password is never stored.
8. If requested, confirm exactly one test message arrived, including its `[TEST]`
   subject, body, attachment, sender, recipient, and delivery-log result.
9. Review the production recipient groups and attachments before any separately
   approved production delivery. Do not use the client authorization or test
   launchers for production delivery.

Both `config/google_credentials.json` and `config/google_token.json` are private,
machine-local operational files. Never commit, package, document the contents of,
or send either file to another person. If authorization shows an unexpected
warning or error, stop and contact the Workspace administrator.
