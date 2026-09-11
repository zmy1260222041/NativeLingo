"""Archive every bake layer inside the .blend; does not change runtime exports."""
from pathlib import Path
import json

import bpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
manifest = json.loads((ROOT / 'art/source/environment/ASSET_LOCK_MANIFEST.json').read_text())
protected = {item['path'] for asset in manifest['assets'] for item in asset['files']}
blends = sorted(HERE.glob('*/*.blend'))
assert not any(str(p.relative_to(ROOT)) in protected for p in blends), 'Create a new version before editing locked sources'
bpy.context.preferences.filepaths.save_version = 0
for source in blends:
    bpy.ops.wm.open_mainfile(filepath=str(source))
    stem = source.stem
    for channel in ('base_color', 'normal', 'ao', 'roughness', 'orm'):
        name = stem + '_' + channel
        image = bpy.data.images.get(name)
        if image is None:
            image = bpy.data.images.load(str(source.parent / (name + '.png')))
            image.name = name
        image.colorspace_settings.name = 'sRGB' if channel == 'base_color' else 'Non-Color'
        image.use_fake_user = True
        image.pack()
        image.filepath_raw = '//' + name + '.png'
    bpy.ops.wm.save_as_mainfile(filepath=str(source))
    path = source.parent / 'bake_report.json'
    report = json.loads(path.read_text())
    report['maps']['roughness'] = str((source.parent / (stem + '_roughness.png')).relative_to(ROOT))
    report['all_five_maps_packed'] = True
    path.write_text(json.dumps(report, indent=2) + '\n')
    print('PACKED SOURCE', stem, flush=True)
