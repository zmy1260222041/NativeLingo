class_name CharacterVisual
extends Node3D

const IDLE_BREATH_DURATION := 2.4
const PLAYER_MODEL_PATH := "res://assets/characters/chr_player_juvenile.glb"
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
	# The cloud-built GLB (v06) faces +Z; the third-person rig needs it facing
	# -Z (away from camera). Turn 180° around Godot's up axis. Loader-side
	# correction until the export bakes -Z forward directly.
	runtime_root.rotation_degrees.y = 180.0
	add_child(runtime_root)
	_collect_runtime_nodes(runtime_root)
	if runtime_animation_player == null:
		remove_child(runtime_root)
		runtime_root.free()
		runtime_root = null
		return false
	_set_runtime_lod(0)
	_play_runtime_animation(RUNTIME_IDLE, 0.0)
	return true

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
