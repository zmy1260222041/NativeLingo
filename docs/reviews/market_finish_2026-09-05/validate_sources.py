"""Read-only Blender source/export validation; only writes a review report."""
from pathlib import Path
import hashlib
import json
import struct

import bpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / 'art/source/environment/env_market_corner/quality_pass_v01'
LIMITS = {
    'env_ground_market_a': 2048,
    'env_market_stall_a': 2048,
    'env_plaza_market_a': 1024,
    'fol_ground_tufts_a': 1024,
    'fol_tree_stranger_a': 1024,
    'prp_market_burger_v01': 512,
    'prp_market_wrap_v01': 512,
    'prp_market_drink_v01': 512,
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


results = {}
for stem, limit in LIMITS.items():
    directory = SOURCE / stem
    bpy.ops.wm.open_mainfile(filepath=str(directory / (stem + '.blend')))
    high = bpy.data.collections.get('HIGH_BAKE_SOURCES')
    assert high and len(high.objects), (stem, 'missing high-poly sources')
    assert all(o.hide_render and o.hide_get() for o in high.objects), (stem, 'visible bake source')
    lows = [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('lod')]
    visible = [o.name for o in lows if not o.hide_get() and not o.hide_render]
    assert len(visible) == 1 and visible[0].startswith('lod0__'), (stem, visible)
    maps = {}
    for channel in ('base_color', 'normal', 'ao', 'roughness', 'orm'):
        name = stem + '_' + channel
        image = bpy.data.images.get(name)
        assert image and image.packed_file, (stem, channel, 'not packed')
        assert tuple(image.size) == (limit, limit), (stem, channel, tuple(image.size))
        expected = 'sRGB' if channel == 'base_color' else 'Non-Color'
        assert image.colorspace_settings.name == expected, (stem, channel, 'color space')
        external = bpy.data.images.load(str(directory / (name + '.png')), check_existing=False)
        assert tuple(external.size) == (limit, limit), (stem, channel, 'external size')
        maps[channel] = {'size': list(image.size), 'packed': True, 'color_space': expected}
        bpy.data.images.remove(external)
    assert bpy.context.scene.render.bake.use_selected_to_active
    assert not bpy.context.scene.render.bake.use_pass_direct
    assert not bpy.context.scene.render.bake.use_pass_indirect
    glb = directory / (stem + '.glb')
    content = glb.read_bytes()
    assert content[:4] == b'glTF'
    length, kind = struct.unpack_from('<II', content, 12)
    assert kind == 0x4E4F534A
    gltf = json.loads(content[20:20 + length])
    meshes = {}
    for node in gltf['nodes']:
        if 'mesh' not in node:
            continue
        mesh = gltf['meshes'][node['mesh']]
        assert all(p.get('mode', 4) == 4 for p in mesh['primitives'])
        meshes[node['name']] = sum(gltf['accessors'][p['indices']]['count'] // 3 for p in mesh['primitives'])
    assert len(gltf['materials']) == 1, (stem, 'material slots')
    assert len(gltf['images']) == 3, (stem, 'embedded maps')
    sha = digest(glb)
    assert digest(ROOT / 'game/assets/environment' / (stem + '.glb')) == sha, (stem, 'runtime/source mismatch')
    report = json.loads((directory / 'bake_report.json').read_text())
    assert report['sha256'] == sha, (stem, 'stale bake report')
    results[stem] = {
        'passed': True,
        'source_high_objects': len(high.objects),
        'visible_source_meshes': visible,
        'maps': maps,
        'export_triangles_by_node': meshes,
        'export_material_slots': 1,
        'runtime_matches_source': True,
        'glb_sha256': sha,
    }
    print('SOURCE PASS', stem, meshes, flush=True)

(HERE / 'source_validation.json').write_text(json.dumps(results, indent=2) + '\n')
print('SOURCE VALIDATION PASSED', len(results), flush=True)
