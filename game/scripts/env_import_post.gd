@tool
extends EditorScenePostImport
## Post-import hook for environment GLBs (art-bible §8.7 import checklist + asset contract).
##
## Wired per-asset via the .import file's `import_script/path` (mirrors how
## character_fbx_import_post.gd is wired for the player FBX). For every env GLB it:
##   - strips any DCC light/camera that slipped into the export
##   - writes the asset contract meta (forward_axis=-Z, metre units)
##   - casts shadows only for hero assets (env_market_stall); props are cel-only
##     (art-bible §3.1.B: 远景可关闭, §8.2 hero vs 陪衬)

const HERO_STEMS := ["env_market_stall", "env_hut_residential", "env_shelter", "env_terrace", "prp_heater", "prp_reservoir", "prp_beacon"]
const CEL_BASE := "res://shaders/cel_base.gdshader"


func _post_import(scene: Node) -> Object:
	_strip_dcc(scene)
	scene.set_meta("forward_axis", "-Z")
	scene.set_meta("units", "metres")
	scene.set_meta("source", "hand_modeled_blender_5.2")
	var is_hero := _is_hero(scene.name)
	_set_cast_shadow(scene, is_hero)
	_apply_cel_materials(scene)
	return scene


## Swap every surface material for a cel_base ShaderMaterial, carrying the baked
## 2K atlas into albedo_tex and preserving the slot identity in resource_name
## (art-bible §3.1.B cel shading; Gate E asserts a cel_base material exists).
func _apply_cel_materials(node: Node) -> void:
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		var mesh := mi.mesh
		for s in range(mesh.get_surface_count()):
			var src := mesh.surface_get_material(s)
			var cel := _cel_from(src)
			if cel != null:
				mesh.surface_set_material(s, cel)
	for child in node.get_children():
		_apply_cel_materials(child)


func _cel_from(src: Material) -> ShaderMaterial:
	if src == null:
		return null
	var shader := load(CEL_BASE) as Shader
	if shader == null:
		push_warning("env_import_post: cel_base shader missing")
		return null
	var sm := ShaderMaterial.new()
	sm.shader = shader
	sm.resource_name = src.resource_name if src.resource_name != "" else "mat_env_default"
	sm.set_shader_parameter("base_color", Color(1, 1, 1))
	if src is StandardMaterial3D:
		var std := src as StandardMaterial3D
		sm.set_shader_parameter("base_color", Color(1, 1, 1))
		if std.albedo_texture != null:
			sm.set_shader_parameter("albedo_tex", std.albedo_texture)
		if std.normal_texture != null:
			sm.set_shader_parameter("normal_tex", std.normal_texture)
		if std.roughness_texture != null:
			sm.set_shader_parameter("orm_tex", std.roughness_texture)
	elif src is ShaderMaterial:
		var src_sm := src as ShaderMaterial
		for pname in ["albedo_tex", "normal_tex", "orm_tex"]:
			var tex = src_sm.get_shader_parameter(pname)
			if tex != null:
				sm.set_shader_parameter(pname, tex)
	return sm


func _is_hero(root_name: String) -> bool:
	var lower := root_name.to_lower()
	for stem in HERO_STEMS:
		if stem in lower:
			return true
	return false


func _strip_dcc(node: Node) -> void:
	var dcc := []
	for child in node.get_children():
		if child is Light3D or child is Camera3D:
			dcc.append(child)
		else:
			_strip_dcc(child)
	for child in dcc:
		node.remove_child(child)
		child.free()


func _set_cast_shadow(node: Node, on: bool) -> void:
	if node is MeshInstance3D:
		(node as MeshInstance3D).cast_shadow = (
			GeometryInstance3D.SHADOW_CASTING_SETTING_ON if on
			else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF)
	for child in node.get_children():
		_set_cast_shadow(child, on)
