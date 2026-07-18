"""
Micraft Growth Engine - Phase 1.6 Migration
Creates the new User and LeadAssignment tables, updates the leads table,
and creates a default admin user.
"""

import sys
import os
import logging
import bcrypt
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, SessionLocal
from app.models import Base, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def run_migration():
    logger.info("Creating new tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tables created.")

    logger.info("Altering leads table...")
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE leads ADD COLUMN assigned_to INTEGER REFERENCES users(id)"))
            conn.commit()
            logger.info("Added assigned_to column")
        except Exception as e:
            logger.warning(f"Column assigned_to might already exist: {e}")

        try:
            conn.execute(text("ALTER TABLE leads ADD COLUMN assigned_at TIMESTAMP"))
            conn.commit()
            logger.info("Added assigned_at column")
        except Exception as e:
            logger.warning(f"Column assigned_at might already exist: {e}")

    logger.info("Creating default admin user...")
    with SessionLocal() as db:
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            hashed_password = hash_password("micraft2025")
            admin_user = User(
                username="admin",
                password_hash=hashed_password,
                full_name="System Administrator",
                role="admin"
            )
            db.add(admin_user)
            db.commit()
            logger.info("Default admin user 'admin' created successfully.")
        else:
            logger.info("Admin user already exists.")

    logger.info("Migration complete!")

if __name__ == "__main__":
    run_migration()
