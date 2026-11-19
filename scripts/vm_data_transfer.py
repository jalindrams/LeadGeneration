"""Copy the Shiplystic ('ecom') working set between two MS SQL databases without a direct connection.

  python scripts/vm_data_transfer.py export > data.b64     # run where the data is (reads DATABASE_URL)
  python scripts/vm_data_transfer.py import data.b64       # run on the target (writes DATABASE_URL)

Copies: active users (password hashes as they are), ecom leads, stores, store contacts and signals.
Leads arrive UNASSIGNED: an admin assigns them to callers. Safe to re-run (existing ids are skipped).
The payload is gzip+base64 text so it can travel through a clipboard.
"""
import base64
import datetime as dt
import decimal
import gzip
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import MetaData, Table, text  # noqa: E402

from app.database import engine  # noqa: E402


def _ser(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, (uuid.UUID, decimal.Decimal)):
        return str(v)
    return v


def _rows(c, sql):
    r = c.execute(text(sql))
    cols = list(r.keys())
    return [{k: _ser(v) for k, v in zip(cols, row)} for row in r]


def export():
    with engine.connect() as c:
        data = {
            "users": _rows(c, "select * from users where is_active = 1"),
            "leads": _rows(c, "select * from leads where target_product = 'ecom'"),
            "stores": _rows(c, "select * from stores"),
            "store_contacts": _rows(c, "select * from store_contacts"),
            "store_signals": _rows(c, "select * from store_signals"),
        }
    for l in data["leads"]:
        l["assigned_to"] = None
        l["assigned_at"] = None
    for u in data["users"]:
        u.pop("id", None)
    raw = json.dumps(data).encode()
    sys.stdout.write(base64.b64encode(gzip.compress(raw)).decode())
    print("\n" + ", ".join(f"{k}={len(v)}" for k, v in data.items()), file=sys.stderr)


def _coerce(col, v):
    if v is None:
        return None
    try:
        t = col.type.python_type
    except NotImplementedError:
        return v
    if t is dt.datetime:
        return dt.datetime.fromisoformat(v)
    if t is dt.date:
        return dt.date.fromisoformat(v)
    if t is uuid.UUID:
        return uuid.UUID(v)
    if t is decimal.Decimal:
        return decimal.Decimal(v)
    if t is bool:
        return bool(v)
    return v


def _load(table_name, rows, key, keep_ids, conn, md):
    t = Table(table_name, md, autoload_with=conn)
    have = {r[0] for r in conn.execute(text(f"select {key} from {table_name}"))}
    todo = []
    for r in rows:
        if str(r[key]) in {str(h) for h in have}:
            continue
        todo.append({k: _coerce(t.c[k], v) for k, v in r.items() if k in t.c})
    if not todo:
        return 0
    ident = keep_ids and any(c.autoincrement is True or c.identity is not None for c in t.c if c.primary_key)
    if ident:
        conn.execute(text(f"SET IDENTITY_INSERT {table_name} ON"))
    conn.execute(t.insert(), todo)
    if ident:
        conn.execute(text(f"SET IDENTITY_INSERT {table_name} OFF"))
    return len(todo)


def do_import(path):
    data = json.loads(gzip.decompress(base64.b64decode(open(path).read().strip())))
    md = MetaData()
    with engine.begin() as conn:
        for name, key, keep in (("users", "username", False), ("leads", "id", True),
                                ("stores", "id", True), ("store_contacts", "id", True),
                                ("store_signals", "id", True)):
            n = _load(name, data[name], key, keep, conn, md)
            print(f"{name}: {n} inserted ({len(data[name])} in file)")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "export":
        export()
    elif len(sys.argv) >= 3 and sys.argv[1] == "import":
        do_import(sys.argv[2])
    else:
        print(__doc__)
