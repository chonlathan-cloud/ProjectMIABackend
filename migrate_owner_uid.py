#!/usr/bin/env python3
import argparse
import os
from datetime import datetime

from firebase_admin import auth, credentials
import firebase_admin
from sqlmodel import Session, select, create_engine

from src.models import Shop


def to_sync_db_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def resolve_config(args: argparse.Namespace) -> tuple[str, str]:
    load_env_file(".env")

    db_url = args.db_url or os.getenv("DB_URL") or os.getenv("DATABASE_URL")
    firebase_path = (
        args.firebase_credentials_path
        or os.getenv("FIREBASE_CREDENTIALS_PATH")
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    )

    if not db_url or not firebase_path:
        try:
            from src.config import settings

            db_url = db_url or settings.db_url
            firebase_path = firebase_path or settings.firebase_credentials_path
        except Exception:
            pass

    if firebase_path and not os.path.exists(firebase_path):
        if os.getenv("FIREBASE_CREDENTIALS_PATH") == firebase_path:
            os.environ.pop("FIREBASE_CREDENTIALS_PATH", None)
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") == firebase_path:
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        firebase_path = None

    if not db_url or not firebase_path:
        missing = []
        if not db_url:
            missing.append("DB_URL")
        if not firebase_path:
            missing.append("FIREBASE_CREDENTIALS_PATH")
        if missing and missing != ["FIREBASE_CREDENTIALS_PATH"]:
            raise SystemExit(
                "Missing config: "
                + ", ".join(missing)
                + ". Set env vars or pass --db-url/--firebase-credentials-path."
            )

    return db_url, firebase_path


def init_firebase(firebase_path: str | None) -> None:
    if firebase_admin._apps:
        return
    if firebase_path:
        cred = credentials.Certificate(firebase_path)
        firebase_admin.initialize_app(cred)
        return
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and not os.path.exists(env_path):
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate Shop.owner_uid from email to Firebase UID"
    )
    parser.add_argument("--apply", action="store_true", help="Apply updates to the database")
    parser.add_argument("--db-url", help="Database URL (overrides DB_URL)")
    parser.add_argument(
        "--firebase-credentials-path",
        help="Path to Firebase service account JSON",
    )
    args = parser.parse_args()

    db_url, firebase_path = resolve_config(args)
    init_firebase(firebase_path)
    engine = create_engine(to_sync_db_url(db_url))

    with Session(engine) as session:
        stores = session.exec(
            select(Shop).where(Shop.owner_uid.contains("@"))
        ).all()

        if not stores:
            print("No stores with email-like owner_uid found.")
            return

        updates = []
        for store in stores:
            email = store.owner_uid
            try:
                user = auth.get_user_by_email(email)
            except Exception as exc:
                print(f"skip {store.shop_id}: cannot resolve {email}: {exc}")
                continue
            updates.append((store, user.uid, email))

        if not updates:
            print("No resolvable users found.")
            return

        for store, uid, email in updates:
            print(f"{store.shop_id}: {email} -> {uid}")

        if not args.apply:
            print("Dry run only. Re-run with --apply to update records.")
            return

        now = datetime.utcnow()
        for store, uid, _ in updates:
            store.owner_uid = uid
            store.updated_at = now
            session.add(store)

        session.commit()
        print(f"Updated {len(updates)} stores.")


if __name__ == "__main__":
    main()
