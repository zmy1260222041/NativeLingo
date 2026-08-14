extends SceneTree
## Runtime contract for the current static Mira visual.  Rigging and animation
## are intentionally outside this gate; this verifies the baked PBR asset and
## the exact CharacterVisual integration path used by Main.

const MIRA_PATH := "res://assets/characters/chr_npc_mira.glb"
const SOURCE_HEIGHT_M := 1.117689013
const RUNTIME_HEIGHT_M := 1.72

var failures: Array[String] = []
var visual: CharacterVisual
var frames_waited := 0


func _init() -> void:
	var packed := load(MIRA_PATH) as PackedScene
	_check(packed != null, "Mira GLB imports as PackedScene")
	visual = CharacterVisual.new()
	root.add_child(visual)
	visual.configure(Color("f2a85b"), Color("d8665b"), 0, false)
	_check(
		visual.use_authored_static_model(MIRA_PATH, SOURCE_HEIGHT_M, RUNTIME_HEIGHT_M, -1.0),
		"CharacterVisual accepts the authored Mira model",
	)


func _process(_delta: float) -> bool:
	if frames_waited < 4:
		frames_waited += 1
		return false
	_do_checks()
	return true


func _do_checks() -> void:
	var authored := visual.get_node_or_null("AuthoredStaticModel") as Node3D
	_check(authored != null, "authored Mira node is present")
	_check(visual.procedural_root != null and not visual.procedural_root.visible, "procedural Mira fallback is hidden")
	if authored == null:
		_finish()
		return
	var expected_scale := RUNTIME_HEIGHT_M / SOURCE_HEIGHT_M
	_check(authored.scale.is_equal_approx(Vector3.ONE * expected_scale), "uniform scale resolves Mira to 1.72 m")
	_check(is_equal_approx(visual.authored_static_base_position.y, -1.0), "Mira base transform is grounded under the NPC interaction root")
	_check(authored.position.y >= -1.0001 and authored.position.y <= -0.97, "Mira static breathing never drives its feet below the ground plane")
	_check(is_equal_approx(authored.rotation_degrees.y, 180.0), "Mira authored forward matches CharacterVisual -Z")

	var mesh_instance := _find_mesh(authored)
	_check(mesh_instance != null and mesh_instance.mesh != null, "authored Mira contains a mesh")
	if mesh_instance != null and mesh_instance.mesh != null:
		var arrays := mesh_instance.mesh.surface_get_arrays(0)
		_check(not arrays[Mesh.ARRAY_TEX_UV].is_empty(), "Mira mesh carries UV0")
		_check(not arrays[Mesh.ARRAY_NORMAL].is_empty(), "Mira mesh carries normals")
		_check(not arrays[Mesh.ARRAY_TANGENT].is_empty(), "Mira mesh carries tangents")
		var material := mesh_instance.mesh.surface_get_material(0) as StandardMaterial3D
		_check(material != null, "Mira imports a StandardMaterial3D")
		if material != null:
			_check(material.resource_name == "mat_chr_npc_mira_pbr", "Mira material keeps its runtime name")
			_check(material.albedo_texture != null, "Mira material carries Base Color")
			_check(material.normal_texture != null and material.normal_enabled, "Mira material carries tangent-space Normal")
			_check(material.ao_texture != null and material.ao_enabled, "Mira material carries AO")

	visual.play_reaction("greet")
	_check(visual.gesture_clock >= 0.0, "static Mira keeps interaction reaction feedback")
	_finish()


func _find_mesh(node: Node) -> MeshInstance3D:
	if node is MeshInstance3D:
		return node as MeshInstance3D
	for child in node.get_children():
		var found := _find_mesh(child)
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
		print("MIRA_ASSET_TEST_PASS")
		quit(0)
	else:
		print("MIRA_ASSET_TEST_FAIL: ", failures)
		quit(1)
