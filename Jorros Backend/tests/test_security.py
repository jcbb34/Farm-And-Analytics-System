import unittest

try:
    from app.core.security import (
        create_access_token,
        create_two_factor_challenge,
        decode_access_token_claims,
        decode_two_factor_challenge,
        hash_password,
        verify_password,
    )
except ModuleNotFoundError:
    create_access_token = None
    create_two_factor_challenge = None
    decode_access_token_claims = None
    decode_two_factor_challenge = None
    hash_password = None
    verify_password = None


@unittest.skipUnless(hash_password and verify_password, "Install backend requirements to run password hashing tests.")
class SecurityTests(unittest.TestCase):
    def test_password_hash_round_trip(self):
        password = "Joross-Test-Password-2026"
        hashed = hash_password(password)
        self.assertNotEqual(password, hashed)
        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("wrong-password", hashed))

    def test_access_token_carries_auth_version(self):
        token, _ = create_access_token(42, auth_version=7)
        self.assertEqual(decode_access_token_claims(token), (42, 7))

    def test_legacy_token_version_defaults_to_zero(self):
        token, _ = create_access_token(42)
        self.assertEqual(decode_access_token_claims(token), (42, 0))

    def test_two_factor_challenge_carries_auth_version(self):
        token, _ = create_two_factor_challenge(42, auth_version=9)
        self.assertEqual(decode_two_factor_challenge(token), (42, 9))


if __name__ == "__main__":
    unittest.main()
