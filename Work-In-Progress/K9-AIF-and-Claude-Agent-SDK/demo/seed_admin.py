#!/usr/bin/env python3
"""
Create the first admin account. Admin accounts are never self-registered
via a public form (petstore/services/auth.py's register_admin() is not
exposed by any webui_server.py route) -- provisioned out-of-band, here.

Usage:
    python demo/seed_admin.py <username> <password>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from petstore.services import auth


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python demo/seed_admin.py <username> <password>")
        sys.exit(1)

    username, password = sys.argv[1], sys.argv[2]
    admin_id = auth.register_admin(username, password)
    print(f"Admin account created: {username} (admin_id={admin_id})")
    print("Log in at /admin/login")


if __name__ == "__main__":
    main()
