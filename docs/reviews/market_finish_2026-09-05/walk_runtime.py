"""Exercise the real player controller and capture its third-person camera.

Only initial placement is set directly; all travel uses move_forward input and
camera yaw, so collisions and character steering remain active.
"""
from pathlib import Path
import asyncio
import base64
import json
import math
import websockets

HERE=Path(__file__).resolve().parent

async def main():
    samples=[]
    async with websockets.connect('ws://127.0.0.1:6505',max_size=16000000) as ws:
        sequence=0
        async def rpc(method,params):
            nonlocal sequence
            sequence+=1
            await ws.send(json.dumps({'jsonrpc':'2.0','id':sequence,'method':method,'params':params}))
            value=json.loads(await asyncio.wait_for(ws.recv(),25))
            if 'error' in value:raise RuntimeError(value)
            return value['result']
        async def setting(node,prop,value):
            return await rpc('game.set_property',{'node_path':node,'property':prop,'value':value})
        async def action(name,pressed):
            await rpc('input.simulate_action',{'action':name,'pressed':pressed})
        async def state():
            full=await rpc('animation.get_state',{})
            player=full['player']
            player['render_draw_calls']=full.get('render_draw_calls')
            player['frame_delta_ms']=full.get('frame_delta_ms')
            return player
        async def capture(name):
            frame=await rpc('game.capture_frames',{'max_dim':1440})
            (HERE/(name+'.jpg')).write_bytes(base64.b64decode(frame['data']))
            samples.append({'capture':name,'state':await state()})
        await setting('/root/GameState','persistence_enabled',False)
        await setting('/root/GameState','interaction_time_frozen',True)
        await setting('/root/GameState','day_time',90.0)
        await rpc('game.restore_view',{})
        await rpc('game.bring_to_front',{})
        await setting('/root/Main/Player','position',[0,.03,8])
        await setting('/root/Main/Player','rotation',[0,0,0])
        await rpc('control.freeze',{'frozen':False})
        await asyncio.sleep(.4)
        await capture('walk_00_entry_day')
        reached=[]
        async def walk_to(x,z,label):
            await action('move_forward',True)
            success=False
            try:
                for _ in range(150):
                    current=await state();p=current['global_position']
                    dx,dz=x-p[0],z-p[2]
                    if math.hypot(dx,dz)<.28:
                        success=True;break
                    await setting('/root/Main/Player','rotation',[0,math.atan2(-dx,-dz),0])
                    samples.append({'leg':label,'state':current})
                    await asyncio.sleep(.04)
            finally:
                await action('move_forward',False)
            await asyncio.sleep(.35)
            reached.append({'leg':label,'passed':success,'target':[x,z],'position':(await state())['global_position']})
            print(reached[-1],flush=True)
            await capture(label)
        await walk_to(0,4.7,'walk_01_path_day')
        await walk_to(-.45,1.0,'walk_02_approach_day')
        await walk_to(-1.65,-.55,'walk_03_service_day')
        # Real gamepad look input; camera rotates without translating the player.
        for name,duration in [('camera_left',.40),('camera_right',.80)]:
            await action(name,True);await asyncio.sleep(duration);await action(name,False)
            await capture('walk_04_'+name)
        await setting('/root/GameState','day_time',285.0)
        await asyncio.sleep(.4)
        await capture('walk_05_service_night')
        await walk_to(-.2,2.9,'walk_06_return_night')
        await walk_to(0,8,'walk_07_entry_night')
        result={'method':'real player input + CharacterBody3D collision, not waypoint teleport','reached':reached,'samples':samples}
        (HERE/'walk_results.json').write_text(json.dumps(result,indent=2)+'\n')
        await setting('/root/GameState','day_time',90.0)
        await setting('/root/Main/Player','rotation',[0,0,0])
        if not all(item['passed'] for item in reached):raise RuntimeError('A walk leg was blocked')

asyncio.run(main())
