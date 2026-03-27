#!/usr/bin/env python3
"""
Small Flask backend that runs bitget_api.py and exposes JSON API for the web UI.
Run from project root: python3 web/server.py
"""
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, Tuple

from flask import Flask, request, send_from_directory, jsonify

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
API_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "bitget_api.py")

app = Flask(__name__, static_folder="static", static_url_path="")

_CACHE: Dict[Tuple[str, str], Tuple[float, Any]] = {}


def cached_json(key: Tuple[str, str], ttl_s: int, compute_fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] <= ttl_s:
        return hit[1]
    val = compute_fn()
    _CACHE[key] = (now, val)
    return val


def run_cmd(cmd_list):
    """Run bitget_api.py with args; return parsed JSON or error dict."""
    try:
        result = subprocess.run(
            [sys.executable, API_SCRIPT] + cmd_list,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = result.stdout or result.stderr or ""
        out = out.strip()
        if not out:
            return {"error": "No output from script"}
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {"error": "Invalid response", "raw": out}
    except subprocess.TimeoutExpired:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": str(e)}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/token-price", methods=["POST"])
def api_token_price():
    data = request.get_json() or {}
    chain = (data.get("chain") or "").strip()
    contract = (data.get("contract") or "").strip()
    if not chain:
        return jsonify({"error": "chain is required"}), 400
    args = ["token-price", "--chain", chain, "--contract", contract]
    key = ("token-price", f"{chain}:{contract}")
    return jsonify(cached_json(key, 8, lambda: run_cmd(args)))


@app.route("/api/security", methods=["POST"])
def api_security():
    data = request.get_json() or {}
    chain = (data.get("chain") or "").strip()
    contract = (data.get("contract") or "").strip()
    if not chain or not contract:
        return jsonify({"error": "chain and contract are required"}), 400
    args = ["security", "--chain", chain, "--contract", contract]
    key = ("security", f"{chain}:{contract}")
    return jsonify(cached_json(key, 30, lambda: run_cmd(args)))


@app.route("/api/kline", methods=["POST"])
def api_kline():
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    chain = (data.get("chain") or "").strip()
    contract = (data.get("contract") or "").strip()
    period = (data.get("period") or "1h").strip()
    try:
        size = int(data.get("size") or 24)
    except (TypeError, ValueError):
        size = 24
    size = max(1, min(1440, size))
    if not chain:
        return jsonify({"error": "chain is required"}), 400
    args = ["kline", "--chain", chain, "--contract", contract, "--period", period, "--size", str(size)]
    key = ("kline", f"{chain}:{contract}:{period}:{size}")
    return jsonify(cached_json(key, 20, lambda: run_cmd(args)))


@app.route("/api/swap-quote", methods=["POST"])
def api_swap_quote():
    data = request.get_json() or {}
    from_chain = (data.get("from_chain") or data.get("fromChain") or "").strip()
    from_contract = (data.get("from_contract") or data.get("fromContract") or "").strip()
    to_chain = (data.get("to_chain") or data.get("toChain") or from_chain).strip()
    to_contract = (data.get("to_contract") or data.get("toContract") or "").strip()
    amount = (data.get("amount") or "").strip()
    if not from_chain or not to_contract or not amount:
        return jsonify({"error": "from_chain, to_contract, amount are required"}), 400
    args = [
        "swap-quote",
        "--from-chain", from_chain,
        "--from-contract", from_contract,
        "--to-chain", to_chain,
        "--to-contract", to_contract,
        "--amount", amount,
    ]
    return jsonify(run_cmd(args))


@app.route("/api/swap-calldata", methods=["POST"])
def api_swap_calldata():
    data = request.get_json() or {}
    from_chain = (data.get("from_chain") or data.get("fromChain") or "").strip()
    from_contract = (data.get("from_contract") or data.get("fromContract") or "").strip()
    to_chain = (data.get("to_chain") or data.get("toChain") or from_chain).strip()
    to_contract = (data.get("to_contract") or data.get("toContract") or "").strip()
    amount = (data.get("amount") or "").strip()
    from_address = (data.get("from_address") or data.get("fromAddress") or "").strip()
    to_address = (data.get("to_address") or data.get("toAddress") or "").strip()
    market = (data.get("market") or "").strip()
    slippage = data.get("slippage")
    deadline = data.get("deadline")
    if not all([from_chain, to_contract, amount, from_address, to_address, market]):
        return jsonify({"error": "from_chain, to_contract, amount, from_address, to_address, market are required"}), 400
    args = [
        "swap-calldata",
        "--from-chain", from_chain,
        "--from-contract", from_contract,
        "--to-chain", to_chain,
        "--to-contract", to_contract,
        "--amount", amount,
        "--from-address", from_address,
        "--to-address", to_address,
        "--market", market,
    ]
    if slippage is not None and str(slippage).strip() != "":
        args.extend(["--slippage", str(slippage)])
    if deadline is not None and str(deadline).strip() != "":
        args.extend(["--deadline", str(int(deadline))])
    return jsonify(run_cmd(args))


@app.route("/api/chain-detect", methods=["POST"])
def api_chain_detect():
    """
    Best-effort chain detection for EVM contracts.
    Returns first chain where token-price has symbol/name and price>0.
    """
    data = request.get_json() or {}
    contract = (data.get("contract") or "").strip()
    if not contract:
        return jsonify({"error": "contract is required"}), 400
    chains = data.get("chains") or ["base", "bnb", "arbitrum", "matic", "eth"]
    results = []
    for chain in chains:
        chain = str(chain).strip()
        if not chain:
            continue
        args = ["token-price", "--chain", chain, "--contract", contract]
        key = ("token-price", f"{chain}:{contract}")
        r = cached_json(key, 10, lambda: run_cmd(args))
        sym = r.get("symbol") if isinstance(r, dict) else None
        name = r.get("name") if isinstance(r, dict) else None
        price = r.get("price") if isinstance(r, dict) else None
        ok = bool(sym or name) and isinstance(price, (int, float)) and price > 0
        results.append({"chain": chain, "ok": ok, "symbol": sym, "name": name, "price": price})
        if ok:
            return jsonify({"chain": chain, "symbol": sym, "name": name, "price": price, "candidates": results})
    return jsonify({"chain": None, "candidates": results})


@app.route("/api/order-quote", methods=["POST"])
def api_order_quote():
    data = request.get_json() or {}
    from_chain = (data.get("from_chain") or data.get("fromChain") or "").strip()
    from_contract = (data.get("from_contract") or data.get("fromContract") or "").strip()
    to_chain = (data.get("to_chain") or data.get("toChain") or "").strip()
    to_contract = (data.get("to_contract") or data.get("toContract") or "").strip()
    amount = (data.get("amount") or "").strip()
    from_address = (data.get("from_address") or data.get("fromAddress") or "").strip()
    to_address = (data.get("to_address") or data.get("toAddress") or "").strip()
    if not from_chain or not from_contract or not to_chain or not to_contract or not amount or not from_address:
        return jsonify({"error": "from_chain, from_contract, to_chain, to_contract, amount, from_address are required"}), 400
    args = [
        "order-quote",
        "--from-chain", from_chain,
        "--from-contract", from_contract,
        "--to-chain", to_chain,
        "--to-contract", to_contract,
        "--amount", amount,
        "--from-address", from_address,
    ]
    if to_address:
        args.extend(["--to-address", to_address])
    return jsonify(run_cmd(args))


@app.route("/api/order-create", methods=["POST"])
def api_order_create():
    data = request.get_json() or {}
    from_chain = (data.get("from_chain") or data.get("fromChain") or "").strip()
    from_contract = (data.get("from_contract") or data.get("fromContract") or "").strip()
    to_chain = (data.get("to_chain") or data.get("toChain") or "").strip()
    to_contract = (data.get("to_contract") or data.get("toContract") or "").strip()
    amount = (data.get("amount") or "").strip()
    from_address = (data.get("from_address") or data.get("fromAddress") or "").strip()
    to_address = (data.get("to_address") or data.get("toAddress") or from_address).strip()
    market = (data.get("market") or "").strip()
    slippage = (data.get("slippage") or "1").strip()
    feature = (data.get("feature") or "").strip()
    if not all([from_chain, from_contract, to_chain, to_contract, amount, from_address, market]):
        return jsonify({"error": "from_chain, from_contract, to_chain, to_contract, amount, from_address, market are required"}), 400
    args = [
        "order-create",
        "--from-chain", from_chain,
        "--from-contract", from_contract,
        "--to-chain", to_chain,
        "--to-contract", to_contract,
        "--amount", amount,
        "--from-address", from_address,
        "--to-address", to_address,
        "--market", market,
        "--slippage", slippage,
    ]
    if feature:
        args.extend(["--feature", feature])
    return jsonify(run_cmd(args))


@app.route("/api/order-submit", methods=["POST"])
def api_order_submit():
    data = request.get_json() or {}
    order_id = (data.get("order_id") or data.get("orderId") or "").strip()
    signed_txs = data.get("signed_txs") or data.get("signedTxs") or []
    if isinstance(signed_txs, str):
        signed_txs = [s.strip() for s in signed_txs.replace(",", " ").split() if s.strip()]
    if not order_id or not signed_txs:
        return jsonify({"error": "order_id and signed_txs (array or space/comma-separated string) are required"}), 400
    args = ["order-submit", "--order-id", order_id] + ["--signed-txs"] + list(signed_txs)
    return jsonify(run_cmd(args))


@app.route("/api/order-status", methods=["POST"])
def api_order_status():
    data = request.get_json() or {}
    order_id = (data.get("order_id") or data.get("orderId") or "").strip()
    if not order_id:
        return jsonify({"error": "order_id is required"}), 400
    args = ["order-status", "--order-id", order_id]
    return jsonify(run_cmd(args))

@app.route("/api/rankings", methods=["POST"])
def api_rankings():
    data = request.get_json() or {}
    name = (data.get("name") or "topGainers").strip()
    if name not in ("topGainers", "topLosers"):
        return jsonify({"error": "name must be topGainers or topLosers"}), 400
    args = ["rankings", "--name", name]
    key = ("rankings", name)
    return jsonify(cached_json(key, 20, lambda: run_cmd(args)))


@app.route("/api/tx-info", methods=["POST"])
def api_tx_info():
    data = request.get_json() or {}
    chain = (data.get("chain") or "").strip()
    contract = (data.get("contract") or "").strip()
    if not chain or not contract:
        return jsonify({"error": "chain and contract are required"}), 400
    args = ["tx-info", "--chain", chain, "--contract", contract]
    key = ("tx-info", f"{chain}:{contract}")
    return jsonify(cached_json(key, 15, lambda: run_cmd(args)))


@app.route("/api/liquidity", methods=["POST"])
def api_liquidity():
    data = request.get_json() or {}
    chain = (data.get("chain") or "").strip()
    contract = (data.get("contract") or "").strip()
    if not chain or not contract:
        return jsonify({"error": "chain and contract are required"}), 400
    args = ["liquidity", "--chain", chain, "--contract", contract]
    key = ("liquidity", f"{chain}:{contract}")
    return jsonify(cached_json(key, 30, lambda: run_cmd(args)))


@app.errorhandler(Exception)
def handle_error(e):
    return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5051))
    print(f"Bitget Wallet Web UI: http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
