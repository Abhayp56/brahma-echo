"""
scripts/setup_google_auth.py — One-Time Google Calendar & Gmail OAuth Authorization

Run this script once on your laptop to authenticate ARYA with your Google account.
It will generate config/google_token.json containing your persistent refresh token.

Usage:
    python scripts/setup_google_auth.py
"""

from __future__ import annotations

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request
import webbrowser

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
CREDENTIALS_PATH = CONFIG_DIR / "google_credentials.json"
TOKEN_PATH = CONFIG_DIR / "google_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
]
REDIRECT_URI = "http://localhost:8080/"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = """
            <html>
              <body style="font-family: sans-serif; text-align: center; padding: 50px; background: #0c0e14; color: #fff;">
                <h1 style="color: #00ff88;">Authentication Successful!</h1>
                <p>ARYA is now authorized to access Google Calendar and Gmail.</p>
                <p>You can close this tab and return to your terminal.</p>
              </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing authorization code.")

    def log_message(self, format, *args):
        pass  # Quiet HTTP server logs


def exchange_and_save(code: str, client_id: str, client_secret: str, redirect_uri: str) -> bool:
    token_params = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=urllib.parse.urlencode(token_params).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read().decode("utf-8"))

        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            print("[!] Warning: No refresh token returned. Re-run with prompt=consent.")
            return False

        token_data = {
            "refresh_token": refresh_token,
            "access_token": tokens.get("access_token"),
            "expires_at": tokens.get("expires_in", 3600),
        }
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)

        print(f"\n[SUCCESS] Google Calendar and Gmail tokens saved to:\n  {TOKEN_PATH}")
        print("\nARYA is now ready to manage your Calendar and Gmail!")

        # Live verification
        try:
            if str(BASE_DIR) not in sys.path:
                sys.path.insert(0, str(BASE_DIR))
            from cloud.google_workspace import list_calendar_events_sync, list_emails_sync
            print("\n" + "-" * 50)
            print("Verifying Calendar Connection...")
            cal_res = list_calendar_events_sync(max_results=3)
            if cal_res.get("success"):
                print(f"[OK] Calendar Connected! Found {cal_res.get('total', 0)} upcoming events.")
            else:
                print(f"[!] Calendar Notice: {cal_res.get('error')}")

            print("\nVerifying Gmail Connection...")
            gmail_res = list_emails_sync(max_results=3)
            if gmail_res.get("success"):
                print(f"[OK] Gmail Connected! Found {gmail_res.get('total', 0)} unread emails.")
                for m in gmail_res.get("messages", []):
                    subj = m.get("subject", "(No subject)").encode("ascii", "replace").decode("ascii")
                    print(f"    - {subj}")
            else:
                print(f"[!] Gmail Notice: {gmail_res.get('error')}")
            print("-" * 50)
        except Exception as ve:
            print(f"[!] Verification notice: {ve}")

        return True
    except Exception as e:
        print(f"[!] Error exchanging code for tokens: {e}")
        return False


def main():
    print("=" * 65)
    print("  ARYA Google Workspace (Calendar + Gmail) Authorization Setup")
    print("=" * 65)

    if not CREDENTIALS_PATH.exists():
        print(f"\n[!] Error: Credentials file not found at:\n    {CREDENTIALS_PATH}")
        return

    with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        installed = data.get("installed") or data.get("web") or data
        client_id = installed.get("client_id")
        client_secret = installed.get("client_secret")

    if not client_id or not client_secret:
        print("[!] Invalid credentials file: missing client_id or client_secret.")
        return

    # Check if code or URL passed via command line
    manual_code = None
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ("--code", "-c") and len(sys.argv) > 2:
            arg = sys.argv[2]
        if "code=" in arg:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(arg).query)
            manual_code = parsed.get("code", [None])[0]
        else:
            manual_code = arg.strip()

    if manual_code:
        print(f"[+] Using provided authorization code: {manual_code[:12]}...")
        exchange_and_save(manual_code, client_id, client_secret, REDIRECT_URI)
        return

    auth_params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(auth_params)

    print("\nOpening your web browser for Google Account consent...")
    print(f"\nIf browser doesn't open automatically, visit this URL:\n{auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    server = HTTPServer(("localhost", 8080), OAuthCallbackHandler)
    server.timeout = 1.0
    print("Waiting for authentication callback on http://localhost:8080/ ...")
    print("(If automatic redirect does not complete, copy the code from the address bar and run:")
    print(' python scripts/setup_google_auth.py --code "YOUR_CODE")\n')

    while not OAuthCallbackHandler.auth_code:
        server.handle_request()

    code = OAuthCallbackHandler.auth_code
    print("[+] Authorization code received! Exchanging for tokens...")
    exchange_and_save(code, client_id, client_secret, REDIRECT_URI)


if __name__ == "__main__":
    main()
