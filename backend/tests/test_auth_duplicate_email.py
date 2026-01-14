import unittest

from fastapi.testclient import TestClient


class FakeUser:
    def __init__(self, email: str):
        self.email = email


class FakeAdmin:
    def __init__(self, users=None, create_user_error: str | None = None):
        self._users = users or []
        self._create_user_error = create_user_error
        self.create_user_called = False

    def list_users(self, page=None, per_page=None):
        return list(self._users)

    def create_user(self, attributes):
        self.create_user_called = True
        if self._create_user_error:
            raise Exception(self._create_user_error)

        class R:
            pass

        class U:
            id = "user-1"

        r = R()
        r.user = U()
        return r


class FakeAuth:
    def __init__(self, admin: FakeAdmin):
        self.admin = admin


class FakeService:
    def __init__(self, admin: FakeAdmin):
        self.auth = FakeAuth(admin)


class FakeAnonAuth:
    def __init__(self, session_ok: bool = True, reset_error: str | None = None):
        self._session_ok = session_ok
        self._reset_error = reset_error
        self.reset_called = False

    def sign_in_with_password(self, creds):
        class Session:
            access_token = "at"
            refresh_token = "rt"
            expires_in = 3600
            token_type = "bearer"

        class Res:
            session = Session() if self._session_ok else None

        return Res()

    def reset_password_for_email(self, email: str, options=None):
        self.reset_called = True
        if self._reset_error:
            raise Exception(self._reset_error)


class FakeAnon:
    def __init__(self, auth: FakeAnonAuth):
        self.auth = auth


class DuplicateEmailAuthTests(unittest.TestCase):
    def setUp(self):
        import backend.main as main

        self.main = main
        self._orig_get_service = main.get_supabase_service
        self._orig_get_anon = main.get_supabase_anon

    def tearDown(self):
        self.main.get_supabase_service = self._orig_get_service
        self.main.get_supabase_anon = self._orig_get_anon

    def test_email_availability_false_when_exists(self):
        admin = FakeAdmin(users=[FakeUser("exists@example.com")])
        self.main.get_supabase_service = lambda: FakeService(admin)
        client = TestClient(self.main.app)

        r = client.get("/api/auth/email-availability", params={"email": "exists@example.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"available": False})

    def test_signup_returns_409_when_email_exists_precheck(self):
        admin = FakeAdmin(users=[FakeUser("dup@example.com")])
        anon_auth = FakeAnonAuth(session_ok=True)
        self.main.get_supabase_service = lambda: FakeService(admin)
        self.main.get_supabase_anon = lambda: FakeAnon(anon_auth)
        client = TestClient(self.main.app)

        r = client.post("/api/auth/sign-up", json={"email": "dup@example.com", "password": "Password123!"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["code"], "duplicate_email")
        self.assertFalse(admin.create_user_called)

    def test_signup_returns_409_when_create_user_duplicate(self):
        admin = FakeAdmin(users=[], create_user_error="A user with this email address has already been registered")
        anon_auth = FakeAnonAuth(session_ok=True)
        self.main.get_supabase_service = lambda: FakeService(admin)
        self.main.get_supabase_anon = lambda: FakeAnon(anon_auth)
        client = TestClient(self.main.app)

        r = client.post("/api/auth/sign-up", json={"email": "dup2@example.com", "password": "Password123!"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["code"], "duplicate_email")
        self.assertTrue(admin.create_user_called)

    def test_password_recovery_always_ok(self):
        admin = FakeAdmin(users=[])
        anon_auth = FakeAnonAuth(session_ok=True, reset_error="smtp down")
        self.main.get_supabase_service = lambda: FakeService(admin)
        self.main.get_supabase_anon = lambda: FakeAnon(anon_auth)
        client = TestClient(self.main.app)

        r = client.post("/api/auth/password-recovery", json={"email": "x@example.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True})
        self.assertTrue(anon_auth.reset_called)

    def test_storage_file_options_are_strings(self):
        opts = self.main._storage_file_options("application/pdf")
        self.assertEqual(opts, {"content-type": "application/pdf"})
        for v in opts.values():
            self.assertIsInstance(v, str)

    def test_ensure_storage_bucket_creates_when_missing(self):
        class B:
            def __init__(self, bid: str):
                self.id = bid

        class Storage:
            def __init__(self):
                self.created = False

            def list_buckets(self):
                return []

            def create_bucket(self, bid: str, options=None, name=None):
                self.created = True
                return {"name": bid}

        class Svc:
            def __init__(self):
                self.storage = Storage()

        svc = Svc()
        self.main._ensure_storage_bucket(svc)
        self.assertTrue(svc.storage.created)


if __name__ == "__main__":
    unittest.main()
