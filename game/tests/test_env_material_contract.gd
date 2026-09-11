extends SceneTree
## Soft-surface import contract and one-active-authored-LOD regression.
const Factory := preload("res://scripts/env_material_factory.gd")
const Lod := preload("res://scripts/env_lod.gd")
var failures: Array[String] = []

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var source := StandardMaterial3D.new()
	source.resource_name = "mat_alloy_test"
	source.albedo_color = Color(0.27, 0.43, 0.61)
	source.roughness = 0.63
	source.metallic = 0.38
	var converted := Factory.from_material(source)
	_check(converted.get_shader_parameter("base_color").is_equal_approx(source.albedo_color), "import preserves base color")
	_check(is_equal_approx(converted.get_shader_parameter("rough"), 0.63), "import preserves roughness")
	_check(is_equal_approx(converted.get_shader_parameter("metal"), 0.38), "import preserves metallic")
	source.roughness_texture = Factory.solid_texture(Color(1.0, 0.7, 0.5))
	converted = Factory.from_material(source)
	_check(is_equal_approx(converted.get_shader_parameter("orm_rough_factor"), 0.63), "packed roughness retains glTF scalar multiplier")
	_check(is_equal_approx(converted.get_shader_parameter("orm_metal_factor"), 0.38), "packed metallic retains glTF scalar multiplier")
	var default_mat := Factory.from_material(null)
	var normal: Texture2D = default_mat.get_shader_parameter("normal_tex")
	var orm: Texture2D = default_mat.get_shader_parameter("orm_tex")
	var normal_pixel := normal.get_image().get_pixel(0, 0)
	_check(absf(normal_pixel.r - 0.5) <= 1.0/255 and absf(normal_pixel.g - 0.5) <= 1.0/255 and normal_pixel.b == 1.0, "missing normal is flat +Z (8-bit quantization)")
	_check(orm.get_image().get_pixel(0, 0).is_equal_approx(Color(1,1,0)), "neutral ORM is AO=1 rough=1 metal=0")
	for stem in ["env_market_stall_a", "fol_tree_stranger_a", "prp_crate_stack_a", "prp_amphora_cluster_a", "prp_heater_old"]:
		var host := (load("res://assets/environment/%s.glb" % stem) as PackedScene).instantiate()
		root.add_child(host)
		var lod := Lod.new()
		lod.configure(true)
		host.add_child(lod)
		await process_frame
		lod.request_outlines(2)
		lod.request_outlines(2)
		for distance in [0.0, 60.0, 120.0]:
			lod.set_distance(distance)
			var visible_levels := {}
			for i in range(3):
				for mi: MeshInstance3D in lod._lod_groups[i]:
					if mi.visible:
						visible_levels[i] = true
					var count := 0
					for child in mi.get_children():
						if "SurfaceOutline" in String(child.name):
							count += 1
							if i != lod._current_lod:
								_check(not child.is_visible_in_tree(), stem + " outline follows source LOD")
					_check(count <= 1, stem + " no duplicated outline")
			_check(visible_levels.size() == 1, "%s one active LOD at %.0fm" % [stem,distance])
		host.free()
	for stem in ["env_market_stall_a", "env_ground_market_a", "fol_tree_stranger_a", "prp_market_burger_v01", "prp_market_wrap_v01", "prp_market_drink_v01"]:
		var host := (load("res://assets/environment/%s.glb" % stem) as PackedScene).instantiate()
		_check_baked(host, stem)
		host.free()
	for stem in ["env_hut_residential_a", "env_hut_residential_b", "env_hut_residential_c", "prp_crate_stack_a", "prp_amphora_cluster_a"]:
		var host := (load("res://assets/environment/%s.glb" % stem) as PackedScene).instantiate()
		_check(host.get_meta("batch_input_triangles", 0) > 0, stem + " static batching is recorded")
		_check(host.get_meta("batch_input_triangles", -1) == host.get_meta("batch_output_triangles", -2), stem + " batching preserves triangle count")
		host.free()
	if failures.is_empty():
		print("ENV_MATERIAL_LOD_CONTRACT_PASS")
	else:
		for failure in failures:
			push_error(failure)
	quit(0 if failures.is_empty() else 1)

func _check_baked(node: Node, stem: String) -> void:
	if node is MeshInstance3D:
		for s in range(node.mesh.get_surface_count()):
			var mat: ShaderMaterial = node.mesh.surface_get_material(s) as ShaderMaterial
			_check(mat != null, stem + " imported through material factory")
			if mat != null:
				_check(mat.get_shader_parameter("orm_strength") == 1.0, stem + " packed ORM enabled")
				for channel in ["albedo_tex", "normal_tex", "orm_tex"]:
					var tex: Texture2D = mat.get_shader_parameter(channel)
					_check(tex != null and tex.get_width() >= 512, stem + " baked " + channel)
	for child in node.get_children():
		_check_baked(child, stem)

func _check(ok: bool, label: String) -> void:
	if not ok:
		failures.append(label)
