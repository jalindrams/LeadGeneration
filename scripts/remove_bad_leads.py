import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

try:
    sql = """
    WITH bad_leads AS (
        SELECT id FROM leads
        WHERE phone IS NULL
           OR phone = ''
           OR LOWER(TRIM(company_name)) IN ('contact us', 'about us', 'home', 'feedback', 'help', 'login', 'register', 'jobs & careers', 'complaints', 'customer care', 'latest buylead', 'learning centre', 'post your requirement', 'products you buy', 'search products & suppliers', 'hindi', 'affiliate', 'flips', 'visit\n\nmobile site', 'visit mobile site')
           OR LENGTH(LOWER(TRIM(company_name))) < 3
    )
    DELETE FROM lead_assignments WHERE lead_id IN (SELECT id FROM bad_leads);
    """
    db.execute(text(sql))
    
    sql2 = """
    DELETE FROM leads
    WHERE phone IS NULL
       OR phone = ''
       OR LOWER(TRIM(company_name)) IN ('contact us', 'about us', 'home', 'feedback', 'help', 'login', 'register', 'jobs & careers', 'complaints', 'customer care', 'latest buylead', 'learning centre', 'post your requirement', 'products you buy', 'search products & suppliers', 'hindi', 'affiliate', 'flips', 'visit\n\nmobile site', 'visit mobile site')
       OR LENGTH(LOWER(TRIM(company_name))) < 3
    RETURNING id;
    """
    result = db.execute(text(sql2))
    deleted = result.rowcount
    
    db.commit()
    print(f"Deleted {deleted} invalid leads from the database.")
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
