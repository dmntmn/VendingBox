import sqlite3
from datetime import datetime


class Database:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init()

    def _init(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT,
                addr      INTEGER,
                item_name TEXT,
                price     INTEGER,
                paid      INTEGER,
                method    TEXT,
                status    TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS errors (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                ts    TEXT,
                addr  INTEGER,
                code  TEXT,
                msg   TEXT
            )
        """)
        self.conn.commit()

    def save_transaction(self, addr: int, item_name: str, price: int,
                         paid: int, method: str, status: str):
        self.conn.execute(
            "INSERT INTO transactions(ts,addr,item_name,price,paid,method,status) "
            "VALUES (?,?,?,?,?,?,?)",
            (datetime.now().isoformat(), addr, item_name, price, paid, method, status)
        )
        self.conn.commit()

    def save_error(self, addr: int, code: str, msg: str):
        self.conn.execute(
            "INSERT INTO errors(ts,addr,code,msg) VALUES (?,?,?,?)",
            (datetime.now().isoformat(), addr, code, msg)
        )
        self.conn.commit()
