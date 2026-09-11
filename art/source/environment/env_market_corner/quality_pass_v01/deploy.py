"""Deploy only this reviewed derivative's named runtime outputs.

Old source files remain locked. Cached Godot scene imports are recoverable and
are invalidated after the post-import hook changes; source .import UIDs remain.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
ENV=ROOT/'game/assets/environment'
STEMS=['env_market_stall_a','env_ground_market_a','fol_tree_stranger_a','fol_ground_tufts_a','env_plaza_market_a','prp_market_burger_v01','prp_market_wrap_v01','prp_market_drink_v01']

subprocess.run(['python3',str(ROOT/'art/source/environment/verify_env_asset_locks.py')],check=True)
for stem in STEMS:
    source=HERE/stem/(stem+'.glb')
    assert source.is_file(),source
    shutil.copy2(source,ENV/source.name)
    print('DEPLOY',stem,hashlib.sha256(source.read_bytes()).hexdigest())
cached_root=(ROOT/'game/.godot/imported').resolve()
for settings in ENV.glob('*.glb.import'):
    match=re.search(r'^path="res://(.+\.scn)"',settings.read_text(),re.M)
    if match:
        cached=(ROOT/'game'/match[1]).resolve()
        assert cached.parent==cached_root
        if cached.is_file():
            cached.unlink()
            print('INVALIDATED REGENERABLE IMPORT',cached.name)
