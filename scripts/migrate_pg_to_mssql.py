"""
Copy all data from the old PostgreSQL database (PG_SOURCE_URL, read-only)
into the MS SQL database (DATABASE_URL). Creates missing tables first.

Re-runnable: each target table is emptied before copying (--keep skips tables
that already have rows). The source is read inside a READ ONLY transaction.

  python scripts/migrate_pg_to_mssql.py --dry-run   # source row counts only
  python scripts/migrate_pg_to_mssql.py             # copy everything
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, func, inspect, select, text, Integer  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, engine as target  # noqa: E402
import app.models  # noqa: E402,F401

BATCH = 500


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    if not settings.PG_SOURCE_URL:
        sys.exit("PG_SOURCE_URL is not set")
    if target.dialect.name != "mssql":
        sys.exit(f"DATABASE_URL must point at MS SQL, got {target.dialect.name}")

    source = create_engine(settings.PG_SOURCE_URL, pool_pre_ping=True)
    insp = inspect(source)
    src_tables = set(insp.get_table_names())
    if not args.dry_run:
        Base.metadata.create_all(target)

    # Delete children first, then copy parents first
    order = Base.metadata.sorted_tables
    if not args.dry_run and not args.keep:
        with target.begin() as t:
            for table in reversed(order):
                t.execute(table.delete())

    with source.connect() as s:
        s.execute(text("SET TRANSACTION READ ONLY"))
        for table in order:
            if table.name not in src_tables:
                print(f"{table.name:24s} not in source")
                continue
            src_cols = {c["name"] for c in insp.get_columns(table.name)}
            cols = [c for c in table.columns if c.name in src_cols]
            total = s.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
            if args.dry_run:
                print(f"{table.name:24s} {total} rows; missing in source: "
                      f"{[c.name for c in table.columns if c.name not in src_cols]}")
                continue
            if args.keep:
                with target.connect() as t:
                    if t.execute(select(func.count()).select_from(table)).scalar():
                        print(f"{table.name:24s} kept existing rows")
                        continue
            identity = any(c.primary_key and isinstance(c.type, Integer) for c in table.columns)
            names = [c.name for c in cols]
            result = s.execution_options(stream_results=True).execute(
                text(f'SELECT {", ".join(chr(34) + n + chr(34) for n in names)} FROM "{table.name}"'))
            copied = 0
            while rows := result.fetchmany(BATCH):
                with target.begin() as t:
                    if identity:
                        t.execute(text(f"SET IDENTITY_INSERT [{table.name}] ON"))
                    t.execute(table.insert(), [dict(zip(names, r)) for r in rows])
                    if identity:
                        t.execute(text(f"SET IDENTITY_INSERT [{table.name}] OFF"))
                copied += len(rows)
            print(f"{table.name:24s} {copied}/{total} copied")


if __name__ == "__main__":
    main()
