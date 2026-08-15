extends Node
## P0: playable Main.tscn must load MarketCorner env assets without moving
## interactable positions. Run as a scene so autoloads exist.

const EXPECTED_TARGETS := {
	"mira": Vector3(-1.7, 1.0, -0.55),
	"rowan": Vector3(3, 1.0, 0.5),
	"berry_a": Vector3(-10, 0.65, -2),
	"heater": Vector3(-3.2, 0.7, 6.0),
	"shelter": Vector3(-7, 0.8, 8.5),
}

var failures: Array[String] = []
@onready var _main: Node3D = $Main


func _ready() -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	_do_checks()
	_finish()


func _do_checks() -> void:
	_check(_find_named(_main, "env_market_stall_a") != null, "market stall asset exists")
	_check(_find_named(_main, "MarketCanopy") == null, "primitive market canopy fallback is gone")
	_check(_find_named(_main, "env_ground_market_a") != null, "authored ground exists")
	_check(_find_named(_main, "env_hut_residential_a") != null, "shell-plate residence A exists")
	_check(_find_named(_main, "env_hut_residential_b") != null, "shell-plate residence B exists")
	_check(_find_named(_main, "env_hut_residential_c") != null, "pod-crystal residence C exists")
	_check(_find_exact(_main, "Hut") == null, "primitive hut fallback is gone")
	_check(_find_named(_main, "env_shelter_distant_a") != null, "shelter asset exists")
	_check(_find_named(_main, "fol_tree_stranger_a") != null, "stylized tree exists")
	_check(_find_named(_main, "env_rock_facet") != null, "faceted rock exists")
	_check(_find_named(_main, "AuthoredGlowPlants") != null, "glow plants exist")
	_check(_find_named(_main, "GlowStem") == null, "primitive glow-plant ring is gone")
	_check(_find_named(_main, "env_terrace_market_a") != null, "market terrace exists")
	_check(_find_named(_main, "env_plaza_market_a") != null, "plaza asset exists")
	_check(_find_exact(_main, "MeetingPlaza") == null, "primitive plaza is gone")
	_check(_find_named(_main, "prp_heater_old") != null or _find_named(_main, "heater") != null, "heater station exists")
	_check(_find_exact(_main, "BeaconBase") == null, "primitive beacon is gone")
	_check(_has_cel_material(_main), "at least one cel_base material is in the playable scene")
	_check(_has_fitted_collision(_find_named(_main, "env_hut_residential_a")), "hut A has fitted collision")
	_check(_has_fitted_collision(_find_named(_main, "env_hut_residential_b")), "hut B has fitted collision")
	_check(_has_fitted_collision(_find_named(_main, "env_hut_residential_c")), "hut C has fitted collision")
	_check(_has_fitted_collision(_find_named(_main, "env_market_stall_a")), "stall has fitted collision")
	_check(_has_fitted_collision(_find_named(_main, "env_shelter_distant_a")), "shelter has fitted collision")
	_check(_has_fitted_collision(_find_named(_main, "env_terrace_market_a")), "terrace has fitted collision")
	_check(_has_fitted_collision(_find_named(_main, "env_ridge_distant_a")), "ridge has fitted collision")
	_check(_has_fitted_collision(_find_named(_main, "fol_tree_stranger_a")), "tree trunk has fitted collision")
	var world_env := _find_world_environment(_main)
	_check(world_env != null and world_env.environment != null, "playable scene has a WorldEnvironment")
	if world_env != null and world_env.environment != null:
		var env := world_env.environment
		_check(env.glow_enabled, "Glow is on for furnace/fluorescence (art-bible §3.4)")
		_check(env.glow_bloom <= 0.001, "Glow bloom stays off so the screen does not wash out")
		_check(env.fog_enabled, "height fog is enabled")
		_check(env.fog_light_color.b >= env.fog_light_color.r + 0.02, "fog is cool, not warm dust D7B08A")
		_check(env.fog_height_density < 0.0, "height fog density is negative so peaks recede")
	var sun := _find_sun(_main)
	_check(sun != null and sun.shadow_enabled and sun.directional_shadow_max_distance <= 35.5, "key light shadows at high-tier 35 m")
	_check(_find_named(_main, "HeaterGlow") != null, "heater has a local furnace light")
	_check(_has_contact_ao(_main), "cel_base contact AO is wired on environment meshes")
	var found := {}
	var mira_interactable: WorldInteractable
	for node in _main.get_tree().get_nodes_in_group("interactable"):
		if node is WorldInteractable:
			found[node.target_id] = node.global_position
			if node.target_id == "mira":
				mira_interactable = node as WorldInteractable
	for target_id in EXPECTED_TARGETS.keys():
		_check(found.has(target_id), "interactable %s is present" % target_id)
		if found.has(target_id):
			var delta: float = found[target_id].distance_to(EXPECTED_TARGETS[target_id])
			_check(delta < 0.05, "interactable %s stayed at authored position (delta=%.3f)" % [target_id, delta])
	_check(mira_interactable != null and _find_named(mira_interactable, "AuthoredStaticModel") != null, "playable Mira uses the baked authored GLB")
	if mira_interactable != null:
		var mira_visual := mira_interactable.get_node_or_null("CharacterVisual") as CharacterVisual
		_check(mira_visual != null and mira_visual.procedural_root != null and not mira_visual.procedural_root.visible, "playable Mira hides the procedural visual fallback")


func _find_named(root_node: Node, stem: String) -> Node:
	if stem.to_lower() in String(root_node.name).to_lower():
		return root_node
	for child in root_node.get_children():
		var found := _find_named(child, stem)
		if found != null:
			return found
	return null


func _find_exact(root_node: Node, node_name: String) -> Node:
	if String(root_node.name) == node_name:
		return root_node
	for child in root_node.get_children():
		var found := _find_exact(child, node_name)
		if found != null:
			return found
	return null


func _find_world_environment(node: Node) -> WorldEnvironment:
	if node is WorldEnvironment:
		return node as WorldEnvironment
	for child in node.get_children():
		var found := _find_world_environment(child)
		if found != null:
			return found
	return null


func _find_sun(node: Node) -> DirectionalLight3D:
	if node is DirectionalLight3D:
		return node as DirectionalLight3D
	for child in node.get_children():
		var found := _find_sun(child)
		if found != null:
			return found
	return null


func _has_contact_ao(node: Node) -> bool:
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		if _material_has_contact(mi.material_override):
			return true
		if mi.mesh != null:
			for s in range(mi.mesh.get_surface_count()):
				if _material_has_contact(mi.mesh.surface_get_material(s)):
					return true
	for child in node.get_children():
		if _has_contact_ao(child):
			return true
	return false


func _material_has_contact(mat: Material) -> bool:
	if mat is ShaderMaterial:
		var sm := mat as ShaderMaterial
		if sm.shader == null or not String(sm.shader.resource_path).ends_with("cel_base.gdshader"):
			return false
		return sm.get_shader_parameter("contact_enabled") == true
	return false


func _has_fitted_collision(node: Node) -> bool:
	if node == null:
		return false
	if node is CollisionShape3D:
		var cs := node as CollisionShape3D
		return not cs.disabled and cs.shape != null
	for child in node.get_children():
		if _has_fitted_collision(child):
			return true
	return false


func _has_cel_material(node: Node) -> bool:
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		if _material_is_cel(mi.material_override):
			return true
		if mi.mesh != null:
			for s in range(mi.mesh.get_surface_count()):
				if _material_is_cel(mi.mesh.surface_get_material(s)):
					return true
	for child in node.get_children():
		if _has_cel_material(child):
			return true
	return false


func _material_is_cel(mat: Material) -> bool:
	if mat is ShaderMaterial:
		var shader := (mat as ShaderMaterial).shader
		if shader != null and String(shader.resource_path).ends_with("cel_base.gdshader"):
			return true
	return false


func _check(ok: bool, label: String) -> void:
	if not ok:
		failures.append(label)


func _finish() -> void:
	if failures.is_empty():
		print("MAIN_ENV_INTEGRATION_PASS")
		get_tree().quit(0)
	else:
		print("MAIN_ENV_INTEGRATION_FAIL")
		for item in failures:
			print("  - ", item)
		get_tree().quit(1)
