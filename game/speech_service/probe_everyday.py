"""Opt-in live FR-47 content probe. Uses typed fixtures, not player microphone audio.
Run from the repository root: .venv/bin/python game/speech_service/probe_everyday.py
"""
import json
import wave
import io
import server


def main():
    destination = server.REPO_ROOT / 'docs/reviews/everyday_inventory_2026-09-11'
    destination.mkdir(parents=True, exist_ok=True)
    server._probe_gemini()
    cases = [
        ('tavi', 'food_counter', 'Long morning. I could use something to eat.', 'Can I get a sandwich to go, please?'),
        ('ori', 'convenience_store', 'Do you carry batteries?', "Yes, I'll take some batteries, please."),
        ('vesh', 'parts_desk', "It's been cold at home lately.", 'Could I get an extra blanket, please?'),
    ]
    evidence = {'input': 'typed fixture transcripts; no microphone or pronunciation assessment', 'turns': []}
    server._TTS_PREFETCH_ENABLED = False
    for npc, scenario, first, second in cases:
        history = []
        for index, text in enumerate([first, second]):
            reply = server.generate_dialogue_reply({
                'npc_id': npc, 'scenario_id': scenario, 'session_id': f'everyday-live-{npc}',
                'transcript': text, 'history': history, 'game_context': {'player_level': 'toddler'},
                'require_live_dialogue': True,
            })
            evidence['turns'].append({'npc': npc, 'player': text, 'reply': reply})
            (destination / 'live-dialogue.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
            assert reply['gate']['accepted'], reply
            assert bool(reply['player_turn']['transaction_complete']) == (index == 1), reply
            history.extend([{'role': 'player', 'text': text}, {'role': 'npc', 'text': reply['text']}])
    npc, line, text = server.NOVEL_DAILY_LIFE[1]['lines'][1]
    audio = server.synthesize_npc_line(npc, line)
    with wave.open(io.BytesIO(audio)) as wav:
        evidence['tts'] = {'provider': server.TTS_PROVIDER, 'line': line, 'text': text, 'seconds': wav.getnframes() / wav.getframerate()}
        assert evidence['tts']['seconds'] > 0.3
    (destination / 'daily-life-sample.wav').write_bytes(audio)
    (destination / 'live-dialogue.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print('PASS: six live everyday turns and shared-catalog US TTS')


if __name__ == '__main__':
    main()
