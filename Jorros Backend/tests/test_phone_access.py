"""Exercise phone discovery, real QR generation, authorization and the launcher."""

import base64
from contextlib import redirect_stdout
import importlib.util
from io import BytesIO, StringIO
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-at-least-32-bytes-long")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models import Role, User
from app.routers.system import router
from app.services import phone_access as network


class PhoneLinkTests(unittest.TestCase):
    def test_links_use_frontend_port_and_filter_unusable_addresses(self):
        links = network.phone_links(
            ["127.0.0.1", "0.0.0.0", "169.254.1.2", "8.8.8.8", "::1", "invalid",
             "192.168.1.9", "192.168.1.9", "10.0.0.4"], 3105,
            "farm.example.ts.net",
        )
        self.assertEqual([link["url"] for link in links], [
            "http://farm.example.ts.net:3105", "http://192.168.1.9:3105", "http://10.0.0.4:3105",
        ])
        self.assertEqual(network.phone_links([], 3000, "attacker.example/login?token=secret"), [])
        for port in [0, 65536]:
            with self.assertRaises(ValueError):
                network.phone_links(["192.168.1.9"], port)

    def test_connected_physical_adapter_wins_over_vpn_default_route(self):
        with patch.object(network, "physical_lan_addresses", return_value=("192.168.50.8",)), \
             patch.object(network.socket, "socket") as socket, \
             patch.object(network.socket, "getaddrinfo", return_value=[]):
            socket.return_value.__enter__.return_value.getsockname.return_value = ("100.64.0.2", 0)
            self.assertEqual(network.lan_addresses(), ("192.168.50.8",))

    def test_windows_adapter_query_handles_single_ip_and_failure(self):
        with patch.object(network.sys, "platform", "win32"), \
             patch.object(network.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout='"192.168.50.8"')):
            self.assertEqual(network.physical_lan_addresses(), ("192.168.50.8",))
        with patch.object(network.sys, "platform", "win32"), \
             patch.object(network.subprocess, "run", side_effect=OSError):
            self.assertEqual(network.physical_lan_addresses(), ())

    def test_qr_is_a_real_png_generated_entirely_in_memory(self):
        import qrcode
        captured = []
        original = qrcode.QRCode.add_data

        def capture(qr, data, *args, **kwargs):
            captured.append(data)
            return original(qr, data, *args, **kwargs)

        url = "http://192.168.50.8:3105"
        with patch.object(qrcode.QRCode, "add_data", capture):
            encoded = network.qr_data_url(url)
        self.assertEqual(captured, [url])
        prefix, payload = encoded.split(",", 1)
        self.assertEqual(prefix, "data:image/png;base64")
        with Image.open(BytesIO(base64.b64decode(payload, validate=True))) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.width, image.height)
            self.assertGreaterEqual(image.width, 200)
            image.verify()


class PhoneAccessHttpTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:",
                                    connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.headers = {}
        with Session(self.engine) as db:
            for name, permissions in [
                ("Viewer", ["dashboard:view"]),
                ("Worker", ["workforce:submit", "dashboard:view"]),
                ("Administrator", ["*"]),
                ("NoDashboard", ["inventory:view"]),
            ]:
                role = Role(name=name, is_active=True)
                role.set_permissions(permissions)
                user = User(user_code=f"QR-{name}", username=f"qr.{name.lower()}",
                            full_name=f"QR {name}", password_hash="test-only", status="Active", role=role)
                db.add(user)
                db.flush()
                token, _ = create_access_token(user.id)
                self.headers[name] = {"Authorization": f"Bearer {token}"}
            db.commit()

        app = FastAPI()
        app.include_router(router)

        def test_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)
        self.old_port = settings.farm_frontend_port
        settings.farm_frontend_port = 3105

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        settings.farm_frontend_port = self.old_port

    def test_anonymous_invalid_and_unauthorized_users_cannot_discover_links(self):
        with patch("app.routers.system.phone_access") as discovery:
            for headers, status in [({}, 401), ({"Authorization": "Bearer invalid"}, 401),
                                    (self.headers["Worker"], 403), (self.headers["NoDashboard"], 403)]:
                self.assertEqual(self.client.get("/api/v1/system/phone-access", headers=headers).status_code, status)
            discovery.assert_not_called()

    def test_authorized_requests_use_server_network_refresh_and_no_store(self):
        with patch.object(network, "lan_addresses", side_effect=[("192.168.1.8",), ("10.2.3.4",)]), \
             patch.object(network, "stable_phone_hostname", return_value=None):
            first = self.client.get("/api/v1/system/phone-access?port=9999&url=http://attacker.example",
                                    headers={**self.headers["Viewer"], "Host": "attacker.example:9999"})
            second = self.client.get("/api/v1/system/phone-access", headers=self.headers["Administrator"])
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.headers["Cache-Control"], "no-store")
        self.assertEqual(first.json()["links"][0]["url"], "http://192.168.1.8:3105")
        self.assertEqual(second.json()["links"][0]["url"], "http://10.2.3.4:3105")
        self.assertTrue(first.json()["links"][0]["qrDataUrl"].startswith("data:image/png;base64,"))
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(User)).all()), 4)
            self.assertEqual(len(db.scalars(select(Role)).all()), 4)

    def test_no_network_is_actionable_and_tailscale_only_still_works(self):
        with patch.object(network, "lan_addresses", return_value=()), \
             patch.object(network, "stable_phone_hostname", side_effect=[None, "farm.example.ts.net"]):
            empty = self.client.get("/api/v1/system/phone-access", headers=self.headers["Viewer"])
            stable = self.client.get("/api/v1/system/phone-access", headers=self.headers["Viewer"])
        self.assertEqual(empty.json()["links"], [])
        self.assertIn("Wi-Fi", empty.json()["message"])
        self.assertEqual(stable.json()["links"][0]["url"], "http://farm.example.ts.net:3105")


class LauncherPhoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / "run_farm.py"
        spec = importlib.util.spec_from_file_location("qr_test_launcher", path)
        cls.launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.launcher)

    def test_windows_launcher_prints_links_without_opening_photos(self):
        output = StringIO()
        with patch.object(self.launcher.sys, "platform", "win32"), \
             patch.object(self.launcher.os, "startfile", create=True) as viewer, redirect_stdout(output):
            self.launcher.show_phone_link(("192.168.1.9",), 3105)
        viewer.assert_not_called()
        self.assertIn("http://192.168.1.9:3105", output.getvalue())
        self.assertIn("QR button", output.getvalue())

    def test_backend_receives_the_actual_phone_facing_port(self):
        with patch.object(self.launcher.subprocess, "Popen") as popen:
            self.launcher.start_backend(8123, 3105)
        args, kwargs = popen.call_args
        self.assertIn("8123", args[0])
        self.assertEqual(kwargs["env"]["FARM_FRONTEND_PORT"], "3105")


if __name__ == "__main__":
    unittest.main()
