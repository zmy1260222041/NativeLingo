"""Real campus endpoint acceptance. Synthetic text inputs; no user diary/audio."""
from __future__ import annotations
import json
import threading
import time
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
import campus
import server

OUTPUT = Path(__file__).resolve().parents[2] / 'docs/reviews/campus_unified_2026-09-12'
CASES = {
 'class_project_roles': [
  'I can work on the outline, but I am not sure how much detail we need.',
  'I usually write too much because I worry that I have not explained my reasoning.',
  'Last time I spent the whole evening on an introduction and had to rush the examples.',
  'I see your point, but I worry that splitting everything up means our argument will not fit together.',
  'Could you explain what you mean by checking the structure first? I follow the idea, but not the process.',
  'What if we each bring one example and spend the first ten minutes deciding what they support?',
  'I cannot stay late on Thursday. Would a shorter session after class work for you?',
  'That gives me a clearer starting point. I need to head out now, but I would like to continue this next time.'
 ],
 'club_join_group': [
  'Mind if I jump in? I heard you talking about the next event, but I missed the beginning.',
  'I like photography, but I have never been part of a club before, so I am not sure what I could contribute.',
  'When I tried taking photos with a friend, talking about why we chose each shot was the most interesting part.',
  'I get why a casual gathering would be welcoming. I would still like one small thing we can actually work on.',
  'When you say beginner friendly, do you mean no equipment or no experience?',
  'Could we pair people up and let each pair choose something to photograph nearby?',
  'I could help with planning, but I cannot commit to running the whole event. Would that still be useful?',
  'Thanks for letting me join the conversation. I have to leave now, but I would like to hear how the plan develops.'
 ],
 'dining_story': [
  'It took me a while to feel comfortable eating with people here. I used to worry about interrupting.',
  'One day someone asked about a book I was carrying, and that gave me something real to talk about.',
  'I am more comfortable talking about an experience than answering a list of questions about myself.',
  'I am not sure joining more activities always helps. Sometimes I just want to know one person better.',
  'What makes a conversation feel comfortable for you? Could you give me an example?',
  'That reminds me of a friend who could disagree with me without making it feel awkward.',
  'I would like to get better at that. If you disagreed with what I just said, how would you put it?',
  'I have enjoyed talking about this. I should get going, but would you be up for lunch again sometime?'
 ],
 'sports_mistake': [
  'I saw that differently, but I might have missed the first part. Can we talk through what happened?',
  'I thought we were pausing, so I stopped moving. I should have checked instead of assuming.',
  'I get frustrated when I make that kind of mistake because I do not want to let the group down.',
  'I agree that keeping things friendly matters, but I still want us to be consistent about what we decide.',
  'When you say we should restart, do you mean repeat that part or start the whole activity again?',
  'Could we agree on a clear signal before we continue? That would help me avoid the same misunderstanding.',
  'I am okay with that compromise. Next time I will ask if I am unsure instead of guessing.',
  'Thanks for talking it through. I need to leave soon, but I would like to join you again.'
 ]}


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    server._TTS_PREFETCH_ENABLED = False
    service = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=service.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{service.server_port}'
    report = {'source': 'live endpoint, synthetic authored player text', 'cases': [], 'failures': [], 'started_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    try:
        for scene_id, utterances in CASES.items():
            history, summary = [], ''
            case = {'scenario': scene_id, 'turns': []}
            print('CASE', scene_id, flush=True)
            for number, utterance in enumerate(utterances, 1):
                body = {'scenario_id': scene_id, 'participants': campus.SCENARIOS[scene_id]['participants'],
                        'session_id': 'probe-' + scene_id, 'turn_id': str(number), 'turn_index': number - 1, 'transcript': utterance,
                        'history': history[-16:], 'topic_summary': summary,
                        'profile': {'major': 'Computer science', 'clubs': 'Photography', 'sports': 'recreational sports', 'level': 'professional'}}
                started = time.perf_counter()
                req = urllib.request.Request(url + '/game/campus/dialogue', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
                try:
                    with urllib.request.urlopen(req, timeout=90) as response: result = json.load(response)
                    lines = [e['data'] for e in result['events'] if e['event'] == 'speaking']
                    done = result['events'][-1]['data']
                    assert lines and all(line['source'] in ['gemini', 'grok'] and line['model'] for line in lines)
                    history.append({'speaker_id': 'player', 'reply_to': 'group', 'text': utterance})
                    history.extend({k: line[k] for k in ['speaker_id', 'reply_to', 'text']} for line in lines)
                    summary = done['topic_summary']
                    record = {'player': utterance, 'replies': lines, 'receipt': done, 'seconds': round(time.perf_counter() - started, 3)}
                    if number == 1:
                        audio_checks = []
                        for line in lines:
                            tts = urllib.request.Request(url + '/game/tts', data=json.dumps({'npc_id': line['speaker_id'], 'reply_id': line['reply_id']}).encode(), headers={'Content-Type': 'application/json'})
                            with urllib.request.urlopen(tts, timeout=60) as response: wav = response.read()
                            assert wav[:4] == b'RIFF' and len(wav) > 44
                            path = OUTPUT / (scene_id + '-' + line['speaker_id'] + '.wav')
                            path.write_bytes(wav)
                            audio_checks.append({'speaker': line['speaker_id'], 'voice': server.NPC_TTS_VOICES[line['speaker_id']], 'bytes': len(wav), 'file': path.name})
                        record['tts'] = audio_checks
                    case['turns'].append(record)
                    print(scene_id, number, len(lines), record['seconds'], 'seconds', flush=True)
                except Exception as exc:
                    reason = exc.read().decode('utf-8', errors='replace')[:1000] if hasattr(exc, 'read') else str(exc)
                    report['failures'].append({'scenario': scene_id, 'turn': number, 'error': type(exc).__name__, 'reason': reason})
                    print('FAIL', scene_id, number, type(exc).__name__, flush=True)
                    break
            report['cases'].append(case)
            (OUTPUT / 'live-dialogue.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        service.shutdown()
        service.server_close()
    report['passed'] = not report['failures'] and all(len(case['turns']) == 8 for case in report['cases'])
    (OUTPUT / ('live-dialogue-' + time.strftime('%H%M%S') + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (OUTPUT / 'live-dialogue.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print('PASS' if report['passed'] else 'FAIL', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__': raise SystemExit(run())
