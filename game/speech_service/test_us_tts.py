"""US voice transport invariants; all network traffic is mocked."""
import io
import unittest
from unittest import mock
import wave
import server


class USTtsTest(unittest.TestCase):
    def setUp(self):
        provider = mock.patch.object(server, 'TTS_PROVIDER', 'xai')
        provider.start()
        self.addCleanup(provider.stop)
        server._TTS_CACHE.clear()

    def response(self, chunks, status=200, content_type='audio/pcm'):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status_code = status
        response.headers = {'Content-Type': content_type}
        response.iter_content.return_value = iter(chunks)
        return response

    def test_us_pcm_is_aligned_bounded_and_wrapped_as_valid_wav(self):
        session = mock.Mock()
        session.post.return_value = self.response([b'\x01', b'\x02' * 99])
        with mock.patch.object(server, '_xai_api_key', return_value='fixture'), mock.patch.object(server, '_xai_tts_session', return_value=session):
            audio = server._synthesize_speech('water', 'eve')
        args, kwargs = session.post.call_args
        self.assertEqual(args[0], 'https://api.x.ai/v1/tts')
        self.assertEqual(kwargs['json']['language'], 'en')
        self.assertEqual(kwargs['json']['voice_id'], 'eve')
        self.assertFalse(kwargs['allow_redirects'])
        with wave.open(io.BytesIO(audio)) as wav:
            self.assertEqual((wav.getframerate(), wav.getnchannels(), wav.getsampwidth()), (24000, 1, 2))
            self.assertEqual(wav.getnframes(), 50)

    def test_failure_never_falls_back_to_beijing(self):
        session = mock.Mock()
        session.post.return_value = self.response([], 401, 'application/json')
        with mock.patch.object(server, '_xai_api_key', return_value='fixture'), mock.patch.object(server, '_xai_tts_session', return_value=session), mock.patch.object(server, '_dashscope_speech') as legacy:
            with self.assertRaises(RuntimeError):
                server._synthesize_speech('water', 'eve')
            legacy.assert_not_called()

    def test_incomplete_pcm_is_rejected(self):
        session = mock.Mock()
        session.post.return_value = self.response([b'0' * 33])
        with mock.patch.object(server, '_xai_api_key', return_value='fixture'), mock.patch.object(server, '_xai_tts_session', return_value=session):
            with self.assertRaises(RuntimeError):
                list(server._xai_tts_pcm('water', 'eve'))

    def test_stream_cache_written_only_after_complete_audio(self):
        reply = server._register_spoken_reply('tavi', 'Here is your taco.', False, prefetch=False)
        with mock.patch.object(server, '_xai_tts_pcm', return_value=iter([b'0' * 100, b'1' * 100])):
            stream = server._stream_dynamic_reply_audio('tavi', reply)
            self.assertEqual(next(stream), b'0' * 100)
            self.assertFalse(server._TTS_CACHE)
            self.assertEqual(b''.join(stream), b'1' * 100)
            self.assertTrue(server._TTS_CACHE)


if __name__ == '__main__':
    unittest.main()
