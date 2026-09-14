"""Real-model cross-day memory acceptance using authored synthetic player facts.

Runs all eight four-day chains through the HTTP endpoint. Local state tests
separately cover ledger authority; this probe inspects actual speaker payloads,
model replies, and corrections/deletions in fresh sessions without history.
"""
import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import campus
import server

OUTPUT = Path(__file__).resolve().parents[2] / 'docs/reviews/campus_unified_2026-09-12'


def invalidate(ledger, identifier, replacement=None):
    stale = {identifier}
    for memory in ledger:
        if stale.intersection(memory.get('derived_from', [])):
            stale.add(memory['id'])
    remaining = [m for m in ledger if m['id'] not in stale or (m['id'] == identifier and replacement)]
    if replacement:
        next(m for m in remaining if m['id'] == identifier)['text'] = replacement
    return remaining


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    service = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=service.serve_forever, daemon=True).start()
    endpoint = f'http://127.0.0.1:{service.server_port}/game/campus/dialogue'
    report = {'source':'real model via local HTTP endpoint; authored synthetic inputs', 'chains':[], 'failures':[]}
    try:
        for chain in campus.CATALOG['chains']:
            ledger, milestones, records = [], [], []
            seed_id = ''
            serial = 0
            for index, scene_id in enumerate(chain['steps']):
                scene = campus.SCENARIOS[scene_id]
                if index == 0:
                    utterance = scene['example'][1]['text'] + ' Also, please remember that I meet a friend at Cedar Hall on Fridays.'
                else:
                    if index == 2 and seed_id:
                        ledger = invalidate(ledger, seed_id, 'I meet a friend at Willow Library on Fridays.')
                    if index == 3 and seed_id:
                        ledger = invalidate(ledger, seed_id)
                    utterance = scene['example'][1]['text'] + ' Before we continue, do you remember where I meet my friend on Fridays? It is okay if we have not talked about it.'
                relevant = [m for m in ledger if set(m['known_to']).intersection(scene['participants'])][-24:]
                if index in [1,2]:
                    knowers = [p for p in scene['participants'] if any(p in m['known_to'] and ('Cedar Hall' in m['text'] or 'Willow Library' in m['text']) for m in relevant)]
                    if knowers: utterance = campus.PROFILES[knowers[0]]['name'] + ', ' + utterance
                body = {'scenario_id':scene_id, 'participants':scene['participants'], 'session_id':f'{chain["id"]}-day-{index+1}',
                        'turn_id':f'{chain["id"]}:{index+1}', 'transcript':utterance, 'history':[], 'topic_summary':'',
                        'memories':relevant, 'profile':{'level':'professional'}, 'game_time':{'day':index+1,'hour':15},
                        'relationships':{p:('acquaintance' if any(p in m['known_to'] for m in milestones) else 'stranger') for p in scene['participants']},
                        'chain_context':[{'title':chain['title'], 'focus':chain['stages'][index]['focus'], 'milestones':milestones}]}
                try:
                    context = campus.prepare(body)
                    outgoing = {p:campus.speaker_payload(context,p,[]) for p in scene['participants']}
                    for p,payload in outgoing.items():
                        allowed = {m['text'] for m in relevant if p in m['known_to']}
                        assert {m['quote'] for m in payload['known_memories']} <= allowed
                        if index >= 2: assert 'Cedar Hall' not in json.dumps(payload), 'obsolete place remains in outgoing context'
                        if index == 3: assert 'Willow Library' not in json.dumps(payload), 'deleted place remains in outgoing context'
                    req = urllib.request.Request(endpoint,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
                    started = time.perf_counter()
                    with urllib.request.urlopen(req,timeout=90) as response: result = json.load(response)
                    lines = [e['data'] for e in result['events'] if e['event']=='speaking']
                    done = result['events'][-1]['data']
                    assert lines and all(line['source'] in ['gemini','grok'] for line in lines)
                    if index == 1 and any('Cedar Hall' in json.dumps(p['known_memories']) for p in outgoing.values()):
                        assert any('cedar' in line['text'].lower() for line in lines), 'known location not recalled'
                    if index == 2:
                        assert all('cedar' not in line['text'].lower() for line in lines), 'obsolete location recalled'
                        if any('Willow Library' in json.dumps(p['known_memories']) for p in outgoing.values()):
                            assert any('willow' in line['text'].lower() for line in lines), 'corrected location not recalled'
                    if index == 3:
                        assert all('cedar' not in line['text'].lower() and 'willow' not in line['text'].lower() for line in lines), 'deleted location recalled'
                    turn_memories = []
                    for candidate in done.get('memory_candidates',[]):
                        source = candidate['speaker_id']
                        assert ((source=='player' and candidate['text']==utterance) or any(source==line['speaker_id'] and candidate['text']==line['text'] for line in lines))
                        serial += 1
                        memory = dict(candidate,id=f'{chain["id"]}-memory-{serial}', day=index+1, scenario_id=scene_id,
                                      derived_from=list(dict.fromkeys(candidate.get('derived_from',[])+turn_memories)))
                        ledger.append(memory)
                        turn_memories.append(memory['id'])
                        if index==0 and source=='player': seed_id=memory['id']
                    if index==0: assert seed_id, 'specific player fact was not retained'
                    milestones.append({'scenario_id':scene_id,'day':index+1,'known_to':scene['participants']})
                    records.append({'day':index+1,'request':body,'speaker_contexts':outgoing,'replies':lines,'receipt':done,'seconds':round(time.perf_counter()-started,3)})
                    print(chain['id'],index+1,'PASS',flush=True)
                except Exception as exc:
                    report['failures'].append({'chain':chain['id'],'day':index+1,'error':type(exc).__name__,'reason':str(exc),'request':body})
                    print(chain['id'],index+1,'FAIL',type(exc).__name__,str(exc),flush=True)
                    break
            report['chains'].append({'id':chain['id'],'days':records})
            (OUTPUT/'live-continuity.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        service.shutdown()
        service.server_close()
    report['passed'] = not report['failures'] and len(report['chains'])==8 and all(len(c['days'])==4 for c in report['chains'])
    for name in ['live-continuity.json','live-continuity-'+time.strftime('%H%M%S')+'.json']:
        (OUTPUT/name).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('PASS' if report['passed'] else 'FAIL',flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(run())
