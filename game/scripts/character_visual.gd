class_name CharacterVisual
extends Node3D

const IDLE_BREATH_DURATION := 2.4
const PLAYER_MODEL_PATH := "res://assets/characters/chr_player_juvenile_mixamo.fbx"
const RUNTIME_IDLE := "anim_chr_player_idle_neutral"
const RUNTIME_WALK := "anim_chr_player_walk_forward"
const RUNTIME_RUN := "anim_chr_player_run_forward"
const RUNTIME_POINT := "anim_chr_player_gesture_point"
const RUNTIME_OBSERVE := "anim_chr_player_interact_observe"
const RUNTIME_GATHER := "anim_chr_player_interact_gather"
const RUNTIME_TURN_180 := "anim_chr_player_turn_180"
const RUNTIME_JUMP := "anim_chr_player_jump"
const RUNTIME_JUMP_CHAIN := "anim_chr_player_jump_chain_internal"
const RETARGET_REPORT_PATH := "res://assets/characters/chr_player_juvenile_mixamo_retarget.json"
const WALK_CYCLE_DISTANCE_M := 5.562
const RUN_CYCLE_DISTANCE_M := 11.726
const JUMP_ANTICIPATION_SPEED := 1.6
const JUMP_RECOVERY_SPEED := 1.25
const JUMP_DEFAULT_TAKEOFF_TIME := 1.3
const JUMP_DEFAULT_LANDING_TIME := 1.933333
const JUMP_CHAIN_BLEND_SECONDS := 0.18
const JUMP_CHAIN_PHASE_SAMPLE_COUNT := 40
const JUMP_CHAIN_ROTATION_WEIGHT_M := 0.05
const JUMP_CHAIN_MATCH_BONES := [
	"Hips", "Spine", "Spine1", "Spine2",
	"LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
	"RightUpLeg", "RightLeg", "RightFoot", "RightToeBase",
	"LeftArm", "LeftForeArm", "LeftHand",
	"RightArm", "RightForeArm", "RightHand",
]
const JUMP_CHAIN_FOOT_BONES := ["LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]
const TURN_PHASE_SAMPLE_COUNT := 64
const TURN_PHASE_ROTATION_WEIGHT_M := 0.05
const TURN_TRANSITION_CORRECTION_DURATION := 0.2
const GATHER_INTERACTION_KINDS := ["berry", "scrap", "water"]

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
var authored_static_root: Node3D
var authored_static_base_position := Vector3.ZERO
var authored_static_base_rotation := Vector3.ZERO
var runtime_animation_player: AnimationPlayer
var runtime_lod_groups: Array = [[], [], []]
var runtime_lod := -1
var runtime_animation := ""
var debug_animation_override := ""
var debug_probe_active := false
var turn_active := false
var jump_active := false
var jump_expected_duration := 1.4
var jump_stage := "idle"
var jump_takeoff_time := JUMP_DEFAULT_TAKEOFF_TIME
var jump_landing_time := JUMP_DEFAULT_LANDING_TIME
var jump_authored_airborne_lift_m := 0.0
var jump_chain_entry_time := 0.0
var jump_chain_pose_error_m := 0.0
var jump_chain_rotation_error_deg := 0.0
var jump_chain_count := 0
var jump_last_valid_position := 0.0
var turn_to_locomotion_phase_seconds := {}
var turn_to_locomotion_foot_error_m := {}
var turn_to_locomotion_aligned_foot_error_m := {}
var turn_to_locomotion_rotation_error_deg := {}
var turn_to_locomotion_translation := {}
var runtime_root_base_position := Vector3.ZERO
var turn_transition_correction := Vector3.ZERO
var turn_transition_elapsed := TURN_TRANSITION_CORRECTION_DURATION
var turn_phase_matches_ready := false

func configure(base_color: Color, accent_color: Color, style_profile := 0, player_character := false) -> void:
	profile = clampi(style_profile, 0, 4)
	personality_phase = float(profile) * 0.73
	is_player_character = player_character
	idle_segment_remaining = 1.0 + fmod(personality_phase, 1.8)
	add_to_group("character_visual")
	_build(base_color, accent_color)
	var bridge := _get_debug_bridge()
	if bridge != null and bridge.has_method("register_character"):
		bridge.register_character(self)


## Replace an NPC's procedural placeholder with a source-authored static GLB.
## The CharacterVisual node remains the interaction/reaction anchor; until a
## proper rig exists, idle and reaction feedback are limited to subtle whole-
## model motion so the A-pose mesh is never deformed incorrectly.
func use_authored_static_model(
	model_path: String,
	source_height_m: float,
	target_height_m: float,
	local_ground_y: float,
	yaw_degrees := 180.0,
) -> bool:
	if is_player_character or source_height_m <= 0.0 or not ResourceLoader.exists(model_path):
		return false
	var packed := load(model_path) as PackedScene
	if packed == null:
		return false
	var instance := packed.instantiate() as Node3D
	if instance == null:
		return false
	if authored_static_root != null:
		authored_static_root.queue_free()
	if procedural_root != null:
		procedural_root.visible = false
	instance.name = "AuthoredStaticModel"
	var uniform_scale := target_height_m / source_height_m
	instance.scale = Vector3.ONE * uniform_scale
	instance.position = Vector3(0.0, local_ground_y, 0.0)
	instance.rotation_degrees.y = yaw_degrees
	add_child(instance)
	authored_static_root = instance
	authored_static_base_position = instance.position
	authored_static_base_rotation = instance.rotation
	_set_authored_mesh_shadows(instance)
	return true


func _set_authored_mesh_shadows(node: Node) -> void:
	if node is MeshInstance3D:
		(node as MeshInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	for child in node.get_children():
		_set_authored_mesh_shadows(child)

func set_motion(speed: float, is_airborne: bool) -> void:
	motion_speed = speed
	airborne = is_airborne

func has_turn_around_animation() -> bool:
	return runtime_animation_player != null and runtime_animation_player.has_animation(RUNTIME_TURN_180)

func start_turn_around() -> float:
	if not has_turn_around_animation():
		return 0.0
	turn_active = true
	jump_active = false
	gesture_clock = -1.0
	runtime_animation_player.speed_scale = 1.0
	_play_runtime_animation(RUNTIME_TURN_180, 0.08, "large_direction_change")
	var animation := runtime_animation_player.get_animation(RUNTIME_TURN_180)
	return animation.length if animation != null else 0.0

func finish_turn_around(resume_motion_speed := 0.0) -> void:
	if not turn_active:
		return
	turn_active = false
	# PlayerController changes CharacterVisual's outer yaw at the same instant.
	# Match the outgoing feet to the nearest locomotion phase and switch with no
	# pose blend.  The outer 180-degree yaw and the removal of the authored Hips
	# yaw happen atomically, while the selected phase keeps both feet in place.
	if resume_motion_speed > 0.25:
		motion_speed = resume_motion_speed
		var locomotion_animation := RUNTIME_RUN if resume_motion_speed > 6.4 and runtime_animation_player.has_animation(RUNTIME_RUN) else RUNTIME_WALK
		runtime_animation_player.speed_scale = _locomotion_speed_scale(locomotion_animation, resume_motion_speed)
		_play_runtime_animation(locomotion_animation, 0.0, "turn_complete_phase_match")
		var phase_time := float(turn_to_locomotion_phase_seconds.get(locomotion_animation, 0.0))
		runtime_animation_player.seek(phase_time, true, true)
		turn_transition_correction = turn_to_locomotion_translation.get(locomotion_animation, Vector3.ZERO) as Vector3
		turn_transition_elapsed = 0.0
		if runtime_root != null:
			runtime_root.position = runtime_root_base_position + turn_transition_correction
	else:
		runtime_animation_player.speed_scale = 1.0
		_play_runtime_animation(RUNTIME_IDLE, 0.0, "turn_complete")
	runtime_animation_player.advance(0.0)

func start_jump_sequence() -> bool:
	if runtime_animation_player == null or not runtime_animation_player.has_animation(RUNTIME_JUMP):
		return false
	if jump_active:
		if jump_stage == "recovery" and _is_jump_animation(runtime_animation):
			return _start_chained_jump_sequence()
		return false
	jump_active = true
	jump_stage = "anticipation"
	jump_last_valid_position = 0.0
	turn_active = false
	gesture_clock = -1.0
	runtime_animation_player.speed_scale = JUMP_ANTICIPATION_SPEED
	_play_runtime_animation(RUNTIME_JUMP, 0.08, "jump_anticipation")
	return true

func _start_chained_jump_sequence() -> bool:
	## A chain jump begins while the previous jump is still in its authored
	## landing recovery. Match that exact outgoing pose to the closest planted
	## anticipation phase, then crossfade instead of hard-resetting to frame 1.
	var skeleton := _find_skeleton(runtime_root)
	if skeleton == null:
		return false
	var bone_indices: Array[int] = []
	var foot_pose_indices: Array[int] = []
	for bone_name in JUMP_CHAIN_MATCH_BONES:
		var bone_index := skeleton.find_bone(String(bone_name))
		if bone_index < 0:
			continue
		if bone_name in JUMP_CHAIN_FOOT_BONES:
			foot_pose_indices.append(bone_indices.size())
		bone_indices.append(bone_index)
	if bone_indices.is_empty() or foot_pose_indices.is_empty():
		return false

	var outgoing_animation := runtime_animation
	var outgoing_time := runtime_animation_player.current_animation_position
	var outgoing_poses: Array[Transform3D] = []
	for bone_index in bone_indices:
		outgoing_poses.append(_bone_pose_in_visual_space(skeleton, bone_index))

	var best_time := 0.0
	var best_position_error := INF
	var best_rotation_error := INF
	var best_score := INF
	for sample_index in JUMP_CHAIN_PHASE_SAMPLE_COUNT:
		var sample_time := jump_takeoff_time * float(sample_index) / float(JUMP_CHAIN_PHASE_SAMPLE_COUNT)
		runtime_animation_player.play(RUNTIME_JUMP, 0.0)
		runtime_animation_player.seek(sample_time, true, true)
		runtime_animation_player.advance(0.0)
		var candidate_poses: Array[Transform3D] = []
		for bone_index in bone_indices:
			candidate_poses.append(_bone_pose_in_visual_space(skeleton, bone_index))
		var foot_translation := Vector3.ZERO
		for pose_index in foot_pose_indices:
			foot_translation += outgoing_poses[pose_index].origin - candidate_poses[pose_index].origin
		foot_translation /= float(foot_pose_indices.size())
		var position_error := 0.0
		var rotation_error := 0.0
		for pose_index in bone_indices.size():
			position_error += outgoing_poses[pose_index].origin.distance_to(candidate_poses[pose_index].origin + foot_translation)
			rotation_error += outgoing_poses[pose_index].basis.get_rotation_quaternion().angle_to(candidate_poses[pose_index].basis.get_rotation_quaternion())
		position_error /= float(bone_indices.size())
		rotation_error /= float(bone_indices.size())
		var score := position_error + rotation_error * JUMP_CHAIN_ROTATION_WEIGHT_M
		if score < best_score:
			best_score = score
			best_time = sample_time
			best_position_error = position_error
			best_rotation_error = rotation_error

	# Re-evaluate the exact outgoing pose before starting the blend; pose-search
	# temporarily moved the player through the source animation.
	runtime_animation_player.play(outgoing_animation, 0.0)
	runtime_animation_player.seek(outgoing_time, true, true)
	runtime_animation_player.advance(0.0)
	var target_animation := RUNTIME_JUMP_CHAIN if outgoing_animation == RUNTIME_JUMP else RUNTIME_JUMP
	jump_stage = "anticipation"
	turn_active = false
	gesture_clock = -1.0
	runtime_animation_player.speed_scale = JUMP_ANTICIPATION_SPEED
	runtime_animation = target_animation
	runtime_animation_player.play(target_animation, JUMP_CHAIN_BLEND_SECONDS)
	runtime_animation_player.seek(best_time, true, true)
	runtime_animation_player.advance(0.0)
	jump_chain_entry_time = best_time
	jump_chain_pose_error_m = best_position_error
	jump_chain_rotation_error_deg = rad_to_deg(best_rotation_error)
	jump_chain_count += 1
	jump_last_valid_position = best_time
	_debug_log_animation_transition(target_animation, "jump_chain_phase_match")
	DebugLog.info("animation", "jump_chain_match count=%d from_time=%.3f entry_time=%.3f pose_error_m=%.4f rotation_error_deg=%.2f blend=%.3f" % [jump_chain_count, outgoing_time, best_time, best_position_error, jump_chain_rotation_error_deg, JUMP_CHAIN_BLEND_SECONDS])
	return true

func _is_jump_animation(animation_name: String) -> bool:
	return animation_name == RUNTIME_JUMP or animation_name == RUNTIME_JUMP_CHAIN

func _ensure_jump_animation_for_stage() -> void:
	## Defense in depth: no reaction or other one-shot may strand jump_active on
	## a non-jump clip. This also repairs an already-corrupted runtime state.
	if runtime_animation_player == null or _is_jump_animation(runtime_animation):
		return
	var resume_time := jump_last_valid_position
	match jump_stage:
		"anticipation":
			resume_time = clampf(resume_time, 0.0, jump_takeoff_time)
			runtime_animation_player.speed_scale = JUMP_ANTICIPATION_SPEED
		"airborne":
			resume_time = clampf(resume_time, jump_takeoff_time, jump_landing_time)
			var authored_airtime := maxf(0.01, jump_landing_time - jump_takeoff_time)
			runtime_animation_player.speed_scale = clampf(authored_airtime / maxf(0.1, jump_expected_duration), 0.2, 2.0)
		"recovery":
			resume_time = maxf(jump_landing_time, resume_time)
			runtime_animation_player.speed_scale = JUMP_RECOVERY_SPEED
		_:
			resume_time = 0.0
	runtime_animation = RUNTIME_JUMP
	runtime_animation_player.play(RUNTIME_JUMP, 0.0)
	runtime_animation_player.seek(resume_time, true, true)
	runtime_animation_player.advance(0.0)
	DebugLog.info("animation", "jump_animation_guard restored_stage=%s restored_time=%.3f" % [jump_stage, resume_time])

func is_jump_takeoff_due() -> bool:
	return jump_active and jump_stage == "anticipation" and _is_jump_animation(runtime_animation) and runtime_animation_player.current_animation_position >= jump_takeoff_time - 0.001

func mark_jump_launched(expected_airtime: float) -> void:
	if not jump_active:
		return
	_ensure_jump_animation_for_stage()
	jump_stage = "airborne"
	jump_expected_duration = maxf(0.1, expected_airtime)
	# Remove frame scheduling jitter: physics launch and the first authored
	# airborne pose both start at the exact measured takeoff marker.
	runtime_animation_player.seek(jump_takeoff_time, true, true)
	var authored_airtime := maxf(0.01, jump_landing_time - jump_takeoff_time)
	runtime_animation_player.speed_scale = clampf(authored_airtime / jump_expected_duration, 0.2, 2.0)
	_debug_log_jump_stage("airborne")

func mark_jump_landed() -> void:
	if not jump_active:
		return
	jump_stage = "recovery"
	_ensure_jump_animation_for_stage()
	# CharacterBody3D floor contact is authoritative. Align the authored feet to
	# their measured contact frame, then play the crouch recovery independently.
	runtime_animation_player.seek(jump_landing_time, true, true)
	runtime_animation_player.speed_scale = JUMP_RECOVERY_SPEED
	_debug_log_jump_stage("recovery")

func get_jump_authored_airborne_lift_m() -> float:
	return maxf(0.0, jump_authored_airborne_lift_m)

func play_jump(expected_airtime: float) -> bool:
	## Compatibility/debug helper: start at takeoff without the anticipation.
	if not start_jump_sequence():
		return false
	mark_jump_launched(expected_airtime)
	return true

func can_play_reaction() -> bool:
	return not debug_probe_active and not jump_active and not airborne and not turn_active

func play_reaction(kind := "greet") -> bool:
	if not can_play_reaction():
		DebugLog.info("animation", "reaction_rejected kind=%s jump_active=%s jump_stage=%s airborne=%s turn_active=%s" % [kind, jump_active, jump_stage, airborne, turn_active])
		return false
	gesture_kind = kind if kind in ["greet", "offer", "clarify", "point", "observe", "gather"] else "greet"
	gesture_clock = 0.0
	if runtime_animation_player:
		runtime_animation_player.speed_scale = 1.0
		_play_runtime_animation(_runtime_gesture_animation(), 0.12, "reaction")
	return true

func play_environment_interaction(interaction_kind: String) -> bool:
	## Pickups and water use the authored collect motion. Fixed facilities use
	## the authored observation motion; NPC communication remains on the
	## existing greet/offer/clarify/point reactions.
	return play_reaction("gather" if interaction_kind in GATHER_INTERACTION_KINDS else "observe")

func debug_play_animation(animation_name: String, blend := 0.0) -> bool:
	if runtime_animation_player == null or not runtime_animation_player.has_animation(animation_name):
		return false
	debug_animation_override = animation_name
	debug_probe_active = true
	runtime_animation_player.speed_scale = 1.0
	_play_runtime_animation(animation_name, blend, "debug_probe")
	return true

func debug_clear_animation_override() -> void:
	debug_animation_override = ""
	debug_probe_active = false

func get_debug_animation_names() -> Array[String]:
	var names: Array[String] = []
	if runtime_animation_player == null:
		return names
	for name in runtime_animation_player.get_animation_list():
		names.append(name)
	return names

func get_animation_debug_state(bone_names: Array = []) -> Dictionary:
	var state := {
		"animation": runtime_animation,
		"animation_position": 0.0,
		"animation_length": 0.0,
		"speed_scale": runtime_animation_player.speed_scale if runtime_animation_player else 1.0,
		"motion_speed": motion_speed,
		"airborne": airborne,
		"turn_active": turn_active,
		"jump_active": jump_active,
		"jump_stage": jump_stage,
		"jump_takeoff_time": jump_takeoff_time,
		"jump_landing_time": jump_landing_time,
		"jump_authored_airborne_lift_m": jump_authored_airborne_lift_m,
		"jump_chain_entry_time": jump_chain_entry_time,
		"jump_chain_pose_error_m": jump_chain_pose_error_m,
		"jump_chain_rotation_error_deg": jump_chain_rotation_error_deg,
		"jump_chain_count": jump_chain_count,
		"reaction_locked": not can_play_reaction(),
		"turn_to_locomotion_phase_seconds": turn_to_locomotion_phase_seconds.duplicate(),
		"turn_to_locomotion_foot_error_m": turn_to_locomotion_foot_error_m.duplicate(),
		"turn_to_locomotion_aligned_foot_error_m": turn_to_locomotion_aligned_foot_error_m.duplicate(),
		"turn_to_locomotion_rotation_error_deg": turn_to_locomotion_rotation_error_deg.duplicate(),
		"turn_to_locomotion_translation": turn_to_locomotion_translation.duplicate(),
		"turn_transition_correction": turn_transition_correction,
		"global_position": global_position,
		"debug_override": debug_animation_override,
		"debug_probe_active": debug_probe_active,
		"armature_scale": Vector3.ONE,
		"hips_position": Vector3.ZERO,
		"bones": {},
	}
	if runtime_animation_player != null:
		state["animation_position"] = runtime_animation_player.current_animation_position
		var current := runtime_animation_player.get_animation(runtime_animation)
		if current != null:
			state["animation_length"] = current.length
	if runtime_root == null:
		return state
	var armature := runtime_root.get_node_or_null("Armature") as Node3D
	if armature != null:
		state["armature_scale"] = armature.scale
	var skeleton := _find_skeleton(runtime_root)
	if skeleton == null:
		return state
	var selected: Array = bone_names
	if selected.is_empty():
		selected = ["Hips", "Head", "LeftFoot", "RightFoot"]
	for bone_name in selected:
		var index := skeleton.find_bone(String(bone_name))
		if index < 0:
			continue
		var rotation := skeleton.get_bone_pose_rotation(index)
		var global_pose := skeleton.get_bone_global_pose(index)
		var world_pose := skeleton.global_transform * global_pose
		state["bones"][String(bone_name)] = {
			"rotation": rotation,
			"position": skeleton.get_bone_pose_position(index),
			"global_rotation": global_pose.basis.get_rotation_quaternion(),
			"global_position": global_pose.origin,
			"world_rotation": world_pose.basis.get_rotation_quaternion(),
			"world_position": world_pose.origin,
		}
		if bone_name == "Hips":
			state["hips_position"] = skeleton.get_bone_pose_position(index)
	return state

func _process(delta: float) -> void:
	if is_player_character and runtime_root == null:
		return
	animation_clock += delta
	_update_turn_transition_correction(delta)
	locomotion_blend = move_toward(locomotion_blend, clampf(motion_speed / 8.2, 0.0, 1.0), delta * 4.8)
	airborne_blend = move_toward(airborne_blend, 1.0 if airborne else 0.0, delta * 7.0)
	if gesture_clock >= 0.0:
		gesture_clock += delta
		if gesture_clock > _gesture_duration():
			gesture_clock = -1.0
	if jump_active and runtime_animation_player != null and _is_jump_animation(runtime_animation):
		jump_last_valid_position = runtime_animation_player.current_animation_position
	if jump_active and jump_stage == "recovery" and runtime_animation_player != null and _is_jump_animation(runtime_animation):
		var jump_animation := runtime_animation_player.get_animation(runtime_animation)
		if jump_animation != null and runtime_animation_player.current_animation_position >= jump_animation.length - 0.02:
			jump_active = false
			jump_stage = "idle"
	if authored_static_root:
		var breath := (sin(animation_clock * 2.1 + personality_phase) + 1.0) * 0.0035
		var reaction := _gesture_envelope() if gesture_clock >= 0.0 else 0.0
		authored_static_root.position = authored_static_base_position + Vector3(0.0, breath + reaction * 0.018, 0.0)
		authored_static_root.rotation = authored_static_base_rotation + Vector3(0.0, 0.0, reaction * 0.035)
		return
	if runtime_root:
		# Animation probes must render the skinned LOD0. LOD1/2 are current
		# static-mesh placeholders and would make every captured action look like
		# the same standing pose even while skeleton telemetry is changing.
		if debug_probe_active:
			_set_runtime_lod(0)
		else:
			_update_runtime_lod()
		if not debug_animation_override.is_empty():
			if runtime_animation != debug_animation_override:
				_play_runtime_animation(debug_animation_override, 0.0)
		else:
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
	runtime_root_base_position = runtime_root.position
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
	_sanitize_runtime_animation_tracks()
	_restore_hips_position_tracks()
	# New player FBX files contain the selected Mixamo retarget. Keep the old
	# cloud walk source as a compatibility fallback for older local assets.
	if not runtime_animation_player.has_animation(RUNTIME_WALK):
		_add_walk_from_source()
		_sanitize_runtime_animation_tracks()
		_restore_hips_position_tracks()
	_add_jump_chain_animation()
	_add_procedural_gestures()
	_add_lod_meshes()
	_assign_named_material()
	_set_runtime_lod(0)
	if is_inside_tree():
		_prepare_turn_locomotion_phase_matches()
	else:
		call_deferred("_prepare_turn_locomotion_phase_matches")
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
		"87863afffd9fcbef3afb7f04b6005c1d": RUNTIME_IDLE,
		"32795ddb244644eac67ccfd8b84060c3": RUNTIME_WALK,
		RUNTIME_IDLE: RUNTIME_IDLE,
		RUNTIME_WALK: RUNTIME_WALK,
		RUNTIME_RUN: RUNTIME_RUN,
		RUNTIME_POINT: RUNTIME_POINT,
		RUNTIME_OBSERVE: RUNTIME_OBSERVE,
		RUNTIME_GATHER: RUNTIME_GATHER,
		RUNTIME_TURN_180: RUNTIME_TURN_180,
		RUNTIME_JUMP: RUNTIME_JUMP,
	}
	for cloud_name in lib.get_animation_list():
		if cloud_name == "RESET":
			continue
		var target := cloud_name
		for marker in rename:
			if cloud_name.contains(marker):
				target = rename[marker]
				break
		var anim := lib.get_animation(cloud_name)
		if anim != null and (target == RUNTIME_IDLE or target == RUNTIME_WALK or target == RUNTIME_RUN):
			anim.loop_mode = Animation.LOOP_LINEAR
			if target == RUNTIME_WALK:
				anim.set_meta("cycle_distance_m", WALK_CYCLE_DISTANCE_M)
			elif target == RUNTIME_RUN:
				anim.set_meta("cycle_distance_m", RUN_CYCLE_DISTANCE_M)
		if target != cloud_name and not lib.has_animation(target):
			lib.rename_animation(cloud_name, target)

func _sanitize_runtime_animation_tracks() -> void:
	## Imported FBX actions must not animate object scale or Armature position.
	## Blender's FBX bake can emit the armature's centimeter conversion as a
	## root scale track (Godot reads it as 100x), which makes the player pop
	## larger when walk/run/gesture starts. CharacterBody3D owns world
	## translation, while the Hips bone is allowed to retain in-place motion.
	var lib := runtime_animation_player.get_animation_library("")
	if lib == null:
		return
	for anim_name in lib.get_animation_list():
		var animation := lib.get_animation(anim_name)
		if animation == null:
			continue
		for track_index in range(animation.get_track_count() - 1, -1, -1):
			var track_type := animation.track_get_type(track_index)
			if track_type == Animation.TYPE_SCALE_3D:
				animation.remove_track(track_index)
				continue
			if track_type == Animation.TYPE_POSITION_3D:
				var path := animation.track_get_path(track_index)
				# Armature/Skeleton3D:Hips is valid local motion. A one-node
				# path is the imported Armature object transform and is unsafe.
				if path.get_name_count() <= 1 and not _is_safe_in_place_position(animation, track_index):
					animation.remove_track(track_index)

func _restore_hips_position_tracks() -> void:
	## Godot's FBX importer does not reliably preserve root-bone position
	## channels. The Blender retarget report is the authoritative, already
	## de-drifted Hips key stream; restore it as a bone track after import.
	if runtime_animation_player == null or not FileAccess.file_exists(RETARGET_REPORT_PATH):
		return
	var file := FileAccess.open(RETARGET_REPORT_PATH, FileAccess.READ)
	if file == null:
		return
	var parsed = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		return
	var actions: Dictionary = parsed.get("actions", {})
	_load_jump_motion_markers(actions)
	var lib := runtime_animation_player.get_animation_library("")
	if lib == null:
		return
	var skeleton := _find_skeleton(runtime_root)
	var hips_index := skeleton.find_bone("Hips") if skeleton != null else -1
	var hips_rest_position: Vector3 = skeleton.get_bone_rest(hips_index).origin if hips_index >= 0 else Vector3.ZERO
	for animation_name in actions:
		var animation := lib.get_animation(String(animation_name))
		var keys: Array = actions[animation_name].get("hips_position_keys", [])
		if animation == null or keys.is_empty():
			continue
		var has_hips_position := false
		for track_index in animation.get_track_count():
			if animation.track_get_type(track_index) == Animation.TYPE_POSITION_3D:
				var path := animation.track_get_path(track_index)
				if path.get_subname_count() > 0 and path.get_subname(path.get_subname_count() - 1) == "Hips":
					has_hips_position = true
					break
			if has_hips_position:
				break
		if has_hips_position:
			continue
		var track := animation.add_track(Animation.TYPE_POSITION_3D)
		animation.track_set_path(track, NodePath("Armature/Skeleton3D:Hips"))
		var first_frame := float(keys[0].get("frame", 1))
		for item in keys:
			var position_values: Array = item.get("position", [0.0, 0.0, 0.0])
			var position := hips_rest_position + Vector3(float(position_values[0]), float(position_values[1]), float(position_values[2]))
			animation.track_insert_key(track, (float(item.get("frame", first_frame)) - first_frame) / 30.0, position)

func _add_jump_chain_animation() -> void:
	## AnimationPlayer resumes rather than blends when play() receives the same
	## animation name. A duplicate lets consecutive jumps alternate names while
	## preserving the exact same authored tracks and rest-space interpretation.
	if runtime_animation_player == null or not runtime_animation_player.has_animation(RUNTIME_JUMP):
		return
	var lib := runtime_animation_player.get_animation_library("")
	if lib == null or lib.has_animation(RUNTIME_JUMP_CHAIN):
		return
	var source := lib.get_animation(RUNTIME_JUMP)
	var duplicate := source.duplicate(true) as Animation
	if duplicate == null:
		return
	duplicate.loop_mode = Animation.LOOP_NONE
	lib.add_animation(RUNTIME_JUMP_CHAIN, duplicate)

func _load_jump_motion_markers(actions: Dictionary) -> void:
	var jump_data = actions.get(RUNTIME_JUMP, {})
	if not jump_data is Dictionary:
		return
	var markers = jump_data.get("motion_markers", {})
	if not markers is Dictionary or markers.is_empty():
		return
	jump_takeoff_time = float(markers.get("takeoff_time_seconds", JUMP_DEFAULT_TAKEOFF_TIME))
	jump_landing_time = float(markers.get("landing_time_seconds", JUMP_DEFAULT_LANDING_TIME))
	jump_authored_airborne_lift_m = maxf(0.0, float(markers.get("authored_airborne_lift_m", 0.0)))
	DebugLog.info("animation", "jump_markers takeoff=%.3f landing=%.3f authored_lift=%.3f" % [jump_takeoff_time, jump_landing_time, jump_authored_airborne_lift_m])

func _is_safe_in_place_position(animation: Animation, track_index: int) -> bool:
	if animation.track_get_key_count(track_index) < 2:
		return false
	var first := animation.track_get_key_value(track_index, 0) as Vector3
	var last := animation.track_get_key_value(track_index, animation.track_get_key_count(track_index) - 1) as Vector3
	var max_offset := 0.0
	for key_index in animation.track_get_key_count(track_index):
		var value := animation.track_get_key_value(track_index, key_index) as Vector3
		max_offset = maxf(max_offset, value.distance_to(first))
	return max_offset > 0.001 and max_offset < 0.5 and last.distance_to(first) < 0.02

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

func _prepare_turn_locomotion_phase_matches() -> void:
	if turn_phase_matches_ready or not is_inside_tree():
		return
	if runtime_animation_player == null or not runtime_animation_player.has_animation(RUNTIME_TURN_180):
		return
	var skeleton := _find_skeleton(runtime_root)
	if skeleton == null:
		return
	var bone_indices: Array[int] = []
	for bone_name in ["LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]:
		var bone_index := skeleton.find_bone(bone_name)
		if bone_index >= 0:
			bone_indices.append(bone_index)
	if bone_indices.is_empty():
		return

	var turn_animation := runtime_animation_player.get_animation(RUNTIME_TURN_180)
	runtime_animation_player.play(RUNTIME_TURN_180, 0.0)
	runtime_animation_player.seek(turn_animation.length, true, true)
	runtime_animation_player.advance(0.0)
	var turn_poses: Array[Transform3D] = []
	for bone_index in bone_indices:
		turn_poses.append(_bone_pose_in_visual_space(skeleton, bone_index))

	var yaw_180 := Basis(Vector3.UP, PI)
	for locomotion_name in [RUNTIME_WALK, RUNTIME_RUN]:
		if not runtime_animation_player.has_animation(locomotion_name):
			continue
		var locomotion := runtime_animation_player.get_animation(locomotion_name)
		var best_time := 0.0
		var best_position_error := INF
		var best_aligned_position_error := INF
		var best_rotation_error := INF
		var best_translation := Vector3.ZERO
		var best_score := INF
		for sample_index in TURN_PHASE_SAMPLE_COUNT:
			var sample_time := locomotion.length * float(sample_index) / float(TURN_PHASE_SAMPLE_COUNT)
			runtime_animation_player.play(locomotion_name, 0.0)
			runtime_animation_player.seek(sample_time, true, true)
			runtime_animation_player.advance(0.0)
			var position_deltas: Array[Vector3] = []
			var rotation_error := 0.0
			for pose_index in bone_indices.size():
				var locomotion_pose := _bone_pose_in_visual_space(skeleton, bone_indices[pose_index])
				var matched_origin := yaw_180 * locomotion_pose.origin
				var matched_basis := yaw_180 * locomotion_pose.basis
				position_deltas.append(turn_poses[pose_index].origin - matched_origin)
				rotation_error += turn_poses[pose_index].basis.get_rotation_quaternion().angle_to(matched_basis.get_rotation_quaternion())
			var translation := Vector3.ZERO
			for delta_position in position_deltas:
				translation += delta_position
			translation /= float(position_deltas.size())
			var position_error := 0.0
			var aligned_position_error := 0.0
			for delta_position in position_deltas:
				position_error += delta_position.length()
				aligned_position_error += (delta_position - translation).length()
			position_error /= float(position_deltas.size())
			aligned_position_error /= float(position_deltas.size())
			rotation_error /= float(bone_indices.size())
			var score := aligned_position_error + rotation_error * TURN_PHASE_ROTATION_WEIGHT_M
			if score < best_score:
				best_score = score
				best_time = sample_time
				best_position_error = position_error
				best_aligned_position_error = aligned_position_error
				best_rotation_error = rotation_error
				best_translation = translation
		turn_to_locomotion_phase_seconds[locomotion_name] = best_time
		turn_to_locomotion_foot_error_m[locomotion_name] = best_position_error
		turn_to_locomotion_aligned_foot_error_m[locomotion_name] = best_aligned_position_error
		turn_to_locomotion_rotation_error_deg[locomotion_name] = rad_to_deg(best_rotation_error)
		# The correction was measured in the pre-turn CharacterVisual basis. At
		# handoff the outer node has rotated 180 degrees, so express it in that
		# new local basis before applying it to runtime_root.
		var correction_in_new_facing := yaw_180 * best_translation
		turn_to_locomotion_translation[locomotion_name] = correction_in_new_facing
		DebugLog.info("animation", "turn_phase_match animation=%s time=%.3f foot_error=%.4f aligned_error=%.4f correction=%s rotation_error_deg=%.2f" % [locomotion_name, best_time, best_position_error, best_aligned_position_error, correction_in_new_facing, rad_to_deg(best_rotation_error)])
	turn_phase_matches_ready = true

func _bone_pose_in_visual_space(skeleton: Skeleton3D, bone_index: int) -> Transform3D:
	var bone_world := skeleton.global_transform * skeleton.get_bone_global_pose(bone_index)
	return global_transform.affine_inverse() * bone_world

func _update_turn_transition_correction(delta: float) -> void:
	if runtime_root == null or turn_transition_elapsed >= TURN_TRANSITION_CORRECTION_DURATION:
		return
	turn_transition_elapsed = minf(TURN_TRANSITION_CORRECTION_DURATION, turn_transition_elapsed + delta)
	var remaining_weight := 1.0 - turn_transition_elapsed / TURN_TRANSITION_CORRECTION_DURATION
	runtime_root.position = runtime_root_base_position + turn_transition_correction * remaining_weight
	if remaining_weight <= 0.0:
		turn_transition_correction = Vector3.ZERO

func _locomotion_speed_scale(animation_name: String, speed: float) -> float:
	var animation := runtime_animation_player.get_animation(animation_name) if runtime_animation_player != null else null
	var cycle_distance := RUN_CYCLE_DISTANCE_M if animation_name == RUNTIME_RUN else WALK_CYCLE_DISTANCE_M
	if animation != null and animation.has_meta("cycle_distance_m"):
		cycle_distance = float(animation.get_meta("cycle_distance_m"))
	var cycle_reference_speed := cycle_distance / maxf(0.01, animation.length if animation else 1.0)
	return clampf(speed / maxf(0.01, cycle_reference_speed), 0.72, 1.35)

func _update_runtime_animation() -> void:
	if turn_active:
		# start_turn_around() owns this one-shot. Do not restart it when the
		# AnimationPlayer reaches the final frame before PlayerController's timer.
		return
	if jump_active:
		# start/launch/land methods own the three playback rates and markers.
		_ensure_jump_animation_for_stage()
		return
	if airborne:
		if runtime_animation_player.has_animation(RUNTIME_JUMP):
			if runtime_animation != RUNTIME_JUMP:
				runtime_animation_player.speed_scale = 1.0
				_play_runtime_animation(RUNTIME_JUMP, 0.08, "fall")
				runtime_animation_player.seek(jump_takeoff_time, true, true)
			return
	if gesture_clock >= 0.0:
		runtime_animation_player.speed_scale = 1.0
		_play_runtime_animation(_runtime_gesture_animation(), 0.12)
		return
	if motion_speed > 0.25:
		var running := motion_speed > 6.4 and runtime_animation_player.has_animation(RUNTIME_RUN)
		var locomotion_animation := RUNTIME_RUN if running else RUNTIME_WALK
		runtime_animation_player.speed_scale = _locomotion_speed_scale(locomotion_animation, motion_speed)
		_play_runtime_animation(locomotion_animation, 0.16)
	else:
		runtime_animation_player.speed_scale = 1.0
		_play_runtime_animation(RUNTIME_IDLE, 0.18)

func _runtime_gesture_animation() -> String:
	if gesture_kind == "observe":
		return RUNTIME_OBSERVE
	if gesture_kind == "gather":
		return RUNTIME_GATHER
	return "anim_chr_player_gesture_%s" % gesture_kind

func _play_runtime_animation(animation_name: String, blend: float, reason := "locomotion") -> void:
	if runtime_animation_player == null or not runtime_animation_player.has_animation(animation_name):
		return
	if runtime_animation == animation_name and runtime_animation_player.is_playing():
		return
	runtime_animation = animation_name
	runtime_animation_player.play(animation_name, blend)
	_debug_log_animation_transition(animation_name, reason)

func _debug_log_animation_transition(animation_name: String, reason: String) -> void:
	DebugLog.info("animation", "transition=%s reason=%s speed=%.3f motion=%.3f" % [animation_name, reason, runtime_animation_player.speed_scale if runtime_animation_player else 1.0, motion_speed])
	var bridge := _get_debug_bridge()
	if bridge != null and bridge.has_method("record_animation_transition"):
		bridge.record_animation_transition(self, animation_name, reason)

func _debug_log_jump_stage(stage: String) -> void:
	DebugLog.info("animation", "jump_stage=%s animation_time=%.3f speed=%.3f" % [stage, runtime_animation_player.current_animation_position if runtime_animation_player else 0.0, runtime_animation_player.speed_scale if runtime_animation_player else 1.0])

func _get_debug_bridge() -> Node:
	if not is_inside_tree():
		return null
	var tree := get_tree()
	if tree == null or tree.root == null:
		return null
	return tree.root.get_node_or_null("AnimationDebugBridge")

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
	if gesture_kind in ["point", "observe", "gather"] and runtime_animation_player != null:
		var authored_animation := runtime_animation_player.get_animation(_runtime_gesture_animation())
		if authored_animation != null:
			return authored_animation.length
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
