#!/usr/bin/env python3
"""Reset the admin password to ChangeMe123 (or the one you give). Usage: py reset_admin.py [newpassword]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import db
db.init_db(); c = db.connect(); pw = sys.argv[1] if len(sys.argv) > 1 else "ChangeMe123"
h, s = db.hash_pw(pw)
if not c.execute("UPDATE users SET pw_hash=?, salt=?, must_change=0, active=1 WHERE username='admin'", (h, s)).rowcount:
    c.execute("INSERT INTO users(username,name,role,pw_hash,salt,must_change) VALUES('admin','Administrator','admin',?,?,0)", (h, s))
c.commit(); print("Done. Sign in as admin with password:", pw)
