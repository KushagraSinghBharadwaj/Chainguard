import httpx

from app.providers.etherscan import EtherscanClient, Throttle


def test_end_block_is_sent_to_etherscan():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"status": "1", "message": "OK", "result": []})

    client = EtherscanClient(
        "test-key-not-real",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(1000.0),
    )
    client.get_transactions(1, "0x" + "a" * 40, end_block=123)
    client.get_token_transfers(1, "0x" + "a" * 40)
    assert seen[0]["endblock"] == "123"
    assert seen[1]["endblock"] == "99999999"
