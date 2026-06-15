# -*- coding: utf-8 -*-
"""
SQLite 영속 스토어 — 멀티펀드.

라이브 가격은 메모리(워커), 여기엔 '영속이 필요한 것'만:
  funds       펀드 메타
  votes       펀드별 참여자 투표
  nav_history 펀드별 NAV 스냅샷
  allowlist   Private 펀드 허용 지갑(주소 저장만, 인증은 5차)
"""
import os
import json
import time
import sqlite3
import threading

_DB_PATH = os.path.join(os.path.dirname(__file__), 'governance.db')
_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _lock, _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS funds (
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            kind         TEXT NOT NULL DEFAULT 'demo',   -- demo | real
            visibility   TEXT NOT NULL DEFAULT 'public',  -- public | private
            creator      TEXT,                            -- 닉네임/클라이언트ID
            profile      TEXT NOT NULL DEFAULT 'aggressive',
            leverage     INTEGER,
            initial_deposit REAL NOT NULL DEFAULT 100000,
            max_deposit  REAL,
            universe     TEXT NOT NULL,                   -- JSON [symbol,...]
            init_weights TEXT,                            -- JSON {symbol: w}
            created_at   REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS votes (
            fund_id  TEXT NOT NULL,
            user     TEXT NOT NULL,
            deposit  REAL NOT NULL,
            votes    TEXT NOT NULL,                       -- JSON {symbol: -2..2}
            updated  REAL NOT NULL,
            PRIMARY KEY (fund_id, user)
        );
        CREATE TABLE IF NOT EXISTS nav_history (
            fund_id TEXT NOT NULL,
            t       INTEGER NOT NULL,
            value   REAL NOT NULL,
            ret_pct REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS allowlist (
            fund_id TEXT NOT NULL,
            address TEXT NOT NULL,
            PRIMARY KEY (fund_id, address)
        );
        CREATE INDEX IF NOT EXISTS idx_nav ON nav_history(fund_id, t);
        """)


# ── 펀드 ────────────────────────────────────────────────────────
def create_fund(f):
    with _lock, _conn() as c:
        c.execute("""INSERT INTO funds
            (id,name,kind,visibility,creator,profile,leverage,initial_deposit,
             max_deposit,universe,init_weights,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
            f['id'], f['name'], f['kind'], f['visibility'], f.get('creator'),
            f['profile'], f.get('leverage'), f['initial_deposit'], f.get('max_deposit'),
            json.dumps(f['universe']), json.dumps(f.get('init_weights') or {}),
            time.time()))
        for addr in f.get('allowlist', []):
            c.execute("INSERT OR IGNORE INTO allowlist VALUES (?,?)", (f['id'], addr))


def _fund_row_to_dict(r):
    return {
        'id': r['id'], 'name': r['name'], 'kind': r['kind'],
        'visibility': r['visibility'], 'creator': r['creator'],
        'profile': r['profile'], 'leverage': r['leverage'],
        'initial_deposit': r['initial_deposit'], 'max_deposit': r['max_deposit'],
        'universe': json.loads(r['universe']),
        'init_weights': json.loads(r['init_weights'] or '{}'),
        'created_at': r['created_at'],
    }


def get_fund(fund_id):
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM funds WHERE id=?", (fund_id,)).fetchone()
        return _fund_row_to_dict(r) if r else None


def list_funds():
    with _lock, _conn() as c:
        rows = c.execute("SELECT * FROM funds ORDER BY created_at DESC").fetchall()
        return [_fund_row_to_dict(r) for r in rows]


def delete_fund(fund_id):
    with _lock, _conn() as c:
        for t in ('funds', 'votes', 'nav_history', 'allowlist'):
            c.execute(f"DELETE FROM {t} WHERE {'id' if t=='funds' else 'fund_id'}=?", (fund_id,))


def get_allowlist(fund_id):
    with _lock, _conn() as c:
        rows = c.execute("SELECT address FROM allowlist WHERE fund_id=?", (fund_id,)).fetchall()
        return [r['address'] for r in rows]


# ── 투표 ────────────────────────────────────────────────────────
def upsert_vote(fund_id, user, deposit, votes):
    with _lock, _conn() as c:
        c.execute("""INSERT INTO votes (fund_id,user,deposit,votes,updated)
            VALUES (?,?,?,?,?)
            ON CONFLICT(fund_id,user) DO UPDATE SET
              deposit=excluded.deposit, votes=excluded.votes, updated=excluded.updated""",
            (fund_id, user, deposit, json.dumps(votes), time.time()))


def get_votes(fund_id):
    with _lock, _conn() as c:
        rows = c.execute("SELECT * FROM votes WHERE fund_id=?", (fund_id,)).fetchall()
        return [{'user': r['user'], 'deposit': r['deposit'],
                 'votes': json.loads(r['votes'])} for r in rows]


def delete_vote(fund_id, user):
    """참가자 1명의 투표/예치 삭제 (지분 회수=출금 시)."""
    with _lock, _conn() as c:
        c.execute("DELETE FROM votes WHERE fund_id=? AND user=?", (fund_id, user))


def funds_for_user(user):
    """해당 user가 만들었거나 투표한 펀드 id 집합."""
    with _lock, _conn() as c:
        a = c.execute("SELECT id FROM funds WHERE creator=?", (user,)).fetchall()
        b = c.execute("SELECT fund_id FROM votes WHERE user=?", (user,)).fetchall()
        return {r[0] for r in a} | {r[0] for r in b}


# ── NAV ─────────────────────────────────────────────────────────
def append_nav(fund_id, t, value, ret_pct):
    with _lock, _conn() as c:
        c.execute("INSERT INTO nav_history VALUES (?,?,?,?)", (fund_id, t, value, ret_pct))


def upsert_nav_minute(fund_id, value, ret_pct):
    """분 단위 NAV 기록 — 같은 분은 덮어쓰기 (규칙적 시계열)."""
    import time as _t
    minute = int(_t.time() // 60) * 60
    with _lock, _conn() as c:
        row = c.execute("SELECT 1 FROM nav_history WHERE fund_id=? AND t=?",
                        (fund_id, minute)).fetchone()
        if row:
            c.execute("UPDATE nav_history SET value=?, ret_pct=? WHERE fund_id=? AND t=?",
                      (value, ret_pct, fund_id, minute))
        else:
            c.execute("INSERT INTO nav_history VALUES (?,?,?,?)",
                      (fund_id, minute, value, ret_pct))


def get_nav(fund_id, limit=300):
    with _lock, _conn() as c:
        rows = c.execute("SELECT t,value,ret_pct FROM nav_history WHERE fund_id=? "
                         "ORDER BY t DESC LIMIT ?", (fund_id, limit)).fetchall()
        return [{'t': r['t'], 'value': r['value'], 'ret_pct': r['ret_pct']}
                for r in reversed(rows)]
