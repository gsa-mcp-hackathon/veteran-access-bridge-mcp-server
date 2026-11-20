import unittest

from veteran_access_bridge.mcp.app import validate_transport


class MCPTransportGuardTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # stdio is always allowed
    # ------------------------------------------------------------------

    def test_stdio_is_allowed(self) -> None:
        validate_transport("stdio")

    def test_stdio_is_allowed_regardless_of_api_key(self) -> None:
        validate_transport("stdio", api_key="")
        validate_transport("stdio", api_key="some-key")

    # ------------------------------------------------------------------
    # streamable-http: fails closed without a key
    # ------------------------------------------------------------------

    def test_streamable_http_without_key_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "VAB_MCP_API_KEY"):
            validate_transport("streamable-http")

    def test_streamable_http_with_empty_key_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "VAB_MCP_API_KEY"):
            validate_transport("streamable-http", api_key="")

    def test_streamable_http_with_whitespace_only_key_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "VAB_MCP_API_KEY"):
            validate_transport("streamable-http", api_key="   ")

    def test_streamable_http_with_valid_key_passes(self) -> None:
        # Must not raise when a non-empty key is supplied.
        validate_transport("streamable-http", api_key="demo-hackathon-secret")

    # ------------------------------------------------------------------
    # Other / unsupported transports remain rejected
    # ------------------------------------------------------------------

    def test_http_alias_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unsupported transport"):
            validate_transport("http")

    def test_sse_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unsupported transport"):
            validate_transport("sse")

    def test_unknown_transport_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unsupported transport"):
            validate_transport("websocket")


if __name__ == "__main__":
    unittest.main()
