import json, threading, urllib.request, uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
INDEX = DATA_DIR / "index.json"
LEGACY = BASE / "data.json"
SUFFIX = {"NSE": ".NS", "BSE": ".BO", "US": ""}
app = Flask(__name__)
lock = threading.Lock()


def ensure_store():
    """First run: set up data/index.json and data/<id>.json, migrating any old single-portfolio data.json."""
    DATA_DIR.mkdir(exist_ok=True)
    if not INDEX.exists():
        content = LEGACY.read_text() if LEGACY.exists() else json.dumps({"stocks": []})
        (DATA_DIR / "default.json").write_text(content)
        INDEX.write_text(json.dumps({"portfolios": [{"id": "default", "name": "My Portfolio"}]}, indent=2))


ensure_store()


def load_index():
    return json.loads(INDEX.read_text())


def save_index(idx):
    INDEX.write_text(json.dumps(idx, indent=2))


def pf_path(pid):
    safe = "".join(c for c in pid if c.isalnum() or c in "-_") or "default"
    return DATA_DIR / f"{safe}.json"


def get_pf_id():
    """The ?pf= query param if it names a real portfolio, else the first one in the index."""
    idx = load_index()
    ids = [p["id"] for p in idx["portfolios"]]
    pid = request.args.get("pf", "")
    if pid in ids:
        return pid
    return ids[0] if ids else "default"


def fetch_quote(symbol, exchange):
    """Returns (ltp, prevClose) from Yahoo Finance, or (None, None) on failure."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + symbol + SUFFIX.get(exchange.upper(), ".NS"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            meta = json.load(r)["chart"]["result"][0]["meta"]
            ltp = float(meta["regularMarketPrice"])
            prev = meta.get("previousClose") or meta.get("chartPreviousClose")
            return ltp, (float(prev) if prev is not None else None)
    except Exception:
        return None, None


def fetch_dividends(symbol, exchange):
    """Returns a list of {date, amount} dividend payouts (ex-dividend date), oldest first, or None on failure."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + symbol + SUFFIX.get(exchange.upper(), ".NS")
           + "?range=10y&interval=1mo&events=div")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.load(r)["chart"]["result"][0]
            evs = ((result.get("events") or {}).get("dividends") or {}).values()
            out = [{"date": datetime.utcfromtimestamp(v["date"]).strftime("%Y-%m-%d"), "amount": float(v["amount"])} for v in evs]
            out.sort(key=lambda x: x["date"])
            return out
    except Exception:
        return None


# ---- Pages ----

@app.get("/")
def landing():
    return send_from_directory(BASE, "portfolios.html")


@app.get("/dashboard")
def dashboard():
    return send_from_directory(BASE, "index.html")


@app.get("/pnl")
def pnl():
    return send_from_directory(BASE, "pnl.html")


@app.get("/booked")
def booked():
    return send_from_directory(BASE, "booked.html")


@app.get("/returns")
def returns():
    return send_from_directory(BASE, "returns.html")


@app.get("/download")
def download():
    return send_from_directory(BASE, "download.html")


@app.get("/dividend")
def dividend():
    return send_from_directory(BASE, "dividend.html")


@app.get("/common.js")
def common_js():
    return send_from_directory(BASE, "common.js")


@app.get("/style.css")
def style_css():
    return send_from_directory(BASE, "style.css")


@app.get("/theme.css")
def theme_css():
    return send_from_directory(BASE, "theme.css")


# ---- Portfolio management ----

@app.get("/api/portfolios")
def list_portfolios():
    idx = load_index()
    out = []
    for p in idx["portfolios"]:
        try:
            n = len(json.loads(pf_path(p["id"]).read_text()).get("stocks", []))
        except Exception:
            n = 0
        out.append({"id": p["id"], "name": p["name"], "stocks": n})
    return jsonify(portfolios=out)


@app.post("/api/portfolios")
def create_portfolio():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip() or "New portfolio"
    pid = uuid.uuid4().hex[:8]
    with lock:
        idx = load_index()
        idx["portfolios"].append({"id": pid, "name": name})
        save_index(idx)
        pf_path(pid).write_text(json.dumps({"stocks": []}, indent=2))
    return jsonify(id=pid, name=name)


@app.put("/api/portfolios/<pid>")
def rename_portfolio(pid):
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify(ok=False, error="Name can't be empty."), 400
    with lock:
        idx = load_index()
        for p in idx["portfolios"]:
            if p["id"] == pid:
                p["name"] = name
                save_index(idx)
                return jsonify(ok=True)
    return jsonify(ok=False, error="Portfolio not found."), 404


@app.delete("/api/portfolios/<pid>")
def delete_portfolio(pid):
    with lock:
        idx = load_index()
        if len(idx["portfolios"]) <= 1:
            return jsonify(ok=False, error="Can't delete your only portfolio."), 400
        before = len(idx["portfolios"])
        idx["portfolios"] = [p for p in idx["portfolios"] if p["id"] != pid]
        if len(idx["portfolios"]) == before:
            return jsonify(ok=False, error="Portfolio not found."), 404
        save_index(idx)
        try:
            pf_path(pid).unlink()
        except FileNotFoundError:
            pass
    return jsonify(ok=True)


# ---- Portfolio data (scoped to ?pf=<id>) ----

@app.get("/api/portfolio")
def get_portfolio():
    p = pf_path(get_pf_id())
    if not p.exists():
        p.write_text(json.dumps({"stocks": []}))
    return jsonify(json.loads(p.read_text()))


@app.put("/api/portfolio")
def put_portfolio():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("stocks"), list):
        return jsonify(ok=False, error="Expected an object with a 'stocks' list."), 400
    with lock:
        pf_path(get_pf_id()).write_text(json.dumps(body, indent=2))
    return jsonify(ok=True)


@app.post("/api/refresh")
def refresh():
    p = pf_path(get_pf_id())
    with lock:
        pf = json.loads(p.read_text())
        now = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
        failed = []
        for s in pf["stocks"]:
            ltp, prev = fetch_quote(s["symbol"], s.get("exchange", "NSE"))
            if ltp is None:
                failed.append(s["symbol"])
            else:
                s["ltp"], s["refreshed"] = ltp, now
                if prev is not None:
                    s["prevClose"] = prev
        p.write_text(json.dumps(pf, indent=2))
    return jsonify(portfolio=pf, failed=failed)


@app.post("/api/dividends/refresh")
def refresh_dividends():
    p = pf_path(get_pf_id())
    with lock:
        pf = json.loads(p.read_text())
        now = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
        failed = []
        for s in pf["stocks"]:
            divs = fetch_dividends(s["symbol"], s.get("exchange", "NSE"))
            if divs is None:
                failed.append(s["symbol"])
            else:
                s["dividends"], s["dividendsRefreshed"] = divs, now
        p.write_text(json.dumps(pf, indent=2))
    return jsonify(portfolio=pf, failed=failed)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
