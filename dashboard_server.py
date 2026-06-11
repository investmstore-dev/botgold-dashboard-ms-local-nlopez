"""
Dashboard local — BOT Mining Store GOLD
Ejecutar: python dashboard_server.py
Abrir:    http://localhost:5050
"""
import json
import sqlite3
import os
import re
import sys
import signal
import subprocess
from pathlib import Path
from datetime import datetime, timezone, date
from flask import Flask, jsonify, send_from_directory, request

app = Flask(__name__, static_folder=".", template_folder=".")

ACCOUNTS_FILE = Path(__file__).parent / "accounts.json"
DASHBOARD_HTML = Path(__file__).parent / "dashboard.html"
BOT_SCRIPT    = Path(__file__).parent / "main.py"   # entry point del bot

# ── Procesos bot activos: { account_id: subprocess.Popen } ───────────────────
_bot_processes: dict[str, subprocess.Popen] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_accounts() -> list:
    if not ACCOUNTS_FILE.exists():
        return []
    return json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))


def _save_accounts(accounts: list) -> None:
    ACCOUNTS_FILE.write_text(
        json.dumps(accounts, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def _slug(name: str) -> str:
    """Genera un id unico a partir del nombre de cuenta."""
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    existing = {a["id"] for a in _load_accounts()}
    cand, n = base, 1
    while cand in existing:
        cand = f"{base}_{n}"; n += 1
    return cand


def _read_status(status_file: str) -> dict:
    p = Path(status_file)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _query_db(db_path: str, sql: str, params=()) -> list:
    p = Path(db_path)
    if not p.is_absolute():
        p = Path(__file__).parent / db_path
    if not p.exists():
        return []
    try:
        con = sqlite3.connect(str(p))
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _is_running(acc_id: str) -> bool:
    proc = _bot_processes.get(acc_id)
    if proc is None:
        return False
    if proc.poll() is not None:
        _bot_processes.pop(acc_id, None)
        return False
    return True


def _account_data(acc: dict) -> dict:
    db   = acc["db_path"]
    sf   = acc["status_file"]
    init = float(acc["initial_balance"])
    tgt  = float(acc["target_pct"])
    ddl  = float(acc["daily_loss_limit_pct"])
    mdd  = float(acc["max_dd_pct"])

    status  = _read_status(sf)
    balance = float(status.get("balance", 0) or 0)
    equity  = float(status.get("equity",  0) or 0)
    ea_up   = status.get("state") == "running"

    trades  = _query_db(db, "SELECT * FROM trades ORDER BY timestamp DESC")
    open_t  = [t for t in trades if t.get("status") == "open"]
    closed  = [t for t in trades if t.get("status") == "closed"]

    pnl_total = sum(t.get("pnl") or 0 for t in closed)
    wins      = [t for t in closed if (t.get("pnl") or 0) > 0]
    losses    = [t for t in closed if (t.get("pnl") or 0) <= 0]
    win_rate  = round(len(wins) / len(closed) * 100, 1) if closed else 0
    avg_win   = round(sum(t.get("pnl",0) for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss  = round(sum(t.get("pnl",0) for t in losses) / len(losses), 2) if losses else 0
    pf_num    = sum(t.get("pnl",0) for t in wins)
    pf_den    = abs(sum(t.get("pnl",0) for t in losses))
    pf        = round(pf_num / pf_den, 2) if pf_den > 0 else 0

    streak = cur_streak = 0
    for t in reversed(closed):
        if (t.get("pnl") or 0) <= 0:
            cur_streak += 1; streak = max(streak, cur_streak)
        else:
            cur_streak = 0

    working      = init + pnl_total
    progress_pct = round((working - init) / init * 100, 2) if init > 0 else 0
    remaining_pct= round(tgt - progress_pct, 2)

    today = date.today().isoformat()
    daily_rows  = _query_db(db,
        "SELECT COALESCE(SUM(pnl),0) as dp FROM trades WHERE status='closed' AND DATE(timestamp)=?",
        (today,))
    daily_pnl   = float(daily_rows[0]["dp"]) if daily_rows else 0
    daily_loss_used = round(abs(min(0, daily_pnl)) / init * 100, 2) if init > 0 else 0

    daily_nav   = _query_db(db, "SELECT date, nav FROM daily_log WHERE nav IS NOT NULL ORDER BY date")
    eq_vals     = [r["nav"] for r in daily_nav if r["nav"]]
    max_dd      = 0.0
    if eq_vals:
        peak = eq_vals[0]
        for v in eq_vals:
            if v > peak: peak = v
            dd = (v - peak) / peak * 100
            if dd < max_dd: max_dd = dd
    max_dd = round(max_dd, 2)

    burned = (max_dd < -mdd) or (daily_loss_used > ddl)

    spark = _query_db(db,
        "SELECT date, nav FROM daily_log WHERE nav IS NOT NULL ORDER BY date DESC LIMIT 60")
    spark = list(reversed(spark))

    open_detail = []
    for t in open_t:
        entry      = float(t.get("entry_price") or 0)
        sl         = float(t.get("stop_loss") or 0)
        live_price = float(status.get("current_price", 0) or 0)
        unrealized = 0.0
        if live_price and entry:
            unrealized = (live_price - entry) * float(t.get("units") or 0) \
                         if t.get("direction") == "long" \
                         else (entry - live_price) * float(t.get("units") or 0)
        open_detail.append({
            "id": t.get("id"), "timestamp": t.get("timestamp","")[:16],
            "direction": t.get("direction",""), "units": t.get("units",0),
            "entry": round(entry,2), "sl": round(sl,2),
            "live": round(live_price,2), "unrealized": round(unrealized,2),
            "rsi": round(float(t.get("rsi") or 0),1),
            "adx": round(float(t.get("adx") or 0),1),
        })

    return {
        "id": acc["id"], "name": acc["name"], "phase": acc["phase"],
        "initial": init, "target_pct": tgt,
        "daily_limit": ddl, "max_dd_limit": mdd,
        "balance": round(balance,2), "equity": round(equity,2),
        "ea_up": ea_up,
        "bot_running": _is_running(acc["id"]),
        "working": round(working,2), "progress_pct": progress_pct,
        "remaining_pct": max(0, remaining_pct), "pnl_total": round(pnl_total,2),
        "daily_pnl": round(daily_pnl,2), "daily_loss_used": daily_loss_used,
        "max_dd": max_dd, "burned": burned,
        "trades_total": len(closed), "trades_open": len(open_t),
        "win_rate": win_rate, "avg_win": avg_win, "avg_loss": avg_loss,
        "profit_factor": pf, "loss_streak": streak,
        "open_positions": open_detail,
        "recent_trades": [
            {"id": t.get("id"), "date": t.get("timestamp","")[:10],
             "direction": t.get("direction",""),
             "entry": round(float(t.get("entry_price") or 0),2),
             "exit":  round(float(t.get("exit_price")  or 0),2),
             "pnl":   round(float(t.get("pnl")         or 0),2),
             "rsi":   round(float(t.get("rsi")         or 0),1),
             "adx":   round(float(t.get("adx")         or 0),1),
            } for t in closed[:15]
        ],
        "spark_vals":  [r["nav"]  for r in spark],
        "spark_dates": [r["date"] for r in spark],
    }


# ── API — datos ───────────────────────────────────────────────────────────────

@app.route("/api/data")
def api_data():
    accounts     = _load_accounts()
    result       = []
    burned_total = 0
    for acc in accounts:
        try:
            d = _account_data(acc)
            if d["burned"]: burned_total += 1
            result.append(d)
        except Exception as e:
            result.append({"id": acc["id"], "name": acc["name"], "error": str(e),
                           "bot_running": _is_running(acc["id"])})

    now      = datetime.now(timezone.utc)
    h4_hours = [1, 5, 9, 13, 17, 21]
    next_run = None
    for h in h4_hours + [h4_hours[0] + 24]:
        from datetime import timedelta
        candidate = now.replace(hour=h % 24, minute=5, second=0, microsecond=0)
        if h >= 24:
            candidate += timedelta(days=1)
        if candidate > now:
            next_run = candidate.isoformat(); break

    return jsonify({
        "accounts": result, "burned_total": burned_total,
        "server_time": now.isoformat(), "next_run": next_run,
    })


# ── API — CRUD cuentas ────────────────────────────────────────────────────────

@app.route("/api/accounts", methods=["GET"])
def get_accounts():
    return jsonify(_load_accounts())


@app.route("/api/accounts", methods=["POST"])
def add_account():
    body = request.get_json(force=True)
    required = ["name", "initial_balance", "target_pct",
                "daily_loss_limit_pct", "max_dd_pct", "db_path", "status_file"]
    missing = [f for f in required if f not in body]
    if missing:
        return jsonify({"error": f"Campos faltantes: {missing}"}), 400

    acc = {
        "id":                   _slug(body["name"]),
        "name":                 str(body["name"]),
        "initial_balance":      float(body["initial_balance"]),
        "target_pct":           float(body["target_pct"]),
        "daily_loss_limit_pct": float(body["daily_loss_limit_pct"]),
        "max_dd_pct":           float(body["max_dd_pct"]),
        "phase":                int(body.get("phase", 1)),
        "db_path":              str(body["db_path"]),
        "status_file":          str(body["status_file"]),
    }
    accounts = _load_accounts()
    accounts.append(acc)
    _save_accounts(accounts)
    return jsonify(acc), 201


@app.route("/api/accounts/<acc_id>", methods=["PUT"])
def update_account(acc_id):
    body     = request.get_json(force=True)
    accounts = _load_accounts()
    idx      = next((i for i, a in enumerate(accounts) if a["id"] == acc_id), None)
    if idx is None:
        return jsonify({"error": "Cuenta no encontrada"}), 404

    acc = accounts[idx]
    for field in ["name", "initial_balance", "target_pct",
                  "daily_loss_limit_pct", "max_dd_pct", "phase",
                  "db_path", "status_file"]:
        if field in body:
            acc[field] = type(acc[field])(body[field])
    accounts[idx] = acc
    _save_accounts(accounts)
    return jsonify(acc)


@app.route("/api/accounts/<acc_id>", methods=["DELETE"])
def delete_account(acc_id):
    if _is_running(acc_id):
        return jsonify({"error": "Detener el bot antes de eliminar la cuenta"}), 409
    accounts = _load_accounts()
    accounts = [a for a in accounts if a["id"] != acc_id]
    _save_accounts(accounts)
    return jsonify({"ok": True})


# ── API — control bot ─────────────────────────────────────────────────────────

@app.route("/api/accounts/<acc_id>/start", methods=["POST"])
def start_bot(acc_id):
    if _is_running(acc_id):
        return jsonify({"ok": True, "status": "already_running"})

    accounts = _load_accounts()
    acc = next((a for a in accounts if a["id"] == acc_id), None)
    if acc is None:
        return jsonify({"error": "Cuenta no encontrada"}), 404

    # Lanzar bot.py como subproceso pasando el id de cuenta como argumento
    bot_dir = Path(__file__).parent
    env = os.environ.copy()
    env["GOLDBOT_ACCOUNT_ID"] = acc_id

    try:
        proc = subprocess.Popen(
            [sys.executable, str(BOT_SCRIPT), "--account", acc_id],
            cwd=str(bot_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        _bot_processes[acc_id] = proc
        return jsonify({"ok": True, "status": "started", "pid": proc.pid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/accounts/<acc_id>/stop", methods=["POST"])
def stop_bot(acc_id):
    proc = _bot_processes.get(acc_id)
    if proc is None or proc.poll() is not None:
        _bot_processes.pop(acc_id, None)
        return jsonify({"ok": True, "status": "already_stopped"})
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    _bot_processes.pop(acc_id, None)
    return jsonify({"ok": True, "status": "stopped"})


# ── Sirve dashboard ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(Path(__file__).parent), "dashboard.html")


if __name__ == "__main__":
    print()
    print("  BOT Mining Store GOLD — Dashboard")
    print("  Abre tu navegador en: http://localhost:5050")
    print()
    app.run(host="0.0.0.0", port=5050, debug=False)
