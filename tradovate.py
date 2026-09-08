#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tradovate.py -- minimal Tradovate REST client, standard library only.

Auth: POST /auth/accesstokenrequest with an API key pair (cid/sec) from
Tradovate -> Application Settings -> API Access. Tokens are renewed via
/auth/renewaccesstoken when within 5 minutes of expiry.

Set TRADOVATE_DRY_RUN=1 (the default) to log payloads instead of sending them.
"""

import json
import os
import socket
import time
import uuid
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone


def sp(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


class TradovateError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"Tradovate HTTP {status}: {body}")


@dataclass
class TradovateConfig:
    env: str = "demo"
    username: str = ""
    password: str = ""
    app_id: str = "FFEliteBots"
    app_version: str = "1.0"
    cid: int = 0
    secret: str = ""
    device_id: str = ""
    account_id: int = 0
    dry_run: bool = True

    @classmethod
    def from_env(cls):
        hostname = socket.gethostname() or "unknown"
        default_device = str(uuid.uuid5(uuid.NAMESPACE_DNS, "ff-elite-bots." + hostname))
        return cls(
            env=os.environ.get("TRADOVATE_ENV", "demo"),
            username=os.environ.get("TRADOVATE_USERNAME", ""),
            password=os.environ.get("TRADOVATE_PASSWORD", ""),
            app_id=os.environ.get("TRADOVATE_APP_ID", "FFEliteBots"),
            app_version=os.environ.get("TRADOVATE_APP_VERSION", "1.0"),
            cid=int(os.environ.get("TRADOVATE_CID", "0") or 0),
            secret=os.environ.get("TRADOVATE_SECRET", ""),
            device_id=os.environ.get("TRADOVATE_DEVICE_ID", default_device),
            account_id=int(os.environ.get("TRADOVATE_ACCOUNT_ID", "0") or 0),
            dry_run=os.environ.get("TRADOVATE_DRY_RUN", "1") != "0",
        )

    @property
    def base_url(self):
        if self.env == "live":
            return "https://live.tradovateapi.com/v1"
        return "https://demo.tradovateapi.com/v1"


def _expiry_epoch(ts):
    # Tradovate expirationTime looks like "2024-01-01T12:00:00.000Z" or with offset
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


class TradovateClient:
    def __init__(self, config=None):
        self.cfg = config or TradovateConfig.from_env()
        self.access_token = None
        self.token_expiry = 0.0
        self._account = None

    # ── transport ──────────────────────────────────────────────────────

    def _raw_request(self, method, url, body=None, token=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise TradovateError(e.code, e.read().decode("utf-8", errors="replace"))
        return json.loads(text) if text else {}

    def _request(self, method, path, body=None, params=None, _retried=False):
        url = self.cfg.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        if self.cfg.dry_run:
            sp(f"  [DRY] {method} {url}  {json.dumps(body) if body else ''}")
            return {"dryRun": True, "method": method, "url": url, "body": body}
        self._ensure_token()
        try:
            return self._raw_request(method, url, body, self.access_token)
        except TradovateError as e:
            if e.status == 401 and not _retried:
                self.access_token = None
                self.authenticate()
                return self._request(method, path, body, params, _retried=True)
            raise

    def _ensure_token(self):
        if not self.access_token:
            self.authenticate()
        elif self.token_expiry - time.time() < 300:
            try:
                d = self._raw_request("POST", self.cfg.base_url + "/auth/renewaccesstoken",
                                      {}, self.access_token)
                self._store_token(d)
            except TradovateError:
                self.access_token = None
                self.authenticate()

    # ── auth ───────────────────────────────────────────────────────────

    def _store_token(self, d):
        if "p-ticket" in d:
            raise TradovateError(403,
                f"Tradovate auth penalty/captcha required: {d.get('p-caption','')}. "
                f"Retry after {d.get('p-time', 0)}s.")
        self.access_token = d.get("accessToken")
        self.token_expiry = _expiry_epoch(d.get("expirationTime"))

    def authenticate(self):
        if self.cfg.dry_run:
            self.access_token = "dry-run"
            self.token_expiry = float("inf")
            return
        body = {
            "name": self.cfg.username,
            "password": self.cfg.password,
            "appId": self.cfg.app_id,
            "appVersion": self.cfg.app_version,
            "cid": self.cfg.cid,
            "sec": self.cfg.secret,
            "deviceId": self.cfg.device_id,
        }
        d = self._raw_request("POST", self.cfg.base_url + "/auth/accesstokenrequest", body)
        self._store_token(d)
        sp("  [TRADOVATE] Authenticated (%s env)" % self.cfg.env)

    # ── account / contracts ────────────────────────────────────────────

    def account(self):
        if self._account:
            return self._account
        if self.cfg.dry_run:
            self._account = {"id": self.cfg.account_id or 0, "name": "dry-run"}
            return self._account
        accounts = self._request("GET", "/account/list")
        if isinstance(accounts, dict):
            accounts = accounts.get("d") or []
        accounts = accounts or []
        if self.cfg.account_id:
            for a in accounts:
                if a.get("id") == self.cfg.account_id:
                    self._account = a
                    break
            if not self._account:
                raise TradovateError(404, f"account id {self.cfg.account_id} not found")
        elif accounts:
            self._account = accounts[0]
        else:
            raise TradovateError(404, "no accounts returned by /account/list")
        return self._account

    def find_contract(self, symbol):
        return self._request("GET", "/contract/find", params={"name": symbol})

    def suggest_contract(self, root):
        d = self._request("GET", "/contract/suggest", params={"t": root, "l": 10})
        for c in d or []:
            name = c.get("name", "")
            if name.startswith(root):
                return name
        return None

    # ── orders ─────────────────────────────────────────────────────────

    def _order_base(self, action, qty, order_type, price=None, stop_price=None):
        acct = self.account()
        body = {
            "accountSpec": acct.get("name"),
            "accountId": acct.get("id"),
            "action": action,
            "orderQty": qty,
            "orderType": order_type,
            "isAutomated": True,
        }
        if price is not None:
            body["price"] = price
        if stop_price is not None:
            body["stopPrice"] = stop_price
        return body

    def place_order(self, symbol, action, qty, order_type="Market",
                    price=None, stop_price=None):
        body = self._order_base(action, qty, order_type, price, stop_price)
        body["symbol"] = symbol
        return self._request("POST", "/order/placeorder", body)

    def place_bracket(self, symbol, action, qty, take_profit, stop_loss):
        opposite = "Sell" if action == "Buy" else "Buy"
        body = self._order_base(action, qty, "Market")
        body["symbol"] = symbol
        body["bracket1"] = {"action": opposite, "orderType": "Limit",
                            "price": take_profit}
        body["bracket2"] = {"action": opposite, "orderType": "Stop",
                            "stopPrice": stop_loss}
        return self._request("POST", "/order/placeoso", body)

    # ── positions / order management ───────────────────────────────────

    def positions(self):
        d = self._request("GET", "/position/list")
        return d or []

    def liquidate(self, contract_id):
        acct = self.account()
        return self._request("POST", "/order/liquidateposition",
                             {"accountId": acct.get("id"),
                              "contractId": contract_id,
                              "admin": False})

    def cancel_all_orders(self, contract_id=None):
        orders = self._request("GET", "/order/list") or []
        cancelled = []
        working = {"Working", "Accepted", "Suspended", "Triggered"}
        for o in orders:
            status = o.get("ordStatus") or o.get("status")
            if contract_id is not None and o.get("contractId") != contract_id:
                continue
            if status in working:
                cancelled.append(self._request("POST", "/order/cancelorder",
                                               {"orderId": o.get("id")}))
        return cancelled

    # ── strategy helper ────────────────────────────────────────────────

    def submit_signal(self, symbol, signal):
        # Mirrors the Pine: one entry of `qty` contracts, each contract gets
        # its own TP bracket, all sharing the same stop.
        action = "Buy" if signal.side == "long" else "Sell"
        responses = []
        for tp in signal.tps:
            responses.append(self.place_bracket(symbol, action, 1, tp, signal.stop))
        return responses
