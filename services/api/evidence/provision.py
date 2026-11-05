"""Local operator command. Password is entered with getpass, never a CLI argument."""
import argparse
import getpass
from sqlalchemy import select
from .auth import hash_password
from .db import Session, User
from .migrate import migrate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--email', required=True)
    parser.add_argument('--org', required=True, choices=['aurora', 'meridian'])
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    password = getpass.getpass('LIVE user password (12+ characters): ')
    if len(password) < 12:
        raise SystemExit('Password must have at least 12 characters')
    migrate()
    with Session.begin() as db:
        if db.scalar(select(User).where(User.email == args.email)):
            raise SystemExit('Account already exists; use a distinct LIVE account email')
        db.add(User(email=args.email, org=args.org, name=args.name, mode='LIVE', password_hash=hash_password(password)))
    print('LIVE account created')


if __name__ == '__main__':
    main()
