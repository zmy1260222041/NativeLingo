class_name EnvLod
extends Node3D
## One active authored LOD; outlines are children of their source surface.
const LOD_DIST_HERO := [48.0, 80.0]
const LOD_DIST_PROP := [24.0, 45.0]
const OUTLINE_SHADER := preload("res://shaders/cel_outline.gdshader")
var _lod_groups: Array = [[], [], []]
var _current_lod := -1
var _hero := false
var _outline_limit := 0

func configure(hero: bool) -> void:
	_hero = hero
	_outline_limit = 2 if hero else 0

func _ready() -> void:
	_collect(get_parent())
	_build_outlines(_outline_limit)
	_set_lod(0)

func _process(_delta: float) -> void:
	var cam := get_viewport().get_camera_3d()
	if cam != null:
		set_distance(global_position.distance_to(cam.global_position))
		# Disappear softly from the distant read without duplicating LOD geometry.
		for mi in _lod_groups[0]:
			var outline: Node3D = mi.get_node_or_null("SurfaceOutline")
			if outline != null:
				outline.visible = global_position.distance_to(cam.global_position) < 16.0

func set_distance(distance: float) -> void:
	var limits := LOD_DIST_HERO if _hero else LOD_DIST_PROP
	_set_lod(0 if distance < limits[0] else (1 if distance < limits[1] else 2))

func _collect(node: Node) -> void:
	if node == self or node.name == "SurfaceOutline" or String(node.name).ends_with("_outline"):
		return
	if node is MeshInstance3D:
		var level := 0
		for i in range(3):
			if "lod%d__" % i in String(node.name).to_lower():
				level = i
		_lod_groups[level].append(node)
	for child in node.get_children():
		_collect(child)

func request_outlines(limit: int) -> void:
	if not is_node_ready():
		_outline_limit = maxi(_outline_limit, limit)
		return
	_build_outlines(limit)

func _build_outlines(limit: int) -> void:
	var candidates: Array = _lod_groups[0].duplicate()
	candidates.sort_custom(func(a, b): return _mesh_tris(a) > _mesh_tris(b))
	var count := 0
	for mi: MeshInstance3D in candidates:
		var key := String(mi.name).to_lower()
		if "canopy" in key or "trunk" in key or "ground" in key or "contact" in key or "env_market_stall" in key:
			continue
		if count >= limit:
			break
		count += 1
		if mi.get_node_or_null("SurfaceOutline") != null:
			continue
		var outline := MeshInstance3D.new()
		outline.name = "SurfaceOutline"
		outline.mesh = mi.mesh
		outline.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var material := ShaderMaterial.new()
		material.shader = OUTLINE_SHADER
		material.set_shader_parameter("outline_width", 0.004)
		material.set_shader_parameter("outline_color", Color("354454"))
		outline.material_override = material
		mi.add_child(outline)

func _mesh_tris(mi: MeshInstance3D) -> int:
	var count := 0
	if mi.mesh != null:
		for i in range(mi.mesh.get_surface_count()):
			var arrays := mi.mesh.surface_get_arrays(i)
			count += (arrays[Mesh.ARRAY_INDEX].size() if arrays[Mesh.ARRAY_INDEX].size() else arrays[Mesh.ARRAY_VERTEX].size()) / 3
	return count

func _set_lod(requested: int) -> void:
	var selected := clampi(requested, 0, 2)
	while selected > 0 and _lod_groups[selected].is_empty():
		selected -= 1
	if _lod_groups[selected].is_empty():
		for i in range(3):
			if not _lod_groups[i].is_empty():
				selected = i
				break
	if selected == _current_lod:
		return
	_current_lod = selected
	for level in range(3):
		for mi: MeshInstance3D in _lod_groups[level]:
			mi.visible = level == selected
