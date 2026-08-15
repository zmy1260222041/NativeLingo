class_name EnvLod
extends Node3D
## Runtime LOD controller for hand-modeled environment assets.
##
## Mirrors the character_visual.gd:144-170 manual name-substring LOD contract:
## meshes named "lod0__", "lod1__", "lod2__" (prefix) are grouped by that
## substring and toggled by camera distance. Distances follow art-bible §8.2:
## hero facilities LOD1 50% @12m / LOD2 20% @26m; medium props 12-25m.
##
## Outlines: for a hero asset, each LOD0 mesh is duplicated as an inverted-hull
## child (cel_outline.gdshader) that is hidden past the LOD0->LOD1 boundary
## (12m) — art-bible §3.1.B "远景可关闭，关闭后主形仍须成立".

# Play-field trees/huts sit 10–18 m from the camera. Switching at 12 m made
# lod1 (blob canopy / untextured plates) pop in the middle of the settlement.
const LOD_DIST_HERO := [48.0, 80.0]
const LOD_DIST_PROP := [40.0, 70.0]
const OUTLINE_SHADER := "res://shaders/cel_outline.gdshader"

var _lod_groups: Array = [[], [], []]
var _current_lod := -1
var _hero := false
var _outlines: Array[MeshInstance3D] = []


func configure(hero: bool) -> void:
	_hero = hero


func _ready() -> void:
	var source := get_children()
	if source.is_empty() and get_parent() != null:
		source = get_parent().get_children()
	_collect(source)
	if _hero:
		_build_outlines()
	_set_lod(0)


func _process(_delta: float) -> void:
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return
	var d := global_position.distance_to(cam.global_position)
	var dists := LOD_DIST_HERO if _hero else LOD_DIST_PROP
	_set_lod(0 if d < dists[0] else (1 if d < dists[1] else 2))


func _collect(nodes: Array) -> void:
	for node in nodes:
		if node is MeshInstance3D:
			var lower := String(node.name).to_lower()
			for lod in range(3):
				if "lod%d__" % lod in lower:
					_lod_groups[lod].append(node)
		for c in node.get_children():
			_collect([c])


func _build_outlines() -> void:
	var shader := load(OUTLINE_SHADER) as Shader
	if shader == null:
		push_warning("env_lod: outline shader missing")
		return
	var candidates: Array = _lod_groups[0].duplicate()
	candidates.sort_custom(func(a, b): return _mesh_tris(a) > _mesh_tris(b))
	var limit := mini(6, candidates.size())
	for i in range(limit):
		var mi := candidates[i] as MeshInstance3D
		var om := mi.duplicate() as MeshInstance3D
		om.name = mi.name + "_outline"
		var mat := ShaderMaterial.new()
		mat.shader = shader
		om.material_override = mat
		om.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		(mi.get_parent() as Node3D).add_child(om)
		_outlines.append(om)


func _mesh_tris(mi: MeshInstance3D) -> int:
	if mi.mesh == null:
		return 0
	var total := 0
	for s in range(mi.mesh.get_surface_count()):
		total += mi.mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX].size()
	return total


func _set_lod(n: int) -> void:
	if n == _current_lod:
		return
	_current_lod = n
	for lod in range(3):
		for mi in _lod_groups[lod]:
			(mi as MeshInstance3D).visible = (lod == n)
	var outline_on := _hero and n == 0
	for om in _outlines:
		om.visible = outline_on
