"""Same-camera day/dusk/night evidence and actual, uncapped root-window timings.

Launch Godot at 1440x900 first; keep the window on screen during profiling.
Game persistence is disabled for review. No gameplay state is written to disk.
"""
from pathlib import Path
import asyncio
import json
import shutil
import sys
import websockets

HERE=Path(__file__).resolve().parent
CAMERAS={
 'arrival':{'position':'0,2.8,13.4','look_at':'0,1.2,0','fov':68},
 'counter':{'position':'0,2.6,1.3','look_at':'-1.8,1.5,-2.2','fov':60},
 'overview':{'position':'18,15,24','look_at':'0,1,0','fov':65},
 'water':{'position':'10,2.6,12.4','look_at':'9.7,1.0,8','fov':65},
 'heater':{'position':'-1,2.7,9.5','look_at':'-6.1,1.2,7.2','fov':65},
}

async def main():
    results={}
    async with websockets.connect('ws://127.0.0.1:6505',max_size=16000000) as ws:
        counter=0
        async def rpc(method,params):
            nonlocal counter
            counter+=1
            await ws.send(json.dumps({'jsonrpc':'2.0','id':counter,'method':method,'params':params}))
            response=json.loads(await asyncio.wait_for(ws.recv(),45))
            if 'error' in response:raise RuntimeError(response)
            return response['result']
        async def state(prop,value):
            return await rpc('game.set_property',{'node_path':'/root/GameState','property':prop,'value':value})
        await state('persistence_enabled',False)
        await state('interaction_time_frozen',True)
        await rpc('control.freeze',{'frozen':True})
        await rpc('game.bring_to_front',{})
        for phase,clock in [('day',90.0),('dusk',237.0),('night',285.0)]:
            await state('day_time',clock)
            for view,pose in CAMERAS.items():
                if view not in ['arrival','counter'] and phase=='dusk':continue
                name='after_'+view+'_'+phase
                captured=await rpc('game.capture_view',dict(pose,name=name,max_dim=1440))
                shutil.copy2(captured['path'],HERE/(name+'.jpg'))
                print('CAPTURED',name,flush=True)
                if view in ['arrival','counter'] and '--profile' in sys.argv:
                    sample=await rpc('game.profile_view',dict(pose,frames=360))
                    results[view+'_'+phase]=sample
                    print('MEASURED',view,phase,{k:v for k,v in sample.items() if k!='raw'},flush=True)
        if results:(HERE/'frame_measurements.json').write_text(json.dumps(results,indent=2)+'\n')
        await state('day_time',90.0)
        await rpc('control.freeze',{'frozen':False})
        # A paused day clock is intentional for viewing; player remains walkable.

asyncio.run(main())
