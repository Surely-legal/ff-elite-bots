import sys
import os
import json
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tradovate
import pine_strategy as ps
import live_trader


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(recorder, routes):
    """routes: list of (substr, payload). Records each Request object."""
    def _open(req, timeout=None):
        url = req.full_url
        recorder.append(req)
        for substr, payload in routes:
            if substr in url:
                if isinstance(payload, Exception):
                    raise payload
                return FakeResponse(payload)
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)
    return _open


def make_client(**overrides):
    cfg = tradovate.TradovateConfig(
        env="demo", username="u", password="p", cid=123, secret="s",
        device_id="dev", dry_run=False, **overrides)
    return tradovate.TradovateClient(cfg)


AUTH_OK = {
    "accessToken": "tok123",
    "expirationTime": "2999-01-01T00:00:00.000Z",
    "userId": 1,
}


class TestAuth(unittest.TestCase):
    def test_authenticate_body_and_bearer(self):
        calls = []
        routes = [
            ("accesstokenrequest", AUTH_OK),
            ("account/list", [{"id": 42, "name": "DEMO1"}]),
        ]
        client = make_client()
        with patch("urllib.request.urlopen", fake_urlopen(calls, routes)):
            client.authenticate()
            acct = client.account()
        self.assertEqual(acct["id"], 42)
        auth_body = json.loads(calls[0].data.decode())
        for k in ("name", "password", "appId", "appVersion", "cid", "sec", "deviceId"):
            self.assertIn(k, auth_body)
        self.assertEqual(auth_body["name"], "u")
        self.assertEqual(auth_body["cid"], 123)
        self.assertEqual(calls[1].get_header("Authorization"), "Bearer tok123")

    def test_p_ticket_raises(self):
        calls = []
        routes = [("accesstokenrequest",
                   {"p-ticket": "abc", "p-time": 90, "p-caption": "CAPTCHA"})]
        client = make_client()
        with patch("urllib.request.urlopen", fake_urlopen(calls, routes)):
            with self.assertRaises(tradovate.TradovateError) as ctx:
                client.authenticate()
        self.assertIn("90", str(ctx.exception))


class TestOrders(unittest.TestCase):
    def setUp(self):
        self.calls = []
        routes = [
            ("accesstokenrequest", AUTH_OK),
            ("account/list", [{"id": 42, "name": "DEMO1"}]),
            ("placeoso", {"orderId": 1, "failureText": ""}),
            ("placeorder", {"orderId": 2}),
        ]
        self.client = make_client()
        p = fake_urlopen(self.calls, routes)
        self.patcher = patch("urllib.request.urlopen", p)
        self.patcher.start()
        self.client.authenticate()

    def tearDown(self):
        self.patcher.stop()

    def last_body(self):
        return json.loads(self.calls[-1].data.decode())

    def test_place_bracket(self):
        self.client.place_bracket("ESZ5", "Buy", 1, 6100.0, 5950.0)
        req = self.calls[-1]
        self.assertIn("/order/placeoso", req.full_url)
        body = self.last_body()
        self.assertEqual(body["accountSpec"], "DEMO1")
        self.assertEqual(body["accountId"], 42)
        self.assertEqual(body["action"], "Buy")
        self.assertEqual(body["orderType"], "Market")
        self.assertTrue(body["isAutomated"])
        self.assertEqual(body["bracket1"]["action"], "Sell")
        self.assertEqual(body["bracket1"]["orderType"], "Limit")
        self.assertEqual(body["bracket1"]["price"], 6100.0)
        self.assertEqual(body["bracket2"]["action"], "Sell")
        self.assertEqual(body["bracket2"]["orderType"], "Stop")
        self.assertEqual(body["bracket2"]["stopPrice"], 5950.0)

    def test_submit_signal_one_oso_per_tp(self):
        sig = ps.Signal(side="long", entry=6000.0, stop=5950.0,
                        tps=[6100.0, 6120.0, 6150.0], qty=3, bar_t=1)
        before = len(self.calls)
        resps = self.client.submit_signal("ESZ5", sig)
        self.assertEqual(len(resps), 3)
        new = [r for r in self.calls[before:] if "/order/placeoso" in r.full_url]
        self.assertEqual(len(new), 3)
        prices = [json.loads(r.data.decode())["bracket1"]["price"] for r in new]
        self.assertEqual(prices, [6100.0, 6120.0, 6150.0])


class TestDryRun(unittest.TestCase):
    def test_dry_run_no_network(self):
        cfg = tradovate.TradovateConfig(dry_run=True)
        client = tradovate.TradovateClient(cfg)

        def boom(*a, **k):
            raise AssertionError("network call made in dry-run mode")

        with patch("urllib.request.urlopen", boom):
            client.authenticate()
            sig = ps.Signal(side="short", entry=6000.0, stop=6050.0,
                            tps=[5950.0, 5900.0], qty=2, bar_t=1)
            resps = client.submit_signal("ESZ5", sig)
        self.assertEqual(len(resps), 2)
        self.assertTrue(all(r.get("dryRun") for r in resps))


class TestSimulateFills(unittest.TestCase):
    def _trader(self):
        cfg = tradovate.TradovateConfig(dry_run=True)
        import tempfile
        td = tempfile.mkdtemp()
        return live_trader.LiveTrader(
            tradovate.TradovateClient(cfg),
            state_file=os.path.join(td, "state.json"))

    def _open_long(self, trader):
        m = trader._mkt("ES")
        m["position"] = "long"
        m["last_signal"] = {"side": "long", "entry": 6000.0,
                            "stop": 5950.0, "tps": [6100.0, 6150.0]}
        m["remaining_tps"] = [6100.0, 6150.0]
        return m

    def bar(self, h, l, c=None):
        c = c if c is not None else (h + l) / 2
        return {"t": 1, "o": c, "h": h, "l": l, "c": c, "v": 1}

    def test_long_stop_hit_goes_flat(self):
        t = self._trader()
        m = self._open_long(t)
        t._simulate_fills("ES", self.bar(6010, 5940))
        self.assertIsNone(m["position"])
        self.assertEqual(m["remaining_tps"], [])

    def test_long_all_tps_flat(self):
        t = self._trader()
        m = self._open_long(t)
        t._simulate_fills("ES", self.bar(6120, 5990))   # fills TP1 only
        self.assertEqual(m["position"], "long")
        self.assertEqual(m["remaining_tps"], [6150.0])
        t._simulate_fills("ES", self.bar(6160, 5990))   # fills TP2
        self.assertIsNone(m["position"])
        self.assertEqual(m["remaining_tps"], [])

    def test_long_partial_tp_stays_long(self):
        t = self._trader()
        m = self._open_long(t)
        t._simulate_fills("ES", self.bar(6050, 5990))   # no fills
        self.assertEqual(m["position"], "long")
        self.assertEqual(m["remaining_tps"], [6100.0, 6150.0])
        t._simulate_fills("ES", self.bar(6110, 5990))   # TP1 only
        self.assertEqual(m["position"], "long")
        self.assertEqual(m["remaining_tps"], [6150.0])


class _FakeTrader:
    def __init__(self):
        self.cfg = ps.PineConfig()
        self.routed = []

    def route_signal(self, code, result):
        self.routed.append((code, result))
        return [{"ok": True}]


class TestWebhook(unittest.TestCase):
    def test_bad_token_rejected(self):
        old = live_trader.WEBHOOK_TOKEN
        live_trader.WEBHOOK_TOKEN = "secret"
        try:
            trader = _FakeTrader()
            status, resp = live_trader.handle_webhook(
                {"token": "wrong", "code": "ES", "action": "long"}, trader)
            self.assertEqual(status, 401)
            self.assertEqual(trader.routed, [])
            # also rejected when token unset entirely
            live_trader.WEBHOOK_TOKEN = ""
            status, _ = live_trader.handle_webhook(
                {"token": "", "code": "ES", "action": "long"}, trader)
            self.assertEqual(status, 401)
        finally:
            live_trader.WEBHOOK_TOKEN = old


if __name__ == "__main__":
    unittest.main()
