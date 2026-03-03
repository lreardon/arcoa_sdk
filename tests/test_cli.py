import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from click.testing import CliRunner

from arcoa.cli import cli
from arcoa.config import load_config


@pytest.fixture
def runner():
    return CliRunner()


class TestSignup:
    def test_signup_sends_email(self, runner):
        with patch("arcoa.cli.ArcoaClient") as MockClient:
            instance = MockClient.return_value
            instance.signup = AsyncMock(return_value={})

            result = runner.invoke(cli, ["signup", "--email", "test@example.com"])

            assert result.exit_code == 0, result.output
            assert "Verification email sent to test@example.com" in result.output
            assert "Check your inbox" in result.output
            instance.signup.assert_called_once_with("test@example.com")

    def test_signup_with_custom_api_url(self, runner):
        with patch("arcoa.cli.ArcoaClient") as MockClient:
            instance = MockClient.return_value
            instance.signup = AsyncMock(return_value={})

            result = runner.invoke(cli, [
                "signup", "--email", "test@example.com",
                "--api-url", "https://custom.api.com",
            ])

            assert result.exit_code == 0, result.output
            MockClient.assert_called_once_with(agent_id="", private_key="", api_url="https://custom.api.com")

    def test_signup_requires_email(self, runner):
        result = runner.invoke(cli, ["signup"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()


class TestLogin:
    def test_login_saves_config(self, runner):
        from nacl.signing import SigningKey
        from nacl.encoding import HexEncoder

        sk = SigningKey.generate()
        private_key = sk.encode(encoder=HexEncoder).decode()
        public_key = sk.verify_key.encode(encoder=HexEncoder).decode()

        agent_data = {"agent_id": "agent-abc", "display_name": "TestBot", "public_key": public_key}

        with patch("arcoa.cli.ArcoaClient") as MockClient:
            instance = MockClient.return_value
            instance.get_agent = AsyncMock(return_value=agent_data)

            with patch("arcoa.cli.save_config") as mock_save:
                result = runner.invoke(cli, [
                    "login",
                    "--agent-id", "agent-abc",
                    "--private-key", private_key,
                ])

                assert result.exit_code == 0, result.output
                assert "Logged in as TestBot" in result.output
                assert "Config saved" in result.output

                mock_save.assert_called_once()
                saved = mock_save.call_args[0][0]
                assert saved["agent_id"] == "agent-abc"
                assert saved["private_key"] == private_key
                assert saved["public_key"] == public_key
                assert saved["display_name"] == "TestBot"

    def test_login_invalid_private_key(self, runner):
        result = runner.invoke(cli, [
            "login",
            "--agent-id", "agent-abc",
            "--private-key", "not-a-valid-hex-key",
        ])
        assert result.exit_code != 0
        assert "Invalid private key" in result.output

    def test_login_agent_not_found(self, runner):
        from nacl.signing import SigningKey
        from nacl.encoding import HexEncoder

        sk = SigningKey.generate()
        private_key = sk.encode(encoder=HexEncoder).decode()

        with patch("arcoa.cli.ArcoaClient") as MockClient:
            instance = MockClient.return_value
            instance.get_agent = AsyncMock(side_effect=Exception("404: Agent not found"))

            result = runner.invoke(cli, [
                "login",
                "--agent-id", "nonexistent",
                "--private-key", private_key,
            ])
            assert result.exit_code != 0
            assert "Could not validate agent" in result.output


class TestInit:
    def test_init_registers_and_saves_config(self, runner, tmp_path):
        config_path = tmp_path / "config.json"

        async def mock_register(**kwargs):
            return {"agent_id": "new-agent-123", "display_name": kwargs["display_name"]}

        with patch("arcoa.cli.ArcoaClient") as MockClient:
            instance = MockClient.return_value
            instance.register = AsyncMock(side_effect=mock_register)

            with patch("arcoa.cli.save_config") as mock_save:
                result = runner.invoke(cli, [
                    "init",
                    "--name", "TestBot",
                    "--token", "reg-token-123",
                ])

                assert result.exit_code == 0, result.output
                assert "Agent registered: TestBot" in result.output
                assert "new-agent-123" in result.output

                mock_save.assert_called_once()
                saved_config = mock_save.call_args[0][0]
                assert saved_config["agent_id"] == "new-agent-123"
                assert saved_config["display_name"] == "TestBot"
                assert "private_key" in saved_config
                assert "public_key" in saved_config

    def test_init_with_capabilities(self, runner):
        async def mock_register(**kwargs):
            assert kwargs["capabilities"] == ["pdf", "ocr", "nlp"]
            return {"agent_id": "a1"}

        with patch("arcoa.cli.ArcoaClient") as MockClient:
            instance = MockClient.return_value
            instance.register = AsyncMock(side_effect=mock_register)

            with patch("arcoa.cli.save_config"):
                result = runner.invoke(cli, [
                    "init",
                    "--name", "Bot",
                    "--token", "t",
                    "--capabilities", "pdf, ocr, nlp",
                ])
                assert result.exit_code == 0, result.output

    def test_init_with_custom_api_url(self, runner):
        with patch("arcoa.cli.ArcoaClient") as MockClient:
            instance = MockClient.return_value
            instance.register = AsyncMock(return_value={"agent_id": "a1"})

            with patch("arcoa.cli.save_config") as mock_save:
                result = runner.invoke(cli, [
                    "init",
                    "--name", "Bot",
                    "--token", "t",
                    "--api-url", "https://custom.api.com",
                ])
                assert result.exit_code == 0, result.output
                saved = mock_save.call_args[0][0]
                assert saved["api_url"] == "https://custom.api.com"

    def test_init_passes_hosting_mode_websocket(self, runner):
        async def mock_register(**kwargs):
            assert kwargs["hosting_mode"] == "websocket"
            return {"agent_id": "a1"}

        with patch("arcoa.cli.ArcoaClient") as MockClient:
            instance = MockClient.return_value
            instance.register = AsyncMock(side_effect=mock_register)

            with patch("arcoa.cli.save_config"):
                result = runner.invoke(cli, ["init", "--name", "B", "--token", "t"])
                assert result.exit_code == 0, result.output


class TestStatus:
    def test_status_shows_info(self, runner):
        config = {
            "agent_id": "abc-123",
            "private_key": "deadbeef",
            "api_url": "https://api.staging.arcoa.ai",
            "display_name": "LandhoBot",
        }

        async def mock_balance():
            return {"balance": "42.50"}

        async def mock_reputation(agent_id):
            return {"seller_rating": 4.8, "client_rating": 4.9}

        with patch("arcoa.cli.load_config", return_value=config):
            with patch("arcoa.cli.ArcoaClient") as MockClient:
                instance = MockClient.return_value
                instance.get_balance = AsyncMock(side_effect=mock_balance)
                instance.get_reputation = AsyncMock(side_effect=mock_reputation)

                result = runner.invoke(cli, ["status"])

                assert result.exit_code == 0, result.output
                assert "LandhoBot" in result.output
                assert "abc-123" in result.output
                assert "42.50" in result.output
                assert "4.8" in result.output
                assert "4.9" in result.output

    def test_status_no_config(self, runner):
        with patch("arcoa.cli.load_config", side_effect=Exception("Config not found")):
            result = runner.invoke(cli, ["status"])
            assert result.exit_code != 0


class TestDiscover:
    def test_discover_shows_results(self, runner):
        config = {
            "agent_id": "a1",
            "private_key": "deadbeef",
            "api_url": "https://api.staging.arcoa.ai",
            "display_name": "Bot",
        }

        results = [
            {"display_name": "DataBot", "rating": 4.9, "base_price": "0.05", "price_model": "per_unit", "capabilities": ["pdf", "ocr"]},
            {"display_name": "ParseAgent", "rating": 4.7, "base_price": "0.03", "price_model": "per_unit", "capabilities": ["pdf"]},
        ]

        with patch("arcoa.cli.load_config", return_value=config):
            with patch("arcoa.cli.ArcoaClient") as MockClient:
                instance = MockClient.return_value
                instance.discover = AsyncMock(return_value=results)

                result = runner.invoke(cli, ["discover", "--skill", "pdf"])

                assert result.exit_code == 0, result.output
                assert "Found 2 agents" in result.output
                assert "DataBot" in result.output
                assert "ParseAgent" in result.output

    def test_discover_no_results(self, runner):
        config = {"agent_id": "a1", "private_key": "ab", "api_url": "https://x.com", "display_name": "B"}

        with patch("arcoa.cli.load_config", return_value=config):
            with patch("arcoa.cli.ArcoaClient") as MockClient:
                instance = MockClient.return_value
                instance.discover = AsyncMock(return_value=[])

                result = runner.invoke(cli, ["discover"])

                assert result.exit_code == 0
                assert "No agents found" in result.output


class TestRecover:
    def test_recover_generates_keypair_and_saves_config(self, runner):
        async def mock_rotate(recovery_token, new_public_key):
            return {"message": "Public key rotated successfully."}

        async def mock_get_agent(agent_id):
            return {"display_name": "RecoveredBot"}

        with patch("arcoa.cli.ArcoaClient") as MockClient:
            instance = MockClient.return_value
            instance.rotate_key = AsyncMock(side_effect=mock_rotate)
            instance.get_agent = AsyncMock(side_effect=mock_get_agent)

            with patch("arcoa.cli.save_config") as mock_save:
                result = runner.invoke(cli, [
                    "recover",
                    "--email", "test@example.com",
                    "--token", "recovery-token-123",
                    "--agent-id", "agent-abc",
                ])

                assert result.exit_code == 0, result.output
                assert "rotated successfully" in result.output
                assert "RecoveredBot" in result.output

                mock_save.assert_called_once()
                saved = mock_save.call_args[0][0]
                assert saved["agent_id"] == "agent-abc"
                assert "private_key" in saved
                assert "public_key" in saved

    def test_recover_with_user_provided_key(self, runner):
        async def mock_rotate(recovery_token, new_public_key):
            assert new_public_key == "user-provided-pubkey"
            return {"message": "Public key rotated successfully."}

        with patch("arcoa.cli.ArcoaClient") as MockClient:
            instance = MockClient.return_value
            instance.rotate_key = AsyncMock(side_effect=mock_rotate)

            with patch("arcoa.cli.save_config") as mock_save:
                result = runner.invoke(cli, [
                    "recover",
                    "--email", "test@example.com",
                    "--token", "recovery-token-123",
                    "--agent-id", "agent-abc",
                    "--public-key", "user-provided-pubkey",
                ])

                assert result.exit_code == 0, result.output
                assert "rotated successfully" in result.output
                assert "arcoa login" in result.output
                mock_save.assert_not_called()

    def test_recover_rotation_failure(self, runner):
        with patch("arcoa.cli.ArcoaClient") as MockClient:
            instance = MockClient.return_value
            instance.rotate_key = AsyncMock(side_effect=Exception("Invalid token"))

            result = runner.invoke(cli, [
                "recover",
                "--email", "test@example.com",
                "--token", "bad-token",
                "--agent-id", "agent-abc",
            ])

            assert result.exit_code != 0
            assert "Key rotation failed" in result.output


class TestConnect:
    def test_connect_no_config(self, runner):
        from arcoa.exceptions import ArcoaConfigError

        with patch("arcoa.cli.load_config", side_effect=ArcoaConfigError("No config")):
            result = runner.invoke(cli, ["connect"])
            assert result.exit_code != 0
            assert "No config" in result.output
