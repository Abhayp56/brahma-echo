"""
scripts/pair_phone.py — Quick Pairing Helper for Brahma Connect Android App

Generates a Pairing Offer for your Android phone, prints the terminal QR code,
saves pairing_qr.png, and displays the direct IP:Port connection details.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add root directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import qrcode
from brahma_connect.service import get_service
from brahma_connect.gateway.discovery import local_ip


def main():
    print("\n" + "=" * 60)
    print("      BRAHMA CONNECT — ANDROID COMPANION PAIRING")
    print("=" * 60)

    # 1. Start or connect to service
    service = get_service(BASE_DIR)
    if not service.is_running():
        print("Starting Brahma Connect Gateway background service...")
        service.start_background()

    # 2. Get local IP and config
    ip = local_ip()
    port = service.gateway.config.port
    print(f"Gateway Running on : http://{ip}:{port}")
    print(f"Local mDNS Service : _BRAHMA._tcp.local.")

    # 3. Create Pairing Offer
    offer = service.create_pairing_offer(device_name="Android Phone", platform="android")
    offer_json = json.dumps(offer)
    pairing_code = offer.get("pairing_code", "------")
    print(f"Pairing Code       : {pairing_code}")
    print("-" * 60)

    # 4. Save PNG for easy viewing
    qr_img = qrcode.make(offer_json)
    qr_path = BASE_DIR / "pairing_qr.png"
    qr_img.save(str(qr_path))
    print(f"QR Image Saved     : {qr_path}")
    print("\nOption 1: SCAN QR CODE (In Brahma Connect App -> Scan QR):")

    # 5. Print ASCII QR code in terminal
    try:
        qr = qrcode.QRCode()
        qr.add_data(offer_json)
        qr.print_ascii(invert=True)
    except Exception:
        pass

    print("\nOption 2: ENTER IP MANUALLY (In Brahma Connect App -> Enter IP):")
    print(f"   Host / IP : {ip}")
    print(f"   Port      : {port}")

    print("\nOption 3: AUTO-DISCOVER (In Brahma Connect App):")
    print("   Just tap 'Find Local Brahma' (Phone and PC must be on same Wi-Fi)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
