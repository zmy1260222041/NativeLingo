extends SceneTree
## Gate E contract for the environment art-test assets (art-bible §8.2/§8.6/§8.7,
## §9.5 frame #1). Mirrors test_character_asset.gd's SceneTree/check/finish shape.
##
## Per asset: GLB loads + Node3D + MeshInstance3D; origin at base; -Z forward
## (import-post meta); env_/prp_/fol_ prefix; material slots <= §8.2 cap with
## non-empty resource_name; per-LOD tris <= cap; hero has three LOD groups.
## Scene-wide: at least one cel_base.gdshader material; frame LOD0 tris <= 200k;
## draw calls <= 60 (hero outline pass included). Fails -> quit(1).

const ENV_DIR := "res://assets/environment/"
const CEL_BASE := "res://shaders/cel_base.gdshader"
const MARKET_SCENE := "res://scenes/MarketCorner.tscn"

const ASSETS := [
	"env_market_stall_a",
	"prp_lantern_market_a",
	"env_ground_market_a",
	"env_shelter_distant_a",
	"env_rock_market_a",
	"env_rock_market_b",
	"fol_glowplant_a",
	"prp_food_token_a",
	"prp_food_token_b",
	"prp_food_token_c",
]

# §8.2 LOD0 tri caps + material-slot caps per asset category (by name stem)
const CATEGORY_OF := {
	"env_market_stall": "hero", "prp_lantern": "prop", "env_ground": "ground",
	"env_shelter": "shelter", "env_rock": "rock", "fol_": "veg", "prp_food": "token",
}
const TRI_CAP := {"hero": 16000, "prop": 6000, "ground": 3000, "shelter": 6000,
	"rock": 4000, "veg": 1200, "token": 1800}
const SLOT_CAP := {"hero": 3, "prop": 2, "ground": 1, "shelter": 3,
	"rock": 1, "veg": 1, "token": 1}

const MAX_FRAME_LOD0_TRIS := 200000
const MAX_DRAW_CALLS := 60

var failures: Array[String] = []
var _instances: Array[Node3D] = []
var _market: Node3D
var _frames := 0


func _init() -> void:
	for name in ASSETS:
		var packed := load(ENV_DIR + name + ".glb") as PackedScene
		if packed == null:
			failures.append("%s: GLB fails to load as PackedScene" % name)
			continue
		var inst := packed.instantiate() as Node3D
		if inst == null:
			failures.append("%s: instantiate returns non-Node3D" % name)
			continue
		inst.name = name
		root.add_child(inst)
		_instances.append(inst)
	_check(_instances.size() == ASSETS.size(), "every env GLB loads as a PackedScene (10/10)")
	for inst in _instances:
		_check(_find_first_mesh(inst) != null, "%s contains a MeshInstance3D" % inst.name)

	var market := load(MARKET_SCENE) as PackedScene
	_check(market != null, "MarketCorner.tscn loads as a PackedScene")
	if market != null:
		_market = market.instantiate() as Node3D
		root.add_child(_market)


func _process(_delta: float) -> bool:
	if _frames < 6:
		_frames += 1
		return false
	_do_checks()
	return true


func _do_checks() -> void:
	var total_lod0_tris := 0
	var draw_calls := 0
	var has_cel := [false]
	for inst in _instances:
		var cat := _category(inst.name)
		_check(inst.get_meta("forward_axis", "") == "-Z", "%s import-post meta forward_axis == -Z" % inst.name)
		var aabb := _world_aabb(inst)
		var min_y := aabb.position.y if aabb.size != Vector3.ZERO else -999.0
		var is_ground := inst.name.begins_with("env_ground")
		# ground sits with its TOP at y=0 (thickness below); others rest on the base
		var origin_ok := (aabb.end.y - 0.05 <= 0.05) if is_ground else (absf(min_y) < 0.05)
		_check(origin_ok, "%s origin at base (top_y≈0 ground / min_y≈0 others)" % inst.name)
		_check(_has_valid_prefix(inst.name), "%s uses a valid env_/prp_/fol_ prefix" % inst.name)

		var mesh_names: Array[String] = []
		var material_names: Dictionary = {}
		var lod_tris := [0, 0, 0]
		var unnamed := [false]
		_collect(inst, mesh_names, material_names, lod_tris, unnamed, has_cel)
		if inst.name.begins_with("env_market_stall"):
			var lods_ok := true
			for lod in range(3):
				if not mesh_names.any(func(n): return ("lod%d__" % lod) in n):
					lods_ok = false
			_check(lods_ok, "hero env_market_stall_a has lod0__/lod1__/lod2__ groups")
		var slot_cap: int = SLOT_CAP[cat]
		_check(material_names.size() >= 1 and material_names.size() <= slot_cap, "%s material slots 1..%d (got %d)" % [inst.name, slot_cap, material_names.size()])
		_check(not unnamed[0], "%s every material has a non-empty resource_name" % inst.name)
		var tri_cap: int = TRI_CAP[cat]
		for lod in range(3):
			_check(lod_tris[lod] <= tri_cap, "%s LOD%d tris %d <= §8.2 cap %d" % [inst.name, lod, lod_tris[lod], tri_cap])
		# frame budget contribution: LOD0 tris + LOD0 draw calls (visible when near)
		total_lod0_tris += lod_tris[0]
		draw_calls += _visible_mesh_count(inst, 0)

	# MarketCorner scene-wide frame budget (hero outline pass included)
	var market_draw_calls := draw_calls + _market_outline_count()
	_check(total_lod0_tris <= MAX_FRAME_LOD0_TRIS, "frame LOD0 tris %d <= %d" % [total_lod0_tris, MAX_FRAME_LOD0_TRIS])
	_check(market_draw_calls <= MAX_DRAW_CALLS, "frame draw calls %d <= %d" % [market_draw_calls, MAX_DRAW_CALLS])
	_check(has_cel[0], "at least one material uses cel_base.gdshader")

	print("MARKET_CORNER_ASSET_EVIDENCE lod0_tris=%d draw_calls=%d cel=%s assets=%d" % [
		total_lod0_tris, market_draw_calls, has_cel[0], _instances.size()])
	_finish()


func _category(asset_name: String) -> String:
	var lower := asset_name.to_lower()
	for stem in CATEGORY_OF:
		if lower.begins_with(stem):
			return CATEGORY_OF[stem]
	return "hero"


func _has_valid_prefix(asset_name: String) -> bool:
	var lower := asset_name.to_lower()
	return lower.begins_with("env_") or lower.begins_with("prp_") or lower.begins_with("fol_")


func _collect(node: Node, mesh_names: Array, material_names: Dictionary, lod_tris: Array, unnamed: Array, cel_found: Array) -> void:
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		mesh_names.append(mi.name)
		var lower := String(mi.name).to_lower()
		var lod_index := -1
		for lod in range(3):
			if "lod%d__" % lod in lower:
				lod_index = lod
		if mi.mesh != null:
			for s in range(mi.mesh.get_surface_count()):
				var mat := mi.mesh.surface_get_material(s)
				if mat == null:
					continue
				if mat.resource_name == "":
					unnamed[0] = true
				else:
					material_names[mat.resource_name] = true
				if mat is ShaderMaterial:
					var sm := mat as ShaderMaterial
					if sm.shader != null and sm.shader.resource_path == CEL_BASE:
						cel_found[0] = true
			if lod_index >= 0:
				lod_tris[lod_index] += _tris(mi.mesh)
	for child in node.get_children():
		_collect(child, mesh_names, material_names, lod_tris, unnamed, cel_found)


func _tris(mesh: ArrayMesh) -> int:
	var total := 0
	for s in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(s)
		var indices := arrays[Mesh.ARRAY_INDEX] as PackedInt32Array
		if indices.is_empty():
			total += (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() / 3
		else:
			total += indices.size() / 3
	return total


func _visible_mesh_count(node: Node, lod: int) -> int:
	var count := 0
	if node is MeshInstance3D:
		var lower := String(node.name).to_lower()
		if ("lod%d__" % lod) in lower and node.visible:
			count += 1
	for child in node.get_children():
		count += _visible_mesh_count(child, lod)
	return count


func _market_outline_count() -> int:
	# hero outline meshes are built by EnvLod at runtime; count any *_outline nodes
	if _market == null:
		return 0
	return _count_outlines(_market)


func _count_outlines(node: Node) -> int:
	var count := 0
	if node is MeshInstance3D and String(node.name).ends_with("_outline"):
		count += 1
	for child in node.get_children():
		count += _count_outlines(child)
	return count


func _world_aabb(root: Node3D) -> AABB:
	var merged := AABB()
	for mi in _collect_meshes(root):
		var local: AABB = (mi as MeshInstance3D).get_aabb()
		if local.size == Vector3.ZERO:
			continue
		var world: AABB = (mi as MeshInstance3D).global_transform * local
		if merged.size == Vector3.ZERO:
			merged = world
		else:
			merged = merged.merge(world)
	return merged


func _collect_meshes(node: Node) -> Array:
	var out := []
	_walk_meshes(node, out)
	return out


func _walk_meshes(node: Node, out: Array) -> void:
	if node is MeshInstance3D:
		out.append(node)
	for child in node.get_children():
		_walk_meshes(child, out)


func _find_first_mesh(node: Node) -> MeshInstance3D:
	if node is MeshInstance3D:
		return node as MeshInstance3D
	for child in node.get_children():
		var found := _find_first_mesh(child)
		if found != null:
			return found
	return null


func _check(condition: bool, label: String) -> void:
	if condition:
		print("PASS: ", label)
	else:
		failures.append(label)
		push_error("FAIL: " + label)


func _finish() -> void:
	if failures.is_empty():
		print("MARKET_CORNER_ASSET_TEST_PASS")
		quit(0)
	else:
		print("MARKET_CORNER_ASSET_TEST_FAIL: ", failures)
		quit(1)
