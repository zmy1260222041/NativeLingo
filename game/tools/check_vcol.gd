extends SceneTree
func _init() -> void:
	for f in ["env_hut_residential_a", "env_ground_market_a", "env_rock_market_a", "prp_lantern_market_a"]:
		var path := "res://assets/environment/%s.glb" % f
		var packed := load(path) as PackedScene
		if packed == null:
			print("VCOL ", f, " LOAD_FAIL")
			continue
		var inst := packed.instantiate()
		var report := []
		_walk(inst, report)
		print("VCOL ", f, " ", " | ".join(report.slice(0, 6)))
	quit(0)
func _walk(node: Node, out: Array) -> void:
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		var mesh := mi.mesh as Mesh
		if mesh != null and mesh.get_surface_count() > 0:
			var arrays := mesh.surface_get_arrays(0)
			var colors: PackedColorArray = arrays[Mesh.ARRAY_COLOR] if arrays[Mesh.ARRAY_COLOR] != null else PackedColorArray()
			var fmt: int = mesh.surface_get_format(0)
			var has_color := (fmt & Mesh.ARRAY_FORMAT_COLOR) != 0
			var sample: String
			if colors.size() > 0:
				var c: Color = colors[0]
				sample = "(%.2f,%.2f,%.2f,%.2f)" % [c.r, c.g, c.b, c.a]
			else:
				sample = "none"
			if out.size() < 12:
				out.append("%s[%s n=%d %s]" % [String(mi.name).substr(0, 30), sample, colors.size(), "F" if has_color else "-"])
	for child in node.get_children():
		_walk(child, out)
