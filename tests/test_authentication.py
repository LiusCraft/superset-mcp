import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import main


class FakeResponse:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, login_response):
        self.login_response = login_response
        self.headers = {}
        self.login_payload = None
        self.closed = False

    async def post(self, endpoint, json):
        if endpoint != "/api/v1/security/login":
            raise AssertionError(f"Unexpected POST endpoint: {endpoint}")
        self.login_payload = json
        return self.login_response

    async def aclose(self):
        self.closed = True


class AuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_authentication_defaults_provider_and_sets_token(self):
        client = FakeClient(FakeResponse(data={"access_token": "new-token"}))
        ctx = main.SupersetContext(client=client, base_url="https://superset.test")

        with patch.object(main, "save_access_token") as save_token:
            result = await main.authenticate_with_credentials(
                ctx, "test-user", "test-password", provider=""
            )

        self.assertNotIn("error", result)
        self.assertEqual(client.login_payload["provider"], "db")
        self.assertEqual(ctx.access_token, "new-token")
        self.assertEqual(client.headers["Authorization"], "Bearer new-token")
        save_token.assert_called_once_with("new-token")

    async def test_lifespan_authenticates_from_configured_credentials(self):
        client = FakeClient(FakeResponse(data={"access_token": "env-token"}))

        with (
            patch.object(main.httpx, "AsyncClient", return_value=client),
            patch.object(main, "load_stored_token", return_value=None),
            patch.object(main, "save_access_token"),
            patch.object(main, "SUPERSET_USERNAME", "env-user"),
            patch.object(main, "SUPERSET_PASSWORD", "env-password"),
            patch.object(main, "SUPERSET_PROVIDER", "ldap"),
        ):
            async with main.superset_lifespan(main.mcp) as ctx:
                self.assertEqual(ctx.access_token, "env-token")
                self.assertEqual(client.login_payload["username"], "env-user")
                self.assertEqual(client.login_payload["password"], "env-password")
                self.assertEqual(client.login_payload["provider"], "ldap")

        self.assertTrue(client.closed)


class EnvironmentLoadingTests(unittest.TestCase):
    def test_loads_dotenv_from_cli_launch_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, ".env").write_text(
                "SUPERSET_BASE_URL=https://configured.test\n"
                "SUPERSET_USERNAME=env-user\n"
                "SUPERSET_PASSWORD=env-password\n"
                "SUPERSET_PROVIDER=ldap\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            for name in (
                "SUPERSET_BASE_URL",
                "SUPERSET_USERNAME",
                "SUPERSET_PASSWORD",
                "SUPERSET_PROVIDER",
            ):
                environment.pop(name, None)
            environment["PYTHONPATH"] = str(Path(main.__file__).resolve().parent)

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import main; "
                    "print(main.SUPERSET_BASE_URL); "
                    "print(main.SUPERSET_USERNAME); "
                    "print(main.SUPERSET_PASSWORD); "
                    "print(main.SUPERSET_PROVIDER)",
                ],
                cwd=temp_dir,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            result.stdout.splitlines(),
            ["https://configured.test", "env-user", "env-password", "ldap"],
        )


if __name__ == "__main__":
    unittest.main()
