class_name CharacterVisual
extends Node3D

const IDLE_BREATH_DURATION := 2.4
const PLAYER_MODEL_PATH := "res://assets/characters/chr_player_juvenile.fbx"
const RUNTIME_IDLE := "anim_chr_player_idle_neutral"
const RUNTIME_WALK := "anim_chr_player_walk_forward"

var torso_pivot: Node3D
var head_pivot: Node3D
var left_arm: Node3D
var right_arm: Node3D
var left_leg: Node3D
var right_leg: Node3D
var left_hand: MeshInstance3D
var right_hand: MeshInstance3D
var primary_sail: Node3D
var secondary_sail: Node3D

var motion_speed := 0.0
var airborne := false
var animation_clock := 0.0
var gesture_clock := -1.0
var gesture_kind := "greet"
var personality_phase := 0.0
var is_player_character := false
var profile := 0
var locomotion_blend := 0.0
var airborne_blend := 0.0
var idle_segment_remaining := 1.0
var idle_is_breathing := false
var procedural_root: Node3D
var runtime_root: Node3D
var runtime_animation_player: AnimationPlayer
var runtime_lod_groups: Array = [[], [], []]
var runtime_lod := -1
var runtime_animation := ""

func configure(base_color: Color, accent_color: Color, style_profile := 0, player_character := false) -> void:
	profile = clampi(style_profile, 0, 4)
	personality_phase = float(profile) * 0.73
	is_player_character = player_character
	idle_segment_remaining = 1.0 + fmod(personality_phase, 1.8)
	_build(base_color, accent_color)

func set_motion(speed: float, is_airborne: bool) -> void:
	motion_speed = speed
	airborne = is_airborne

func play_reaction(kind := "greet") -> void:
	gesture_kind = kind if kind in ["greet", "offer", "clarify"] else "greet"
	gesture_clock = 0.0
	if runtime_animation_player:
		runtime_animation_player.speed_scale = 1.0
		_play_runtime_animation(_runtime_gesture_animation(), 0.12)

func _process(delta: float) -> void:
	if is_player_character and runtime_root == null:
		return
	animation_clock += delta
	locomotion_blend = move_toward(locomotion_blend, clampf(motion_speed / 8.2, 0.0, 1.0), delta * 4.8)
	airborne_blend = move_toward(airborne_blend, 1.0 if airborne else 0.0, delta * 7.0)
	if gesture_clock >= 0.0:
		gesture_clock += delta
		if gesture_clock > _gesture_duration():
			gesture_clock = -1.0
	if runtime_root:
		_update_runtime_lod()
		_update_runtime_animation()
		return
	_update_idle_segment(delta)
	_apply_pose()

func _build(base_color: Color, accent_color: Color) -> void:
	if is_player_character:
		if _try_build_runtime_model():
			return
		push_warning("Approved Rodin player asset is not available; obsolete player fallback is disabled.")
		set_process(false)
		return
	procedural_root = Node3D.new()
	procedural_root.name = "NpcProceduralVisual"
	procedural_root.position.y = 0.0
	add_child(procedural_root)
	torso_pivot = Node3D.new()
	torso_pivot.name = "TorsoPivot"
	procedural_root.add_child(torso_pivot)
	var torso_mesh := CapsuleMesh.new()
	torso_mesh.radius = 0.34
	torso_mesh.height = 1.12
	_add_mesh(torso_pivot, "Torso", torso_mesh, Vector3(0, 0.12, 0), Vector3(0.92, 1.0, 0.82), _material(base_color))

	head_pivot = Node3D.new()
	head_pivot.name = "HeadPivot"
	head_pivot.position = Vector3(0, 0.78, 0)
	procedural_root.add_child(head_pivot)
	var head_mesh := SphereMesh.new()
	head_mesh.radius = 0.3
	head_mesh.height = 0.6
	_add_mesh(head_pivot, "Head", head_mesh, Vector3.ZERO, Vector3(1.14, 0.92, 1.0), _material(base_color.lightened(0.12)))

	var eye_material := _material(Color("17243b"), Color("78c9a4"))
	for side in [-1.0, 1.0]:
		var eye_mesh := SphereMesh.new()
		eye_mesh.radius = 0.065
		eye_mesh.height = 0.13
		_add_mesh(head_pivot, "Eye", eye_mesh, Vector3(side * 0.13, 0.025, -0.285), Vector3(0.78, 1.2, 0.42), eye_material)

	left_arm = _build_limb("LeftArm", Vector3(-0.36, 0.34, 0), base_color.darkened(0.08), 0.66, 0.09)
	right_arm = _build_limb("RightArm", Vector3(0.36, 0.34, 0), base_color.darkened(0.08), 0.66, 0.09)
	left_hand = _build_hand(left_arm, "LeftPalm", Vector3(0, -0.57, 0), base_color.lightened(0.08))
	right_hand = _build_hand(right_arm, "RightPalm", Vector3(0, -0.57, 0), base_color.lightened(0.08))
	left_leg = _build_limb("LeftLeg", Vector3(-0.17, -0.44, 0), accent_color.darkened(0.12), 0.86, 0.1)
	right_leg = _build_limb("RightLeg", Vector3(0.17, -0.44, 0), accent_color.darkened(0.12), 0.86, 0.1)

	_build_npc_contour(accent_color)
	_apply_npc_profile()

func _try_build_runtime_model() -> bool:
	if not ResourceLoader.exists(PLAYER_MODEL_PATH):
		return false
	var packed := load(PLAYER_MODEL_PATH) as PackedScene
	if packed == null:
		return false
	runtime_root = packed.instantiate() as Node3D
	if runtime_root == null:
		return false
	runtime_root.name = "OrganicPlayerModel"
	# The Tencent FBX is Z-up; Godot's importer already rotates the root -90°X
	# so the model stands on +Y. It faces +Z by default; the third-person rig
	# needs -Z (away from camera), so turn 180° around Godot's up axis.
	runtime_root.rotation_degrees.y = 180.0
	add_child(runtime_root)
	# rename the LOD0 mesh BEFORE collecting nodes so it lands in the LOD0 group
	_rename_lod0_mesh()
	_collect_runtime_nodes(runtime_root)
	if runtime_animation_player == null:
		remove_child(runtime_root)
		runtime_root.free()
		runtime_root = null
		return false
	_rename_cloud_animations()
	_add_walk_from_source()
	_add_procedural_gestures()
	_add_lod_meshes()
	_assign_named_material()
	_set_runtime_lod(0)
	_play_runtime_animation(RUNTIME_IDLE, 0.0)
	return true

## The cloud motion FBXs use a different 52-bone skeleton, so retargeting them
## onto the 28-bone rig at runtime is not reliable. Instead create simple
## procedural gestures (arm rotations) on the rig — real, in-game, no broken
## scale. greet = wave, offer = reach forward, clarify = palms open.
func _add_procedural_gestures() -> void:
	var ap := runtime_animation_player as AnimationPlayer
	if ap == null:
		return
	var lib: AnimationLibrary = ap.get_animation_library("")
	if lib == null:
		return
	var skeleton := _find_skeleton(runtime_root) as Skeleton3D
	if skeleton == null:
		return
	# find bone index by name (Mixamo-legacy)
	var bone := func(bname: String) -> int:
		for i in skeleton.get_bone_count():
			if skeleton.get_bone_name(i) == bname:
				return i
		return -1
	var right_arm: int = bone.call("RightArm")
	var right_fore: int = bone.call("RightForeArm")
	var left_arm: int = bone.call("LeftArm")
	var right_leg: int = bone.call("RightUpLeg")
	if right_arm < 0 or right_fore < 0:
		return
	# helper to add a single-bone rotation animation
	var make_gesture := func(anim_name: String, bone_idx: int, peak_deg: float, back_deg: float, frames: int) -> void:
		var anim := Animation.new()
		anim.length = frames / 30.0
		var track := anim.add_track(Animation.TYPE_ROTATION_3D)
		# the FBX import nests the skeleton under the "Armature" root; the
		# AnimationPlayer sits at the scene root, so the full path is required
		anim.track_set_path(track, NodePath("Armature/Skeleton3D:" + skeleton.get_bone_name(bone_idx)))
		# up-down (greet) or forward reach, via X rotation keyframes
		anim.track_insert_key(track, 0.0, Quaternion.from_euler(Vector3(0, 0, 0)))
		anim.track_insert_key(track, frames / 30.0 * 0.3, Quaternion.from_euler(Vector3(deg_to_rad(peak_deg), 0, 0)))
		anim.track_insert_key(track, frames / 30.0 * 0.7, Quaternion.from_euler(Vector3(deg_to_rad(back_deg), 0, 0)))
		anim.track_insert_key(track, anim.length, Quaternion.from_euler(Vector3(0, 0, 0)))
		if not lib.has_animation(anim_name):
			lib.add_animation(anim_name, anim)
	make_gesture.call("anim_chr_player_gesture_greet", right_arm, -60.0, 60.0, 60)
	make_gesture.call("anim_chr_player_gesture_offer", right_arm, 40.0, 20.0, 45)
	make_gesture.call("anim_chr_player_gesture_clarify", left_arm, 35.0, 15.0, 60)

## The Tencent FBX's LOD0 mesh keeps its source name (mesh_rep_0_...); rename it
## to the contract "lod0__" substring so the runtime LOD group finds it.
func _rename_lod0_mesh() -> void:
	var mesh := _find_mesh_instance(runtime_root)
	if mesh != null and not mesh.name.to_lower().contains("lod0__"):
		mesh.name = "lod0__body"

## Load the walk animation from the second cloud FBX (same 28-bone rig) into the
## main AnimationPlayer so walk plays alongside idle.
const WALK_SOURCE_PATH := "res://assets/characters/chr_player_walk_source.fbx"
const WALK_SOURCE_HASH := "32795ddb244644eac67ccfd8b84060c3"

const WalkAnimFix := preload("res://scripts/walk_anim_fix.gd")

func _add_walk_from_source() -> void:
	if not ResourceLoader.exists(WALK_SOURCE_PATH):
		push_warning("walk source FBX missing: ", WALK_SOURCE_PATH)
		return
	var ap := runtime_animation_player as AnimationPlayer
	if ap == null:
		return
	var walk_packed := load(WALK_SOURCE_PATH) as PackedScene
	if walk_packed == null:
		return
	var walk_inst := walk_packed.instantiate()
	add_child(walk_inst)
	var walk_ap := _find_animation_player(walk_inst)
	if walk_ap == null:
		walk_inst.queue_free()
		return
	var lib: AnimationLibrary = ap.get_animation_library("")
	if lib == null:
		walk_inst.queue_free()
		return
	var walk_lib: AnimationLibrary = walk_ap.get_animation_library("")
	for cloud_name in walk_lib.get_animation_list():
		if cloud_name.contains(WALK_SOURCE_HASH):
			var anim := walk_lib.get_animation(cloud_name)
			anim.loop_mode = Animation.LOOP_LINEAR
			# The walk source FBX is a separate cloud generation whose skeleton
			# rest pose differs from this rig's (hips yaw ~166° vs ~35°), so
			# playing its keys here twists the pelvis ~130° and the head ~75°
			# off the idle pose (see tools/debug_cli.gd `selftest`). Re-base
			# the walk cycle neutral onto the idle pose, which is authored on
			# this rig and plays correctly.
			var idle_anim := lib.get_animation(RUNTIME_IDLE) if lib.has_animation(RUNTIME_IDLE) else null
			if idle_anim != null:
				anim = WalkAnimFix.build_fixed_walk(anim, idle_anim, "rebase")
			lib.add_animation(RUNTIME_WALK, anim)
			break
	walk_inst.queue_free()

## Attach the cloud LOD1/LOD2 meshes (metre GLBs) under the same armature so the
## runtime LOD group toggles them by distance like LOD0.
const LOD1_PATH := "res://assets/characters/chr_player_lod1.glb"
const LOD2_PATH := "res://assets/characters/chr_player_lod2.glb"

func _add_lod_meshes() -> void:
	var skeleton := _find_skeleton(runtime_root)
	if skeleton == null:
		return
	_add_lod_from(LOD1_PATH, skeleton, 1)
	_add_lod_from(LOD2_PATH, skeleton, 2)

func _add_lod_from(path: String, skeleton: Skeleton3D, lod_index: int) -> void:
	if not ResourceLoader.exists(path):
		return
	var packed := load(path) as PackedScene
	if packed == null:
		return
	var inst := packed.instantiate() as Node3D
	# Add the GLB instance to the tree first so transforms resolve, then move the
	# mesh under the runtime root keeping its world transform. The cloud LOD GLBs
	# are standalone metre meshes (1.78 m standing) with no bone weights, so they
	# can't be skinned; keeping world transform makes them stand in place.
	add_child(inst)
	var mesh := _find_mesh_instance(inst)
	if mesh == null:
		inst.queue_free()
		return
	mesh.reparent(runtime_root, true)
	# the runtime root is turned 180°Y so LOD0 faces -Z; the cloud GLB faces +Z.
	# Rotate the LOD mesh locally so it matches LOD0's world facing.
	mesh.rotate_y(PI)
	mesh.name = "lod%d__body" % lod_index
	# register in the LOD group so _set_runtime_lod hides/shows it by distance
	# (added after _collect_runtime_nodes ran, so it isn't picked up automatically)
	if lod_index < runtime_lod_groups.size():
		runtime_lod_groups[lod_index].append(mesh)
	inst.queue_free()

## Give every runtime mesh a named material (contract: 1..3 named materials).
func _assign_named_material() -> void:
	var mat := StandardMaterial3D.new()
	mat.resource_name = "mat_chr_player_juvenile"
	mat.albedo_color = Color("bfa982")
	# scan the whole runtime tree (LOD1/2 are added after _collect_runtime_nodes)
	var all_meshes: Array[MeshInstance3D] = []
	_collect_all_meshes(runtime_root, all_meshes)
	for mesh in all_meshes:
		mesh.material_override = mat

func _collect_all_meshes(node: Node, out: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D:
		out.append(node as MeshInstance3D)
	for child in node.get_children():
		_collect_all_meshes(child, out)

func _find_animation_player(node: Node) -> AnimationPlayer:
	if node is AnimationPlayer:
		return node
	for child in node.get_children():
		var found := _find_animation_player(child)
		if found != null:
			return found
	return null

func _find_skeleton(node: Node) -> Skeleton3D:
	if node is Skeleton3D:
		return node
	for child in node.get_children():
		var found := _find_skeleton(child)
		if found != null:
			return found
	return null

func _find_mesh_instance(node: Node) -> MeshInstance3D:
	if node is MeshInstance3D:
		return node
	for child in node.get_children():
		var found := _find_mesh_instance(child)
		if found != null:
			return found
	return null

## The Tencent cloud FBX ships actions with hashed names
## ("Armature|87863..._remap"). Map them to the contract animation names the
## test and the rest of this file expect. Godot 4.6 keeps animations in an
## AnimationLibrary; rename via the default library ("").
func _rename_cloud_animations() -> void:
	var ap := runtime_animation_player as AnimationPlayer
	if ap == null:
		return
	var lib: AnimationLibrary = ap.get_animation_library("")
	if lib == null:
		return
	var rename := {
		"87863afffd9fcbef3afb7f04b6005c1d": "anim_chr_player_idle_neutral",
		"32795ddb244644eac67ccfd8b84060c3": "anim_chr_player_walk_forward",
	}
	for cloud_name in lib.get_animation_list():
		if cloud_name == "RESET":
			continue
		for hash_key in rename:
			if cloud_name.contains(hash_key):
				var target: String = rename[hash_key]
				var anim := lib.get_animation(cloud_name)
				if anim != null:
					if target.contains("idle") or target.contains("walk"):
						anim.loop_mode = Animation.LOOP_LINEAR
				lib.rename_animation(cloud_name, target)
				break

func _collect_runtime_nodes(node: Node) -> void:
	if node is AnimationPlayer and runtime_animation_player == null:
		runtime_animation_player = node as AnimationPlayer
	if node is MeshInstance3D:
		var mesh_instance := node as MeshInstance3D
		var lower_name := mesh_instance.name.to_lower()
		for lod in range(3):
			if "lod%d__" % lod in lower_name:
				runtime_lod_groups[lod].append(mesh_instance)
	for child in node.get_children():
		_collect_runtime_nodes(child)

func _update_runtime_lod() -> void:
	var active_camera := get_viewport().get_camera_3d()
	if active_camera == null:
		_set_runtime_lod(0)
		return
	var distance := global_position.distance_to(active_camera.global_position)
	_set_runtime_lod(0 if distance < 10.0 else (1 if distance < 22.0 else 2))

func _set_runtime_lod(next_lod: int) -> void:
	if next_lod == runtime_lod:
		return
	runtime_lod = next_lod
	for lod in range(3):
		for mesh_instance in runtime_lod_groups[lod]:
			(mesh_instance as MeshInstance3D).visible = lod == runtime_lod

func _update_runtime_animation() -> void:
	if gesture_clock >= 0.0:
		runtime_animation_player.speed_scale = 1.0
		_play_runtime_animation(_runtime_gesture_animation(), 0.12)
		return
	if motion_speed > 0.25:
		runtime_animation_player.speed_scale = clampf(motion_speed / 3.1, 0.72, 1.8)
		_play_runtime_animation(RUNTIME_WALK, 0.16)
	else:
		runtime_animation_player.speed_scale = 1.0
		_play_runtime_animation(RUNTIME_IDLE, 0.18)

func _runtime_gesture_animation() -> String:
	return "anim_chr_player_gesture_%s" % gesture_kind

func _play_runtime_animation(animation_name: String, blend: float) -> void:
	if runtime_animation_player == null or not runtime_animation_player.has_animation(animation_name):
		return
	if runtime_animation == animation_name and runtime_animation_player.is_playing():
		return
	runtime_animation = animation_name
	runtime_animation_player.play(animation_name, blend)

func _build_sail(node_name: String, local_position: Vector3, size: Vector3, yaw: float, color: Color) -> Node3D:
	var pivot := Node3D.new()
	pivot.name = node_name
	pivot.position = local_position
	pivot.rotation.x = -0.42
	pivot.rotation.y = yaw
	head_pivot.add_child(pivot)
	var sail_mesh := PrismMesh.new()
	sail_mesh.size = size
	var sail := _add_mesh(pivot, "Sail", sail_mesh, Vector3(0, size.y * 0.33, 0.06), Vector3.ONE, _material(color))
	sail.rotation.z = yaw * 0.35
	return pivot

func _build_npc_contour(color: Color) -> void:
	match profile:
		0:
			var cap := SphereMesh.new()
			cap.radius = 0.18
			cap.height = 0.28
			_add_mesh(head_pivot, "RoundCap", cap, Vector3(-0.08, 0.3, 0.03), Vector3(1.35, 0.55, 0.9), _material(color))
		1:
			var spire := CylinderMesh.new()
			spire.top_radius = 0.04
			spire.bottom_radius = 0.17
			spire.height = 0.52
			_add_mesh(head_pivot, "TallSpire", spire, Vector3(0.09, 0.43, 0.08), Vector3.ONE, _material(color))
		2:
			primary_sail = _build_sail("LowBackFin", Vector3(-0.15, 0.04, 0.17), Vector3(0.32, 0.38, 0.14), -0.58, color)
		3:
			for index in range(3):
				var bud := SphereMesh.new()
				bud.radius = 0.105 - float(index) * 0.012
				bud.height = bud.radius * 2.0
				_add_mesh(head_pivot, "CrownBud%d" % index, bud, Vector3(-0.16 + index * 0.16, 0.31 + absf(index - 1) * 0.05, 0.02), Vector3.ONE, _material(color))
		4:
			var crest := PrismMesh.new()
			crest.size = Vector3(0.5, 0.22, 0.16)
			var crest_mesh := _add_mesh(head_pivot, "FlatCrest", crest, Vector3(0.1, 0.31, 0.04), Vector3.ONE, _material(color))
			crest_mesh.rotation.z = -0.24

func _build_limb(node_name: String, local_position: Vector3, color: Color, length: float, radius: float) -> Node3D:
	var pivot := Node3D.new()
	pivot.name = node_name
	pivot.position = local_position
	procedural_root.add_child(pivot)
	var mesh := CapsuleMesh.new()
	mesh.radius = radius
	mesh.height = length
	_add_mesh(pivot, "Limb", mesh, Vector3(0, -length * 0.42, 0), Vector3.ONE, _material(color))
	return pivot

func _build_hand(parent: Node3D, node_name: String, local_position: Vector3, color: Color) -> MeshInstance3D:
	var palm_mesh := SphereMesh.new()
	palm_mesh.radius = 0.12
	palm_mesh.height = 0.2
	return _add_mesh(parent, node_name, palm_mesh, local_position, Vector3(1.25, 0.7, 0.9), _material(color))

func _apply_npc_profile() -> void:
	match profile:
		0:
			torso_pivot.scale = Vector3(1.18, 0.9, 1.0)
			left_arm.position.x = -0.45
			right_arm.position.x = 0.45
		1:
			torso_pivot.scale = Vector3(0.82, 1.22, 0.82)
			head_pivot.position.y += 0.16
			left_leg.scale.y = 1.16
			right_leg.scale.y = 1.16
		2:
			torso_pivot.scale = Vector3(1.28, 0.78, 1.08)
			head_pivot.scale = Vector3(1.22, 0.88, 1.0)
			head_pivot.position.y -= 0.08
		3:
			torso_pivot.scale = Vector3(0.9, 1.08, 0.86)
			left_arm.scale.y = 1.28
			right_arm.scale.y = 1.28
			left_hand.position.y -= 0.12
			right_hand.position.y -= 0.12
		4:
			torso_pivot.scale = Vector3(1.05, 0.96, 0.82)
			head_pivot.scale = Vector3(0.96, 1.16, 0.92)
			left_arm.position.y += 0.12
			right_arm.position.y -= 0.08

func _update_idle_segment(delta: float) -> void:
	if locomotion_blend > 0.08 or airborne_blend > 0.08 or gesture_clock >= 0.0:
		idle_is_breathing = false
		idle_segment_remaining = maxf(idle_segment_remaining, 0.35)
		return
	idle_segment_remaining -= delta
	if idle_segment_remaining > 0.0:
		return
	idle_is_breathing = not idle_is_breathing
	if idle_is_breathing:
		idle_segment_remaining = IDLE_BREATH_DURATION
	else:
		idle_segment_remaining = 1.0 + fmod(animation_clock * 0.37 + personality_phase, 2.0)

func _apply_pose() -> void:
	var stride := sin(animation_clock * lerpf(4.6, 10.5, locomotion_blend)) * locomotion_blend
	var breath := 0.0
	if idle_is_breathing:
		var breath_progress := 1.0 - idle_segment_remaining / IDLE_BREATH_DURATION
		breath = sin(breath_progress * TAU) * 0.018
	torso_pivot.position.y = 0.02 + breath + absf(stride) * 0.025
	torso_pivot.rotation = Vector3(0, 0, stride * 0.045)
	head_pivot.position.y = 0.78 + breath * 0.7 + absf(stride) * 0.015
	head_pivot.rotation = Vector3(0, 0, -stride * 0.035)
	left_arm.rotation = Vector3(stride * 0.7, 0, 0)
	right_arm.rotation = Vector3(-stride * 0.7, 0, 0)
	left_leg.rotation = Vector3(-stride * 0.92, 0, 0)
	right_leg.rotation = Vector3(stride * 0.92, 0, 0)
	if primary_sail:
		primary_sail.rotation.z = -0.28 - locomotion_blend * 0.05
	if secondary_sail:
		secondary_sail.rotation.z = -0.36 - locomotion_blend * 0.03
	if airborne_blend > 0.0:
		left_leg.rotation.x = lerpf(left_leg.rotation.x, -0.52, airborne_blend)
		right_leg.rotation.x = lerpf(right_leg.rotation.x, 0.52, airborne_blend)
		left_arm.rotation.x = lerpf(left_arm.rotation.x, 0.38, airborne_blend)
		right_arm.rotation.x = lerpf(right_arm.rotation.x, 0.38, airborne_blend)
	if gesture_clock >= 0.0:
		_apply_gesture_pose(_gesture_envelope())

func _gesture_duration() -> float:
	match gesture_kind:
		"offer":
			return 1.25
		"clarify":
			return 1.12
		_:
			return 0.96

func _gesture_envelope() -> float:
	var duration := _gesture_duration()
	var attack := 0.18
	var release := 0.25
	if gesture_clock < attack:
		return _ease_cubic(gesture_clock / attack)
	if gesture_clock < duration - release:
		return 1.0
	return _ease_cubic((duration - gesture_clock) / release)

func _apply_gesture_pose(envelope: float) -> void:
	match gesture_kind:
		"offer":
			left_arm.rotation.x = lerpf(left_arm.rotation.x, -0.8, envelope)
			right_arm.rotation.x = lerpf(right_arm.rotation.x, -0.8, envelope)
			left_arm.rotation.z = -0.34 * envelope
			right_arm.rotation.z = 0.34 * envelope
			head_pivot.rotation.x = 0.1 * envelope
		"clarify":
			left_arm.rotation.z = -0.72 * envelope
			right_arm.rotation.z = 0.72 * envelope
			head_pivot.rotation.z = -0.14 * envelope
		"greet":
			right_arm.rotation.z = -1.18 * envelope
			right_arm.rotation.x = 0.18 * envelope
			head_pivot.rotation.z = -0.1 * envelope

func _ease_cubic(value: float) -> float:
	var clamped := clampf(value, 0.0, 1.0)
	return 1.0 - pow(1.0 - clamped, 3.0)

func _add_mesh(parent: Node3D, node_name: String, mesh: PrimitiveMesh, local_position: Vector3, scale_value: Vector3, material: Material) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = node_name
	instance.mesh = mesh
	instance.position = local_position
	instance.scale = scale_value
	instance.material_override = material
	parent.add_child(instance)
	return instance

func _material(color: Color, emission := Color.TRANSPARENT) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.78
	if emission.a > 0.0:
		material.emission_enabled = true
		material.emission = emission
		material.emission_energy_multiplier = 0.36
	return material
