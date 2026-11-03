"""Discover the server's phone links without trusting browser Host headers.

Kept independent of settings/database imports so the desktop launcher and API
use exactly the same physical-adapter and Tailscale discovery.
"""

import base64
from io import BytesIO
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys

def physical_lan_addresses():
    """On Windows, prefer active Wi-Fi/Ethernet over a VPN default route."""
    if sys.platform != "win32":
        return ()
    script = (
        "$ErrorActionPreference='Stop'; "
        "@(Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' } | "
        "ForEach-Object { Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 "
        "-ErrorAction SilentlyContinue | Where-Object { $_.AddressState -eq 'Preferred' } | "
        "Select-Object -ExpandProperty IPAddress }) | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ()
        addresses = json.loads(result.stdout)
        return tuple(addresses if isinstance(addresses, list) else [addresses])
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return ()


def lan_addresses():
    """Prefer connected physical adapters; fall back to the default route."""
    addresses = list(physical_lan_addresses())
    fallback = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("1.1.1.1", 80))  # No packet is sent by UDP connect.
            fallback.append(sock.getsockname()[0])
    except OSError:
        pass

    try:
        fallback.extend(
            info[4][0]
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        )
    except OSError:
        pass
    for candidates in (addresses, fallback):
        usable = []
        for address in candidates:
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError:
                continue
            if parsed.version == 4 and parsed.is_private and not parsed.is_loopback and not parsed.is_link_local and address not in usable:
                usable.append(address)
        if usable:
            return tuple(usable)
    return ()


def stable_phone_hostname():
    """Use an existing private MagicDNS name if Tailscale is connected."""
    executable = shutil.which("tailscale")
    if not executable and sys.platform == "win32":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tailscale" / "tailscale.exe"
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "status", "--json"], capture_output=True, text=True,
            timeout=3, check=False,
        )
        if result.returncode != 0:
            return None
        status = json.loads(result.stdout)
        hostname = str((status.get("Self") or {}).get("DNSName") or "").rstrip(".").lower()
        if status.get("BackendState") == "Running" and re.fullmatch(r"[a-z0-9.-]+\.ts\.net", hostname):
            return hostname
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        pass
    return None


def phone_links(addresses, port, hostname=None):
    """Return plain login links; never embed credentials or session tokens."""
    if not 1 <= port <= 65535:
        raise ValueError("Frontend port must be between 1 and 65535.")
    links = []
    if hostname and re.fullmatch(r"[a-z0-9.-]+\.ts\.net", hostname):
        links.append({"kind": "tailscale", "label": "Tailscale", "url": f"http://{hostname}:{port}"})
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if (parsed.version != 4 or not parsed.is_private or parsed.is_loopback
                or parsed.is_link_local or parsed.is_unspecified or parsed.is_multicast):
            continue
        url = f"http://{parsed}:{port}"
        if not any(link["url"] == url for link in links):
            links.append({"kind": "lan", "label": "Same Wi-Fi / LAN", "url": url})
    return links


def qr_data_url(url):
    """Create the QR in memory; no temp PNG or external viewer is needed."""
    import qrcode

    qr = qrcode.QRCode(box_size=8, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    output = BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def phone_access(frontend_port):
    links = phone_links(lan_addresses(), frontend_port, stable_phone_hostname())
    return {
        "links": [{**link, "qrDataUrl": qr_data_url(link["url"])} for link in links],
        "message": ("Scan a QR code with your phone to open Joross Farm. Sign in with your own account."
                    if links else "No LAN address was found. Connect this computer and your phone to the same Wi-Fi, then refresh."),
    }
