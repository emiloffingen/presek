import datetime
import os

import jwt
import pytest

# core.admin_tokens reads this at import time and refuses to load without it when
# ENV=production. Set it before the first import of that module.
os.environ.setdefault("ADMIN_TOKEN_SECRET", "test-admin-secret-for-jwt-testing-1234567890")

from core.logging_config import get_logger

log = get_logger("presek.tests.admin_tokens")


class _Row(dict):
    """Row type that supports both ``dict(row)`` and ``row[0]`` positional access.

    ``core.admin_tokens.verify_admin_token`` uses ``row[0]`` on the result of
    ``db.execute`` while the other helpers iterate the rows directly, so the fake
    needs to behave like a psycopg row record.
    """

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(dict.values(self))[key]
        return super().__getitem__(key)


class FakeTokenDB:
    """Minimal in-memory stand-in for the ``admin_tokens`` table.

    The production module talks to Postgres through ``db.execute`` with a handful
    of fixed statements. Rather than requiring a live database (which made this
    module error out on any developer machine and in Termux environments where
    Postgres cannot initialize), dispatch on the statement verb and emulate the
    small slice of SQL the module actually uses.
    """

    COLUMNS = (
        "token_id",
        "token_hash",
        "subject",
        "scope",
        "expires_at",
        "created_at",
        "revoked_at",
        "last_used_at",
    )

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.initialized = False

    # -- helpers ------------------------------------------------------------
    def _project(self, row: dict) -> _Row:
        return _Row({col: row.get(col) for col in self.COLUMNS})

    @staticmethod
    def _normalize_sql(sql: str) -> str:
        return " ".join(sql.split()).strip().upper()

    def _matching(self, predicate) -> list[dict]:
        return [row for row in self.rows.values() if predicate(row)]

    # -- db.execute compatible entry point ----------------------------------
    def execute(self, sql, params=None, fetch=True, read_only=None):
        params = params or ()
        stmt = self._normalize_sql(sql)

        if stmt.startswith("CREATE TABLE") or stmt.startswith("CREATE INDEX"):
            self.initialized = True
            return 0

        if stmt.startswith("INSERT INTO ADMIN_TOKENS"):
            record = dict(zip(self.COLUMNS, params))
            self.rows[str(record["token_id"])] = record
            return 1

        if stmt.startswith("DELETE FROM ADMIN_TOKENS"):
            now = params[0]
            expired = self._matching(lambda r: r["expires_at"] < now)
            for row in expired:
                self.rows.pop(str(row["token_id"]), None)
            return [_Row({"token_id": row["token_id"]}) for row in expired]

        if stmt.startswith("UPDATE ADMIN_TOKENS SET LAST_USED_AT"):
            last_used_at, token_id = params
            row = self.rows.get(str(token_id))
            if row is not None:
                row["last_used_at"] = last_used_at
            return 1

        if stmt.startswith("UPDATE ADMIN_TOKENS SET CREATED_AT"):
            created_at, expires_at, token_id = params
            row = self.rows.get(str(token_id))
            if row is not None:
                row["created_at"] = created_at
                row["expires_at"] = expires_at
            return 1

        # The subject-scoped revoke shares a prefix with the id-scoped one, so it
        # has to be matched first: both bind ``revoked_at`` first but differ in
        # the second placeholder (subject vs token_id).
        if "WHERE SUBJECT = %S" in stmt and stmt.startswith("UPDATE ADMIN_TOKENS"):
            revoked_at, subject = params
            targets = self._matching(lambda r: r["subject"] == subject and r["revoked_at"] is None)
            for row in targets:
                row["revoked_at"] = revoked_at
            return [_Row({"token_id": row["token_id"]}) for row in targets]

        if stmt.startswith("UPDATE ADMIN_TOKENS SET REVOKED_AT"):
            revoked_at, token_id = params
            row = self.rows.get(str(token_id))
            if row is None or row["revoked_at"] is not None:
                return []
            row["revoked_at"] = revoked_at
            return [_Row({"token_id": row["token_id"]})]

        if stmt.startswith("SELECT") and "FROM ADMIN_TOKENS" in stmt:
            if "WHERE TOKEN_ID = %S" in stmt:
                token_id = params[0]
                row = self.rows.get(str(token_id))
                return [self._project(row)] if row is not None else []
            if "WHERE SUBJECT = %S" in stmt:
                subject = params[0]
                rows = self._matching(lambda r: r["subject"] == subject)
                return [self._project(r) for r in rows]
            if "WHERE (REVOKED_AT IS NULL OR REVOKED_AT > %S)" in stmt:
                now, expires_cutoff = params
                rows = self._matching(
                    lambda r: (r["revoked_at"] is None or r["revoked_at"] > now) and r["expires_at"] > expires_cutoff
                )
                rows.sort(key=lambda r: r["created_at"], reverse=True)
                return [self._project(r) for r in rows]

        raise AssertionError(f"FakeTokenDB received unexpected SQL: {stmt}")


@pytest.fixture(autouse=True)
def fake_token_db(monkeypatch):
    """Swap the real database for an in-memory table.

    Patching the attribute the module imported (``core.admin_tokens.db``) keeps
    the production code path intact while removing the Postgres dependency.
    """
    import core.admin_tokens as admin_tokens

    fake = FakeTokenDB()
    monkeypatch.setattr(admin_tokens, "db", fake)

    # The module runs _initialize_database() at import time, which already went
    # to the real (unavailable) database. Re-run it against the fake so the
    # schema-init path is still exercised here.
    assert admin_tokens._initialize_database() is True
    assert fake.initialized, "admin_tokens schema was never initialized"

    yield fake


def test_create_and_verify_admin_token():
    """Test standard admin token creation and verification flow."""
    from core.admin_tokens import create_admin_token, verify_admin_token

    token_str, token_meta = create_admin_token(subject="test-admin-subject", scope="read-only", expiry_hours=2)

    assert token_str is not None
    assert token_meta.subject == "test-admin-subject"
    assert token_meta.scope == "read-only"
    assert token_meta.expires_at > token_meta.created_at

    verified = verify_admin_token(token_str)
    assert verified is not None
    assert verified.token_id == token_meta.token_id
    assert verified.subject == "test-admin-subject"
    assert verified.scope == "read-only"


def test_tampered_signature_verification_fails():
    """Test that tampered JWT signatures fail verification."""
    from core.admin_tokens import create_admin_token, verify_admin_token

    token_str, _ = create_admin_token(subject="security-admin")

    tampered_token = token_str + "x"
    assert verify_admin_token(tampered_token) is None


def test_token_signed_with_wrong_key_fails():
    """Test that a token signed with an unauthorized external key fails verification."""
    from core.admin_tokens import ADMIN_TOKEN_SECRET, create_admin_token, verify_admin_token

    _, token_meta = create_admin_token(subject="other-admin")

    payload = {
        "jti": token_meta.token_id,
        "sub": "other-admin",
        "scope": token_meta.scope,
        "iat": int(token_meta.created_at.timestamp()),
        "exp": int(token_meta.expires_at.timestamp()),
        "iss": "presek-admin",
        "aud": "presek-api",
    }

    wrong_key_token = jwt.encode(payload, "completely-wrong-key-secret-12345", algorithm="HS256")
    assert verify_admin_token(wrong_key_token) is None

    # Guard against the fixture accidentally signing with the same key.
    assert wrong_key_token != jwt.encode(payload, ADMIN_TOKEN_SECRET, algorithm="HS256")


def test_token_revocation():
    """Test token revocation flow."""
    from core.admin_tokens import create_admin_token, revoke_admin_token, verify_admin_token

    token_str, token_meta = create_admin_token(subject="revocation-target")
    assert verify_admin_token(token_str) is not None

    success = revoke_admin_token(token_meta.token_id)
    assert success is True

    assert verify_admin_token(token_str) is None


def test_revoke_all_tokens_for_subject():
    """Test revoking all active tokens for a specific subject."""
    from core.admin_tokens import create_admin_token, revoke_all_tokens_for_subject, verify_admin_token

    token_str_1, _ = create_admin_token(subject="multi-admin")
    token_str_2, _ = create_admin_token(subject="multi-admin")
    token_str_3, _ = create_admin_token(subject="other-admin")

    assert verify_admin_token(token_str_1) is not None
    assert verify_admin_token(token_str_2) is not None
    assert verify_admin_token(token_str_3) is not None

    count = revoke_all_tokens_for_subject("multi-admin")
    assert count == 2

    assert verify_admin_token(token_str_1) is None
    assert verify_admin_token(token_str_2) is None
    assert verify_admin_token(token_str_3) is not None


def test_list_active_admin_tokens():
    """Test listing active admin tokens excludes expired/revoked ones."""
    from core.admin_tokens import create_admin_token, list_active_admin_tokens, revoke_admin_token

    _, token_meta_1 = create_admin_token(subject="list-admin-1")
    _, token_meta_2 = create_admin_token(subject="list-admin-2")

    active_tokens = list_active_admin_tokens()
    active_ids = {t.token_id for t in active_tokens}
    assert token_meta_1.token_id in active_ids
    assert token_meta_2.token_id in active_ids

    revoke_admin_token(token_meta_1.token_id)

    active_tokens_after = list_active_admin_tokens()
    active_ids_after = {t.token_id for t in active_tokens_after}
    assert token_meta_1.token_id not in active_ids_after
    assert token_meta_2.token_id in active_ids_after


def test_cleanup_expired_tokens():
    """Test cleaning up expired tokens removes them from the database."""
    from core.admin_tokens import cleanup_expired_tokens, create_admin_token

    _, token_meta = create_admin_token(subject="expiring-soon")

    past_created_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=10)
    past_expiry_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)
    with_fake_db_update(token_meta.token_id, past_created_date, past_expiry_date)

    cleaned = cleanup_expired_tokens()
    assert cleaned == 1


def with_fake_db_update(token_id, created_at, expires_at):
    """Backdate a token through the in-memory fake table."""
    import core.admin_tokens as admin_tokens

    fake = admin_tokens.db
    row = fake.rows.get(str(token_id))
    assert row is not None
    row["created_at"] = created_at
    row["expires_at"] = expires_at
