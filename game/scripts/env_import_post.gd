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
	_merge_static_surfaces(scene)
	_apply_cel_materials(scene)
	return scene


## Geometry-preserving batching of legacy fragmented static facilities. Keep
## authored LODs and emissive/foliage semantics separate; never batch characters.
func _merge_static_surfaces(scene: Node) -> void:
	var file := get_source_file().get_file()
	var eligible := false
	for stem in ["env_hut_residential", "env_shelter", "env_terrace", "prp_crate", "prp_amphora", "prp_reservoir", "prp_drying_rack"]:
		if file.begins_with(stem):
			eligible = true
	if not eligible:
		return
	var groups := {}
	var sources: Array[MeshInstance3D] = []
	for child in scene.get_children():
		_gather_batch_surfaces(child, Transform3D.IDENTITY, groups, sources)
	var input_triangles := 0
	var output_triangles := 0
	for key in groups:
		var group: Dictionary = groups[key]
		var builder := SurfaceTool.new()
		builder.begin(Mesh.PRIMITIVE_TRIANGLES)
		builder.set_material(group.material)
		for entry in group.surfaces:
			var arrays: Array = entry.mesh.surface_get_arrays(entry.surface)
			input_triangles += (arrays[Mesh.ARRAY_INDEX].size() if arrays[Mesh.ARRAY_INDEX].size() > 0 else arrays[Mesh.ARRAY_VERTEX].size()) / 3
			builder.append_from(entry.mesh, entry.surface, entry.transform)
		var combined := MeshInstance3D.new()
		combined.name = group.name
		combined.mesh = builder.commit()
		var output_arrays := combined.mesh.surface_get_arrays(0)
		output_triangles += (output_arrays[Mesh.ARRAY_INDEX].size() if output_arrays[Mesh.ARRAY_INDEX].size() > 0 else output_arrays[Mesh.ARRAY_VERTEX].size()) / 3
		combined.cast_shadow = group.shadow
		scene.add_child(combined)
		combined.owner = scene
	for source in sources:
		source.get_parent().remove_child(source)
		source.free()
	scene.set_meta("static_batching", "same_material_same_lod_same_semantic_no_geometry_change")
	scene.set_meta("batch_input_triangles", input_triangles)
	scene.set_meta("batch_output_triangles", output_triangles)
	assert(input_triangles == output_triangles, "Static batching must not lose or add triangles")

func _gather_batch_surfaces(node: Node, parent_transform: Transform3D, groups: Dictionary, sources: Array[MeshInstance3D]) -> void:
	var transform := parent_transform
	if node is Node3D:
		transform *= node.transform
	if node is MeshInstance3D and node.mesh != null:
		var name_lower := String(node.name).to_lower()
		var lod := 0
		for i in range(3):
			if "lod%d__" % i in name_lower:
				lod = i
		var semantic := "surface"
		for word in ["window", "bulb", "glyph", "canopy", "trunk", "valley_floor", "valley_foothill"]:
			if word in name_lower:
				semantic = word
		for surface in range(node.mesh.get_surface_count()):
			var material: Material = node.get_active_material(surface)
			var identity := material.get_instance_id() if material != null else 0
			var key := "%d_%d_%s_%d" % [lod, identity, semantic, node.mesh.surface_get_format(surface)]
			if not groups.has(key):
				var mat_name := material.resource_name if material != null else "default"
				groups[key] = {"material": material, "surfaces": [], "name": "lod%d__batch_%s_%s" % [lod, mat_name, semantic], "shadow": node.cast_shadow}
			groups[key].surfaces.append({"mesh": node.mesh, "surface": surface, "transform": transform})
		sources.append(node)
	for child in node.get_children():
		_gather_batch_surfaces(child, transform, groups, sources)


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
	return preload("res://scripts/env_material_factory.gd").from_material(src)

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
