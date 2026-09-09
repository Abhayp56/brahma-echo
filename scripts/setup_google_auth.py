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


def main():
    print("=" * 65)
    print("  ARYA Google Workspace (Calendar + Gmail) Authorization Setup")
    print("=" * 65)

    if not CREDENTIALS_PATH.exists():
        print(f"\n[!] Error: Credentials file not found at:\n    {CREDENTIALS_PATH}")
        print("\nPlease follow these steps:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a project and enable 'Google Calendar API' and 'Gmail API'.")
        print("3. Go to 'Credentials' -> 'Create Credentials' -> 'OAuth client ID'.")
        print("   - Application type: Desktop app (or Web application with http://localhost:8080/ redirect)")
        print("4. Download the JSON file and save it as:")
        print(f"   {CREDENTIALS_PATH}\n")
        return

    with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        installed = data.get("installed") or data.get("web") or data
        client_id = installed.get("client_id")
        client_secret = installed.get("client_secret")

    if not client_id or not client_secret:
        print("[!] Invalid credentials file: missing client_id or client_secret.")
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
    print("Waiting for authentication callback on http://localhost:8080/ ...")
    while not OAuthCallbackHandler.auth_code:
        server.handle_request()

    code = OAuthCallbackHandler.auth_code
    print("[+] Authorization code received! Exchanging for tokens...")

    token_params = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
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
            return

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
    except Exception as e:
        print(f"[!] Error exchanging code for tokens: {e}")


if __name__ == "__main__":
    main()
