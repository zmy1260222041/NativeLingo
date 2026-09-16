"""Opt-in real model narrative checks; synthetic text only, no player save or mic."""
import json
from pathlib import Path
import server
server._TTS_PREFETCH_ENABLED = False

def run(npc, scenario, text, history=None, contact=None, opening=False):
    body=dict(npc_id=npc,scenario_id=scenario,transcript=text,history=history or [],require_live_dialogue=True,game_context=dict(player_level='youth',town_contact=contact or {},turn_kind='opening' if opening else 'reply'))
    events=list(server.iter_dialogue_events(body))
    speech=next(e['data'] for e in events if e['event']=='speaking')
    score=next(e['data'] for e in events if e['event']=='score')
    assert speech['source'] in ['gemini','grok']
    row=dict(npc=npc,player=text,reply=speech['text'],contact=contact or {},complete=score['player_turn']['transaction_complete'])
    print(json.dumps(row,ensure_ascii=False),flush=True)
    return row

if __name__=='__main__':
    folder=Path('docs/reviews/town-belonging-2026-09-14');folder.mkdir(parents=True,exist_ok=True)
    rows=[]
    for npc,scene in [('mira','market_conversation'),('tavi','food_counter'),('ori','convenience_store'),('vesh','parts_desk'),('rowan','neighbor_conversation')]:
        row=run(npc,scene,"I'm new here. I don't know anyone or how things work.")
        assert not row['complete'];rows.append(row)
    rows.append(run('mira','market_conversation','[NPC opens conversation]',opening=True))
    shared=[{'role':'player','text':'I find Vesh a bit intimidating.'},{'role':'npc','text':'He is brief with everyone. You can start by telling him what needs fixing.'}]
    rows.append(run('mira','market_conversation','[NPC opens conversation]',shared,{'completed_exchanges':5,'days_met':2},True))
    rows.append(run('rowan','neighbor_conversation','Do you remember me?',contact={'completed_exchanges':4,'days_met':2,'helped_rowan':True}))
    rows.append(run('vesh','parts_desk',"I'd like to buy alloy, please."))
    assert rows[-1]['complete']
    (folder/'live.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
