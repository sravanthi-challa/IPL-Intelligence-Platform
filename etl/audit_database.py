import os
import psycopg2
import sys

def audit():
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="cricket_intelligence",
            user="postgres",
            password=os.environ.get("DB_PASSWORD", "")
        )
        cur = conn.cursor()
        print("Connected to PostgreSQL successfully.")
        
        # Check installed extensions
        cur.execute("SELECT extname, extversion FROM pg_extension;")
        extensions = cur.fetchall()
        print("\nInstalled PostgreSQL Extensions:")
        for ext, ver in extensions:
            print(f"  - {ext}: version {ver}")
            
        # Check tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        tables = [r[0] for r in cur.fetchall()]
        print(f"\nFound {len(tables)} tables in 'public' schema:")
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM {t};")
            count = cur.fetchone()[0]
            print(f"  - {t}: {count} rows")
            
        print("\nChecking columns for each table:")
        for t in tables:
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """, (t,))
            cols = cur.fetchall()
            col_summary = ", ".join([f"{c[0]} ({c[1]})" for c in cols])
            print(f"  - {t}: {col_summary}")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error during database audit: {e}", file=sys.stderr)

if __name__ == "__main__":
    audit()
