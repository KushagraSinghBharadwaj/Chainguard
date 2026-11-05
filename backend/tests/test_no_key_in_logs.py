import logging

import httpx

from app.providers.etherscan import EtherscanClient, Throttle


def test_http_library_does_not_log_the_api_key(caplog):
    key = "secret-key-for-log-test"
    body = {"status": "0", "message": "No transactions found", "result": []}
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    client = EtherscanClient(key, http=http, throttle=Throttle(1000.0))
    client.get_transactions(1, "0x" + "a" * 40)
    assert key not in caplog.text
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
