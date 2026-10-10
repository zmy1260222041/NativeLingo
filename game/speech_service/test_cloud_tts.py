"""Cloud TTS provider: service-account auth, voice mapping and pace control.

The service account assertion is verified locally with a throwaway RSA key so
the crypto path is exercised without touching Google. Every other test pins the
exact request the provider would send.
"""
from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def _write_service_account(directory: Path) -> tuple[Path, rsa.RSAPrivateKey]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = directory / "service-account.json"
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "nativelingo-test",
                "client_email": "tts-runner@nativelingo-test.iam.gserviceaccount.com",
                "private_key": pem.decode("ascii"),
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        encoding="utf-8",
    )
    return path, key


def _decode_segment(segment: str) -> dict:
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class CloudTTSAuthTest(unittest.TestCase):
    def setUp(self):
        server._CLOUD_TTS_SERVICE_ACCOUNT = {}
        server._CLOUD_TTS_TOKEN = {"value": "", "expires_at": 0.0}
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.account_path, self.key = _write_service_account(Path(self._tmp.name))
        patch = mock.patch.object(server, "CLOUD_TTS_CREDENTIALS", str(self.account_path))
        patch.start()
        self.addCleanup(patch.stop)

    def test_assertion_is_a_valid_rs256_jwt(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["body"] = request.data.decode("utf-8")
            return _FakeResponse({"access_token": "ya29.test", "expires_in": 3600})

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            token = server._cloud_tts_access_token()

        self.assertEqual(token, "ya29.test")
        self.assertEqual(captured["url"], "https://oauth2.googleapis.com/token")

        from urllib.parse import parse_qs

        fields = {key: value[0] for key, value in parse_qs(captured["body"]).items()}
        self.assertEqual(fields["grant_type"], "urn:ietf:params:oauth:grant-type:jwt-bearer")

        assertion = fields["assertion"]
        header_seg, claims_seg, signature_seg = assertion.split(".")

        header = _decode_segment(header_seg)
        self.assertEqual(header["alg"], "RS256")
        self.assertEqual(header["typ"], "JWT")

        claims = _decode_segment(claims_seg)
        self.assertEqual(claims["iss"], "tts-runner@nativelingo-test.iam.gserviceaccount.com")
        self.assertEqual(claims["aud"], "https://oauth2.googleapis.com/token")
        self.assertIn("cloud-platform", claims["scope"])
        self.assertGreater(claims["exp"], claims["iat"])

        # The signature must verify against the public half of the key, which
        # is the part Google checks.
        signing_input = (header_seg + "." + claims_seg).encode("ascii")
        signature = base64.urlsafe_b64decode(signature_seg + "=" * (-len(signature_seg) % 4))
        self.key.public_key().verify(
            signature, signing_input, padding.PKCS1v15(), hashes.SHA256()
        )

    def test_token_is_cached_across_calls(self):
        calls = {"count": 0}

        def fake_urlopen(request, timeout=None):
            calls["count"] += 1
            return _FakeResponse({"access_token": "ya29.cached", "expires_in": 3600})

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            first = server._cloud_tts_access_token()
            second = server._cloud_tts_access_token()

        self.assertEqual(first, second)
        self.assertEqual(calls["count"], 1)

    def test_expiring_token_is_refreshed(self):
        calls = {"count": 0}

        def fake_urlopen(request, timeout=None):
            calls["count"] += 1
            return _FakeResponse({"access_token": f"ya29.n{calls['count']}", "expires_in": 3600})

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            server._cloud_tts_access_token()
            server._CLOUD_TTS_TOKEN["expires_at"] = 0.0
            refreshed = server._cloud_tts_access_token()

        self.assertEqual(refreshed, "ya29.n2")
        self.assertEqual(calls["count"], 2)

    def test_missing_credentials_are_reported_without_leaking_path(self):
        with mock.patch.object(server, "CLOUD_TTS_CREDENTIALS", ""):
            with mock.patch.object(server, "_cloud_tts_credentials_path", lambda: ""):
                with self.assertRaises(RuntimeError) as caught:
                    server._cloud_tts_access_token()
        self.assertIn("no service account credentials", str(caught.exception))

    def test_non_service_account_json_is_rejected(self):
        bad = Path(self._tmp.name) / "bad.json"
        bad.write_text(json.dumps({"installed": {"client_id": "x"}}), encoding="utf-8")
        with mock.patch.object(server, "CLOUD_TTS_CREDENTIALS", str(bad)):
            server._CLOUD_TTS_SERVICE_ACCOUNT = {}
            with self.assertRaises(RuntimeError) as caught:
                server._cloud_tts_access_token()
        self.assertIn("not a service account key", str(caught.exception))


class CloudTTSVoiceTest(unittest.TestCase):
    def test_cast_voice_maps_to_full_chirp_name(self):
        with mock.patch.object(server, "TTS_PROVIDER", "cloud"):
            self.assertEqual(server._cloud_tts_voice_name("eve"), "en-US-Chirp3-HD-Kore")
            self.assertEqual(server._cloud_tts_voice_name("rex"), "en-US-Chirp3-HD-Charon")

    def test_full_voice_name_passes_through(self):
        with mock.patch.object(server, "TTS_PROVIDER", "cloud"):
            self.assertEqual(
                server._cloud_tts_voice_name("en-GB-Chirp3-HD-Sulafat"),
                "en-GB-Chirp3-HD-Sulafat",
            )

    def test_unknown_voice_id_is_treated_as_a_chirp_name(self):
        with mock.patch.object(server, "TTS_PROVIDER", "cloud"):
            self.assertEqual(server._cloud_tts_voice_name("Puck"), "en-US-Chirp3-HD-Puck")

    def test_every_cast_member_resolves_under_cloud(self):
        # The catalogue is the contract: no NPC may end up without a voice.
        for npc_id, voice in server.NPC_TTS_VOICES.items():
            with self.subTest(npc=npc_id):
                self.assertTrue(voice)
                self.assertIn("Chirp3-HD", server._cloud_tts_voice_name(voice))


class CloudTTSSynthesisTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.account_path, _ = _write_service_account(Path(self._tmp.name))
        for patch in (
            mock.patch.object(server, "CLOUD_TTS_CREDENTIALS", str(self.account_path)),
            mock.patch.object(server, "TTS_PROVIDER", "cloud"),
            mock.patch.object(server, "CLOUD_TTS_SPEAKING_RATE", 1.0),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        server._CLOUD_TTS_SERVICE_ACCOUNT = {}
        server._CLOUD_TTS_TOKEN = {"value": "ya29.fixed", "expires_at": 1e12}

    def _capture_synthesis(self, audio: bytes = b"RIFF....WAVE") -> dict:
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.headers)
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse({"audioContent": base64.b64encode(audio).decode("ascii")})

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            captured["audio"] = server._synthesize_speech("Water, please.", "rex", 0.85)
        return captured

    def test_request_shape_and_pace_are_sent(self):
        captured = self._capture_synthesis()
        self.assertEqual(captured["url"], server.CLOUD_TTS_ENDPOINT)

        payload = captured["payload"]
        self.assertEqual(payload["input"]["text"], "Water, please.")
        self.assertEqual(payload["voice"]["name"], "en-US-Chirp3-HD-Charon")
        self.assertEqual(payload["voice"]["languageCode"], "en-US")
        self.assertEqual(payload["audioConfig"]["audioEncoding"], "LINEAR16")
        self.assertEqual(payload["audioConfig"]["sampleRateHertz"], 24000)
        self.assertAlmostEqual(payload["audioConfig"]["speakingRate"], 0.85, places=6)

        # LINEAR16 already carries a WAV header upstream, so no re-wrap happens.
        self.assertEqual(captured["audio"], b"RIFF....WAVE")

    def test_bearer_token_and_project_header_are_attached(self):
        captured = self._capture_synthesis()
        self.assertEqual(captured["headers"].get("Authorization"), "Bearer ya29.fixed")
        self.assertEqual(captured["headers"].get("X-goog-user-project"), "nativelingo-test")

    def test_rate_is_clamped_to_the_documented_range(self):
        self.assertAlmostEqual(server._effective_speaking_rate(0.01), 0.25, places=6)
        self.assertAlmostEqual(server._effective_speaking_rate(9.0), 2.0, places=6)
        self.assertAlmostEqual(server._effective_speaking_rate(0.9), 0.9, places=6)

    def test_empty_audio_is_rejected(self):
        def fake_urlopen(request, timeout=None):
            return _FakeResponse({"audioContent": ""})

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(RuntimeError) as caught:
                server._synthesize_speech("Hello.", "rex")
        self.assertIn("empty audio", str(caught.exception))

    def test_http_error_surfaces_as_runtime_error(self):
        import urllib.error

        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                server.CLOUD_TTS_ENDPOINT, 403, "Forbidden", {}, None
            )

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(RuntimeError) as caught:
                server._synthesize_speech("Hello.", "rex")
        self.assertIn("HTTP 403", str(caught.exception))

    def test_paced_variants_never_share_a_cache_key(self):
        base = server._tts_key("mira", "r1", "Kore", 1.0)
        slow = server._tts_key("mira", "r1", "Kore", 0.85)
        slower = server._tts_key("mira", "r1", "Kore", 0.80)
        self.assertEqual(len({base, slow, slower}), 3)
        self.assertEqual(base, "mira/r1/Kore")
        self.assertEqual(slow, "mira/r1/Kore@r0.85")

        text_base = server._tts_text_key("mira", "Kore", "Hello.", 1.0)
        text_slow = server._tts_text_key("mira", "Kore", "Hello.", 0.85)
        self.assertNotEqual(text_base, text_slow)

    def test_non_cloud_providers_keep_their_original_keys(self):
        with mock.patch.object(server, "TTS_PROVIDER", "xai"):
            self.assertEqual(server._tts_key("mira", "r1", "eve"), "mira/r1/eve")
            self.assertEqual(
                server._tts_key("mira", "r1", "eve", 0.85), "mira/r1/eve"
            )

    def test_configured_requires_credentials(self):
        with mock.patch.object(server, "_cloud_tts_credentials_path", lambda: "/tmp/sa.json"):
            self.assertTrue(server._tts_configured())
        with mock.patch.object(server, "_cloud_tts_credentials_path", lambda: ""):
            self.assertFalse(server._tts_configured())


class PitchDetectorTest(unittest.TestCase):
    """The acceptance script's verdict is only worth trusting if the detector
    separates a resampled slowdown from a pitch-preserving one."""

    SAMPLE_RATE = 24000
    BASE_F0 = 150.0

    def _voiced_signal(self, seconds: float) -> "object":
        import numpy as np

        time = np.arange(int(self.SAMPLE_RATE * seconds)) / self.SAMPLE_RATE
        return sum(
            np.sin(2 * np.pi * self.BASE_F0 * harmonic * time) / harmonic
            for harmonic in range(1, 12)
        ) * 0.3

    def _stretch(self, signal, factor: float):
        import numpy as np

        return np.interp(
            np.linspace(0, signal.size - 1, int(signal.size * factor)),
            np.arange(signal.size),
            signal,
        )

    def test_detector_reads_the_known_pitch(self):
        import verify_cloud_tts

        measured = verify_cloud_tts.median_f0(self._voiced_signal(2.0), self.SAMPLE_RATE)
        self.assertIsNotNone(measured)
        self.assertAlmostEqual(measured, self.BASE_F0, delta=1.0)

    def test_resampled_slowdown_is_flagged(self):
        import verify_cloud_tts

        baseline = verify_cloud_tts.median_f0(self._voiced_signal(2.0), self.SAMPLE_RATE)
        for speed in (0.80, 0.90):
            with self.subTest(speed=speed):
                stretched = self._stretch(self._voiced_signal(2.0), 1.0 / speed)
                f0 = verify_cloud_tts.median_f0(stretched, self.SAMPLE_RATE)
                drift = f0 / baseline - 1.0
                # A resampled slowdown drops F0 by exactly the speed ratio.
                self.assertLess(abs(drift - (speed - 1.0)), verify_cloud_tts.PITCH_TOLERANCE)
                self.assertTrue(
                    abs(drift + (1.0 - speed)) < verify_cloud_tts.PITCH_TOLERANCE
                )

    def test_pitch_preserving_slowdown_is_not_flagged(self):
        import verify_cloud_tts

        baseline = verify_cloud_tts.median_f0(self._voiced_signal(2.0), self.SAMPLE_RATE)
        # Same F0 held for longer: the shape a real slow-down must have.
        held = verify_cloud_tts.median_f0(self._voiced_signal(2.5), self.SAMPLE_RATE)
        drift = held / baseline - 1.0
        self.assertLess(abs(drift), verify_cloud_tts.PITCH_TOLERANCE)
        self.assertFalse(abs(drift + 0.2) < verify_cloud_tts.PITCH_TOLERANCE)


if __name__ == "__main__":
    unittest.main()
