#!/usr/bin/env python3
"""Start the NGO Suite.  Usage: python3 run.py [--port 8000] [--host 127.0.0.1]"""
import argparse, os, secrets, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DEMO = "--demo" in sys.argv
if DEMO:   # demo mode keeps sample data in its own file, so your real data is never touched
    os.environ["NGO_DB"] = os.path.join(HERE, "data", "demo.db")
from app import db, server, automation

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to share on your office network")
    ap.add_argument("--demo", action="store_true", help="run with sample data in data/demo.db (admin / ChangeMe123)")
    a = ap.parse_args()
    db.init_db()
    if a.demo:
        import seed
        seed.main()      # loads sample data only if data/demo.db is empty
        print("\n  DEMO MODE: sample data in data/demo.db. Sign in as admin / ChangeMe123.  Delete data/demo.db to reset it.\n")
    c = db.connect()
    if not c.execute("SELECT 1 FROM users").fetchone():
        pw = os.environ.get("NGO_ADMIN_PASSWORD") or secrets.token_urlsafe(9)
        h, salt = db.hash_pw(pw)
        c.execute("INSERT INTO users(username,name,role,pw_hash,salt,must_change) VALUES('admin','Administrator','admin',?,?,1)", (h, salt))
        c.commit()
        print(f"\n  First run: sign in as  admin  /  {pw}\n  (you will be asked to change this password)\n")
    c.close()
    httpd = server.serve(a.host, a.port)
    automation.start_scheduler()   # daily backup, digest, alerts, birthday wishes, scheduled reports
    print(f"NGO Suite running at http://{a.host if a.host != '0.0.0.0' else 'localhost'}:{a.port}   (Ctrl+C to stop)")
    try: httpd.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")

if __name__ == "__main__":
    main()
