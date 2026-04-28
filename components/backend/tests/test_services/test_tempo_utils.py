"""Tests for tempo_utils blockchain utilities."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import syfthub.services.tempo_utils as tempo_module


@pytest.fixture(autouse=True)
def reset_module_globals():
    """Reset module-level cached instances between tests."""
    tempo_module._w3_instance = None
    tempo_module._w3_rpc_url = None
    tempo_module._balance_contract = None
    tempo_module._transfer_contract = None

    yield

    tempo_module._w3_instance = None
    tempo_module._w3_rpc_url = None
    tempo_module._balance_contract = None
    tempo_module._transfer_contract = None


class TestGetRpcUrl:
    def test_mainnet_when_testnet_false(self):
        with patch("syfthub.services.tempo_utils.settings") as mock_settings:
            mock_settings.tempo_testnet = False
            url = tempo_module._get_rpc_url()
            assert url == tempo_module.TEMPO_MAINNET_RPC_URL

    def test_testnet_when_testnet_true(self):
        with patch("syfthub.services.tempo_utils.settings") as mock_settings:
            mock_settings.tempo_testnet = True
            url = tempo_module._get_rpc_url()
            assert url == tempo_module.TEMPO_TESTNET_RPC_URL


class TestGetW3:
    def test_creates_new_instance(self):
        mock_w3 = MagicMock()
        mock_provider = MagicMock()
        with patch("syfthub.services.tempo_utils.settings") as mock_settings:
            mock_settings.tempo_testnet = False
            with patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls:
                mock_web3_cls.HTTPProvider.return_value = mock_provider
                mock_web3_cls.return_value = mock_w3
                result = tempo_module._get_w3()
                assert result is mock_w3
                mock_web3_cls.assert_called_once_with(mock_provider)

    def test_returns_cached_instance_same_url(self):
        mock_w3 = MagicMock()
        tempo_module._w3_instance = mock_w3
        tempo_module._w3_rpc_url = TEMPO_MAINNET_RPC_URL
        with patch("syfthub.services.tempo_utils.settings") as mock_settings:
            mock_settings.tempo_testnet = False
            with patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls:
                result = _get_w3()
                assert result is mock_w3
                mock_web3_cls.assert_not_called()

    def test_recreates_instance_on_url_change(self):
        mock_w3_old = MagicMock()
        mock_w3_new = MagicMock()
        tempo_module._w3_instance = mock_w3_old
        tempo_module._w3_rpc_url = tempo_module.TEMPO_MAINNET_RPC_URL
        with patch("syfthub.services.tempo_utils.settings") as mock_settings:
            mock_settings.tempo_testnet = True  # switches to testnet URL
            with patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls:
                mock_web3_cls.return_value = mock_w3_new
                result = tempo_module._get_w3()
                assert result is mock_w3_new


class TestGetBalanceContract:
    def test_creates_contract_when_none(self):
        mock_w3 = MagicMock()
        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        mock_w3.to_checksum_address = MagicMock(return_value="0xCHECKSUM")

        with (
            patch("syfthub.services.tempo_utils._get_w3", return_value=mock_w3),
            patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls,
        ):
            mock_web3_cls.to_checksum_address.return_value = "0xCHECKSUM"
            result = tempo_module._get_balance_contract()
            assert result is mock_contract

    def test_returns_cached_contract(self):
        mock_contract = MagicMock()
        mock_w3 = MagicMock()
        tempo_module._balance_contract = mock_contract
        with patch("syfthub.services.tempo_utils._get_w3", return_value=mock_w3):
            result = tempo_module._get_balance_contract()
            assert result is mock_contract
            mock_w3.eth.contract.assert_not_called()


class TestGetTransferContract:
    def test_creates_contract_when_none(self):
        mock_w3 = MagicMock()
        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract

        with (
            patch("syfthub.services.tempo_utils._get_w3", return_value=mock_w3),
            patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls,
        ):
            mock_web3_cls.to_checksum_address.return_value = "0xCHECKSUM"
            result = tempo_module._get_transfer_contract()
            assert result is mock_contract

    def test_returns_cached_contract(self):
        mock_contract = MagicMock()
        mock_w3 = MagicMock()
        tempo_module._transfer_contract = mock_contract
        with patch("syfthub.services.tempo_utils._get_w3", return_value=mock_w3):
            result = tempo_module._get_transfer_contract()
            assert result is mock_contract
            mock_w3.eth.contract.assert_not_called()


class TestSyncGetBalance:
    def test_returns_balance(self):
        mock_contract = MagicMock()
        mock_contract.functions.balanceOf.return_value.call.return_value = 1_500_000

        with (
            patch(
                "syfthub.services.tempo_utils._get_balance_contract",
                return_value=mock_contract,
            ),
            patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls,
        ):
            mock_web3_cls.to_checksum_address.return_value = "0xADDR"
            result = tempo_module._sync_get_balance("0xabc")
            expected = 1_500_000 / (10**PATH_USD_DECIMALS)
            assert result == pytest.approx(expected)

    def test_zero_balance(self):
        mock_contract = MagicMock()
        mock_contract.functions.balanceOf.return_value.call.return_value = 0

        with (
            patch(
                "syfthub.services.tempo_utils._get_balance_contract",
                return_value=mock_contract,
            ),
            patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls,
        ):
            mock_web3_cls.to_checksum_address.return_value = "0xADDR"
            result = tempo_module._sync_get_balance("0xabc")
            assert result == 0.0


class TestSyncGetTransactions:
    def _make_log(
        self, tx_hash: str, from_addr: str, to_addr: str, value: int, block_number: int
    ):
        log = MagicMock()
        log.transactionHash.hex.return_value = tx_hash
        log.args = {"from": from_addr, "to": to_addr, "value": value}
        log.blockNumber = block_number
        return log

    def test_empty_transactions(self):
        mock_w3 = MagicMock()
        mock_w3.eth.block_number = 1000
        mock_contract = MagicMock()
        mock_contract.events.Transfer.get_logs.return_value = []

        with (
            patch("syfthub.services.tempo_utils._get_w3", return_value=mock_w3),
            patch(
                "syfthub.services.tempo_utils._get_transfer_contract",
                return_value=mock_contract,
            ),
            patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls,
        ):
            mock_web3_cls.to_checksum_address.return_value = "0xADDR"
            result = tempo_module._sync_get_transactions("0xabc")
            assert result == []

    def test_incoming_transaction(self):
        mock_w3 = MagicMock()
        mock_w3.eth.block_number = 1000
        block_mock = MagicMock()
        block_mock.timestamp = 1700000000
        mock_w3.eth.get_block.return_value = block_mock

        incoming_log = self._make_log("0xhash1", "0xSENDER", "0xADDR", 2_000_000, 999)
        mock_contract = MagicMock()
        mock_contract.events.Transfer.get_logs.side_effect = [
            [incoming_log],  # incoming
            [],  # outgoing
        ]

        with (
            patch("syfthub.services.tempo_utils._get_w3", return_value=mock_w3),
            patch(
                "syfthub.services.tempo_utils._get_transfer_contract",
                return_value=mock_contract,
            ),
            patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls,
        ):
            mock_web3_cls.to_checksum_address.return_value = "0xADDR"
            result = tempo_module._sync_get_transactions("0xabc")

            assert len(result) == 1
            assert result[0]["id"] == "0xhash1"
            assert result[0]["amount"] == pytest.approx(2.0)
            assert result[0]["status"] == "confirmed"

    def test_outgoing_transaction(self):
        mock_w3 = MagicMock()
        mock_w3.eth.block_number = 1000
        block_mock = MagicMock()
        block_mock.timestamp = 1700000000
        mock_w3.eth.get_block.return_value = block_mock

        outgoing_log = self._make_log("0xhash2", "0xADDR", "0xRECEIVER", 3_000_000, 998)
        mock_contract = MagicMock()
        mock_contract.events.Transfer.get_logs.side_effect = [
            [],  # incoming
            [outgoing_log],  # outgoing
        ]

        with (
            patch("syfthub.services.tempo_utils._get_w3", return_value=mock_w3),
            patch(
                "syfthub.services.tempo_utils._get_transfer_contract",
                return_value=mock_contract,
            ),
            patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls,
        ):
            mock_web3_cls.to_checksum_address.return_value = "0xADDR"
            result = tempo_module._sync_get_transactions("0xabc")

            assert len(result) == 1
            assert result[0]["id"] == "0xhash2"
            assert result[0]["amount"] == pytest.approx(-3.0)

    def test_get_logs_exception_incoming(self):
        mock_w3 = MagicMock()
        mock_w3.eth.block_number = 1000
        mock_contract = MagicMock()

        # Raise on first call (incoming), return [] on second (outgoing)
        mock_contract.events.Transfer.get_logs.side_effect = [
            Exception("RPC error incoming"),
            [],
        ]

        with (
            patch("syfthub.services.tempo_utils._get_w3", return_value=mock_w3),
            patch(
                "syfthub.services.tempo_utils._get_transfer_contract",
                return_value=mock_contract,
            ),
            patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls,
        ):
            mock_web3_cls.to_checksum_address.return_value = "0xADDR"
            result = tempo_module._sync_get_transactions("0xabc")
            assert result == []

    def test_get_logs_exception_outgoing(self):
        mock_w3 = MagicMock()
        mock_w3.eth.block_number = 1000
        mock_contract = MagicMock()
        mock_contract.events.Transfer.get_logs.side_effect = [
            [],
            Exception("RPC error outgoing"),
        ]

        with (
            patch("syfthub.services.tempo_utils._get_w3", return_value=mock_w3),
            patch(
                "syfthub.services.tempo_utils._get_transfer_contract",
                return_value=mock_contract,
            ),
            patch("syfthub.services.tempo_utils.Web3") as mock_web3_cls,
        ):
            mock_web3_cls.to_checksum_address.return_value = "0xADDR"
            result = tempo_module._sync_get_transactions("0xabc")
            assert result == []


class TestGetWalletBalance:
    @pytest.mark.asyncio
    async def test_returns_balance_on_success(self):
        with (
            patch("syfthub.services.tempo_utils._sync_get_balance", return_value=1.5),
            patch("asyncio.to_thread", new=AsyncMock(return_value=1.5)),
        ):
            result = await get_wallet_balance("0xabc")
            assert result == 1.5

    @pytest.mark.asyncio
    async def test_returns_zero_on_exception(self):
        async def raiser(*args, **kwargs):
            raise Exception("blockchain error")

        with patch("asyncio.to_thread", new=raiser):
            result = await get_wallet_balance("0xabc")
            assert result == 0.0


class TestGetWalletTransactions:
    @pytest.mark.asyncio
    async def test_returns_transactions_on_success(self):
        mock_txs = [{"id": "0xhash", "amount": 1.0}]
        with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_txs)):
            result = await get_wallet_transactions("0xabc")
            assert result == mock_txs

    @pytest.mark.asyncio
    async def test_returns_empty_on_exception(self):
        async def raiser(*args, **kwargs):
            raise Exception("blockchain error")

        with patch("asyncio.to_thread", new=raiser):
            result = await get_wallet_transactions("0xabc")
            assert result == []


class TestTimestampToIso:
    def test_converts_unix_timestamp(self):
        ts = 1700000000
        result = _timestamp_to_iso(ts)
        expected = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        assert result == expected

    def test_zero_timestamp(self):
        result = _timestamp_to_iso(0)
        assert "1970-01-01" in result

    def test_output_is_iso_format(self):
        result = _timestamp_to_iso(1700000000)
        # Should be parseable as ISO 8601
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo is not None
