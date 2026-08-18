"""
Generates a QR code PNG pointing at the QR event server's submission page
(qr_event_server.py). Run this AFTER confirming the actual reachable URL
(LAN IP or tunnel) works from a phone on venue wifi -- don't guess the URL,
test it live in the room beforehand.

Usage: python generate_qr.py "http://192.168.1.42:8010/" [out_path]
"""
import sys

import qrcode


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    url = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "outputs/qr_event/qr_code.png"

    import os
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    img = qrcode.make(url, box_size=12, border=4)
    img.save(out_path)
    print(f"QR code for {url!r} written to {out_path}")


if __name__ == "__main__":
    main()
