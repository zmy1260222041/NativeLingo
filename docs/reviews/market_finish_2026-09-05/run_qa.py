"""Repeatable scoped regression. Captures full output and real exit status."""
from pathlib import Path
import json
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
GODOT='/Applications/Godot-4.6.app/Contents/MacOS/Godot'
CASES={
 'material_lod':['--script','res://tests/test_env_material_contract.gd'],
 'environment_assets':['--script','res://tests/test_market_corner_asset.gd'],
 'main_integration':['res://tests/MainEnvIntegration.tscn'],
 'npc_workplace':['--script','res://tests/test_npc_dialogue_assets.gd'],
 'social_counter_clearance':['res://tests/SocialDialogueTest.tscn'],
 'desktop_no_voice':['res://tests/DesktopBetaNoVoiceTest.tscn'],
}
results={}
for name,args in CASES.items():
    command=[GODOT,'--headless','--path',str(ROOT/'game')]+args
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=55)
        output=result.stdout+result.stderr
        (HERE/(name+'.log')).write_text(output)
        results[name]={'exit_code':result.returncode,'command':command,'script_errors':'SCRIPT ERROR:' in output,'engine_errors':'ERROR:' in output}
    except subprocess.TimeoutExpired:
        results[name]={'exit_code':None,'timeout':True,'command':command}
    print(name,results[name],flush=True)
(HERE/'regression_results.json').write_text(json.dumps(results,indent=2)+'\n')
raise SystemExit(0 if all(v['exit_code']==0 and not v.get('engine_errors',False) for v in results.values()) else 1)
