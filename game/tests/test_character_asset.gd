extends SceneTree
## Gate D contract for the player character runtime assembly.
## The runtime asset is assembled in code (character_visual.gd): the target rig
## plus idle and the selected Mixamo-retargeted actions come from the player
## FBX; LOD1/2 are added from metre GLBs; a named material is assigned at
## runtime. This test drives the same loader path the game uses.

const CHARACTER_PATH := "res://assets/characters/chr_player_juvenile_mixamo.fbx"
const MAX_DEFORM_BONES := 72
const MAX_MATERIAL_SLOTS := 3
const MIN_LOD0_FACIAL_MORPHS := 3
const EXPECTED_ANIMATIONS := [
	"anim_chr_player_idle_neutral",
	"anim_chr_player_walk_forward",
	"anim_chr_player_run_forward",
	"anim_chr_player_gesture_point",
	"anim_chr_player_interact_observe",
	"anim_chr_player_interact_gather",
	"anim_chr_player_gesture_greet",
	"anim_chr_player_gesture_offer",
	"anim_chr_player_gesture_clarify",
]

var failures: Array[String] = []
var _visual: CharacterVisual

func _init() -> void:
	var packed := load(CHARACTER_PATH) as PackedScene
	_check(packed != null, "character FBX loads as a PackedScene")
	if packed == null:
		_finish()
		return

	# Drive the same runtime assembly the game uses; check after a few frames
	# so the loader's _ready/configure pipeline has run.
	_visual = CharacterVisual.new()
	root.add_child(_visual)
	_visual.configure(Color("bfa982"), Color("5a3f58"), 0, true)

var _frames_waited := 0

func _process(_delta: float) -> bool:
	if _frames_waited < 4:
		_frames_waited += 1
		return false
	_do_checks()
	return true

func _do_checks() -> void:
	var visual := _visual
	var skeleton := _find_first(visual, "Skeleton3D") as Skeleton3D
	_check(skeleton != null, "imported character contains Skeleton3D")
	if skeleton:
		_check(skeleton.get_bone_count() > 0 and skeleton.get_bone_count() <= MAX_DEFORM_BONES, "skeleton deform bones within art-spec budget (1..%d)" % MAX_DEFORM_BONES)

	var animation_player := _find_first(visual, "AnimationPlayer") as AnimationPlayer
	_check(animation_player != null, "imported character contains AnimationPlayer")
	if animation_player:
		var imported_names := Array(animation_player.get_animation_list())
		print("IMPORTED_ANIMATIONS=", imported_names)
		for expected in EXPECTED_ANIMATIONS:
			_check(expected in imported_names, "animation imported: %s" % expected)
		for looping_name in ["anim_chr_player_idle_neutral", "anim_chr_player_walk_forward", "anim_chr_player_run_forward"]:
			var animation := animation_player.get_animation(looping_name)
			_check(animation != null and animation.loop_mode != Animation.LOOP_NONE, "loop suffix configures looping: %s" % looping_name)

	var lod_counts := [0, 0, 0]
	var material_names: Dictionary = {}
	var has_unnamed_material := [false]
	var blend_shapes: Dictionary = {}
	_collect_mesh_evidence(visual, lod_counts, material_names, has_unnamed_material, blend_shapes)
	for lod in range(3):
		_check(lod_counts[lod] >= 1, "LOD%d group present so runtime distance culling has meshes to toggle" % lod)
	_check(material_names.size() >= 1 and material_names.size() <= MAX_MATERIAL_SLOTS, "runtime asset uses 1..%d named materials" % MAX_MATERIAL_SLOTS)
	_check(not has_unnamed_material[0], "every material carries a non-empty resource_name (distinct slot identity)")
	_check(blend_shapes.size() >= MIN_LOD0_FACIAL_MORPHS, "LOD0 carries facial morphs for blink/jaw/viseme animation (>= %d)" % MIN_LOD0_FACIAL_MORPHS)

	print("CHARACTER_ASSET_EVIDENCE bones=%d lods=%s materials=%s morphs=%d" % [
		skeleton.get_bone_count() if skeleton else 0,
		str(lod_counts),
		str(material_names.keys()),
		blend_shapes.size(),
	])
	visual.queue_free()
	_finish()

func _collect_mesh_evidence(node: Node, lod_counts: Array, material_names: Dictionary, has_unnamed_material: Array, blend_shapes: Dictionary) -> void:
	if node is MeshInstance3D:
		var mesh_instance := node as MeshInstance3D
		var lower_name := mesh_instance.name.to_lower()
		var lod_index := -1
		for lod in range(3):
			if "lod%d__" % lod in lower_name:
				lod_counts[lod] += 1
				lod_index = lod
		if mesh_instance.mesh:
			# the runtime assembly assigns a named material via material_override;
			# when present it replaces the (possibly unnamed) surface materials
			var override_mat := mesh_instance.material_override
			if override_mat != null:
				if override_mat.resource_name == "":
					has_unnamed_material[0] = true
				else:
					material_names[override_mat.resource_name] = true
			else:
				for surface in range(mesh_instance.mesh.get_surface_count()):
					var material := mesh_instance.mesh.surface_get_material(surface)
					if material:
						if material.resource_name == "":
							has_unnamed_material[0] = true
						else:
							material_names[material.resource_name] = true
			if lod_index == 0:
				for shape_index in range(mesh_instance.mesh.get_blend_shape_count()):
					blend_shapes[mesh_instance.mesh.get_blend_shape_name(shape_index)] = true
	for child in node.get_children():
		_collect_mesh_evidence(child, lod_counts, material_names, has_unnamed_material, blend_shapes)

func _find_first(node: Node, class_name_value: String) -> Node:
	if node.is_class(class_name_value):
		return node
	for child in node.get_children():
		var found := _find_first(child, class_name_value)
		if found:
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
		print("CHARACTER_ASSET_TEST_PASS")
		quit(0)
	else:
		print("CHARACTER_ASSET_TEST_FAIL: ", failures)
		quit(1)
