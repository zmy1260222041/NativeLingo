class_name PlayerController
extends CharacterBody3D

signal interaction_prompt_changed(prompt: String)
signal speech_mode_changed(toggle_mode: bool)

const WALK_SPEED := 5.4
const SPRINT_SPEED := 8.2
const ACCELERATION := 18.0
const AIR_ACCELERATION := 5.0
const JUMP_VELOCITY := 7.0
const INTERACTION_DISTANCE := 4.0
const GAMEPAD_LOOK_SPEED := 2.35
const DIRECTION_EPSILON_SQUARED := 0.01
const SMALL_TURN_ANGULAR_SPEED := deg_to_rad(360.0)
const JUMP_BUFFER_SECONDS := 0.2
const DirectionRules := preload("res://scripts/directional_movement.gd")

@onready var camera_pivot: Node3D = $CameraPivot
@onready var camera: Camera3D = $CameraPivot/SpringArm3D/Camera3D

var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var nearby_target: Node3D
var character_visual: CharacterVisual
var previous_target_id := 0
var camera_bob_clock := 0.0
var toggle_to_talk := false
var reduce_motion := false
var debug_frozen := false
var facing_direction_world := Vector3.FORWARD
var turn_target_direction_world := Vector3.FORWARD
var turn_time_remaining := 0.0
var turning_around := false
var requested_move_direction_world := Vector3.ZERO
var turn_requested_direction_world := Vector3.FORWARD
var jump_anticipating := false
var jump_airborne_sequence := false
var jump_has_left_floor := false
var jump_physical_impulse := 0.0
var jump_physical_height := 0.0
var jump_authored_lift := 0.0
var jump_buffer_remaining := 0.0
var gesture_rejection_count := 0

func _ready() -> void:
	add_to_group("player")
	_build_character()
	facing_direction_world = (global_transform.basis * Vector3.FORWARD).normalized()
	_apply_visual_facing()
	SpeechAdapter.recognition_finished.connect(_on_recognition_finished)
	if not OS.has_feature("web"):
		# 浏览器要求在用户手势中申请指针锁定；Web 构建延迟到第一次点击画布。
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _unhandled_input(event: InputEvent) -> void:
	if OS.has_feature("web") and event is InputEventMouseButton and event.pressed \
			and Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		# First click on the canvas becomes the trusted gesture that captures
		# the pointer; requesting it during engine startup throws in Chrome.
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	if event.is_action_pressed("ui_cancel") and SpeechAdapter.is_interaction_active():
		SpeechAdapter.cancel_recording()
		get_viewport().set_input_as_handled()
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * 0.0026)
		camera_pivot.rotation.x = clampf(camera_pivot.rotation.x - event.relative.y * 0.0022, -0.8, 0.45)
	if event.is_action_pressed("reset_prototype"):
		GameState.reset_run()
		GameState.save_game()
		get_tree().reload_current_scene()
	if event.is_action_pressed("interact"):
		_attempt_interaction("action")
	if event.is_action_pressed("gesture"):
		if not _can_trigger_gesture():
			gesture_rejection_count += 1
			DebugLog.info("input", "gesture_rejected count=%d on_floor=%s jump_anticipating=%s jump_airborne=%s jump_stage=%s" % [gesture_rejection_count, is_on_floor(), jump_anticipating, jump_airborne_sequence, character_visual.jump_stage if character_visual != null else "missing"])
			get_viewport().set_input_as_handled()
			return
		SpeechAdapter.cancel_recording()
		_attempt_interaction("gesture")
	if event.is_action_pressed("push_to_talk"):
		if not SpeechAdapter.is_available():
			# 首轮网页内测不包含语音：说话按键被整体忽略。
			get_viewport().set_input_as_handled()
			return
		if toggle_to_talk and SpeechAdapter.is_recording():
			SpeechAdapter.finish_recording()
		else:
			_start_voice_interaction()
	if event.is_action_released("push_to_talk") and not toggle_to_talk:
		SpeechAdapter.finish_recording()

func _physics_process(delta: float) -> void:
	if debug_frozen:
		velocity.x = 0.0
		velocity.z = 0.0
		_apply_visual_facing()
		character_visual.set_motion(0.0, not is_on_floor())
		return
	jump_buffer_remaining = maxf(0.0, jump_buffer_remaining - delta)
	if Input.is_action_just_pressed("jump"):
		jump_buffer_remaining = JUMP_BUFFER_SECONDS
	var look_vector := Input.get_vector("camera_left", "camera_right", "camera_up", "camera_down")
	if look_vector.length_squared() > 0.01:
		rotate_y(-look_vector.x * GAMEPAD_LOOK_SPEED * delta)
		camera_pivot.rotation.x = clampf(camera_pivot.rotation.x - look_vector.y * GAMEPAD_LOOK_SPEED * 0.72 * delta, -0.8, 0.45)
	var input_vector := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var direction := (global_transform.basis * Vector3(input_vector.x, 0.0, input_vector.y)).normalized()
	requested_move_direction_world = direction
	var target_speed := SPRINT_SPEED if Input.is_action_pressed("sprint") else WALK_SPEED
	if turning_around:
		# Commit to the direction that started the one-shot. If input or camera
		# changes mid-clip, evaluate that new intent after the turn completes;
		# changing the target here would make the final authored 180-degree pose
		# snap to an unrelated angle.
		_update_turn_around(delta, direction)
		return
	if jump_anticipating:
		_update_jump_anticipation(delta)
		return
	if direction.length_squared() > DIRECTION_EPSILON_SQUARED:
		if is_on_floor() and is_large_direction_change(facing_direction_world, direction) and character_visual.has_turn_around_animation():
			_begin_turn_around(direction)
			_update_turn_around(delta, direction)
			return
		_steer_facing_toward(direction, delta)
	_apply_visual_facing()
	var accel := ACCELERATION if is_on_floor() else AIR_ACCELERATION
	# The body travels along the facing vector while a small turn is in progress;
	# this prevents the character from skating sideways toward a direction its
	# walk pose has not reached yet.
	var movement_direction := facing_direction_world if direction.length_squared() > DIRECTION_EPSILON_SQUARED else Vector3.ZERO
	velocity.x = move_toward(velocity.x, movement_direction.x * target_speed, accel * delta)
	velocity.z = move_toward(velocity.z, movement_direction.z * target_speed, accel * delta)
	if not is_on_floor():
		velocity.y -= gravity * delta
	elif jump_buffer_remaining > 0.0:
		if _try_start_buffered_jump():
			_update_jump_anticipation(delta)
			return
	if direction.length_squared() > 0.01 and not SpeechAdapter.is_interaction_active():
		GameState.energy = maxf(0.0, GameState.energy - delta * (0.7 if target_speed == SPRINT_SPEED else 0.12))
	move_and_slide()
	_update_jump_landing_state()
	if is_on_floor() and jump_buffer_remaining > 0.0 and not jump_anticipating:
		_try_start_buffered_jump()
	var planar_speed := Vector2(velocity.x, velocity.z).length()
	character_visual.set_motion(planar_speed, not is_on_floor())
	_update_camera_motion(delta, planar_speed, target_speed == SPRINT_SPEED and planar_speed > 1.0)
	_find_nearby_target()

func _update_camera_motion(delta: float, planar_speed: float, sprinting: bool) -> void:
	if reduce_motion:
		camera.fov = lerpf(camera.fov, 68.0, minf(1.0, delta * 8.0))
		camera_pivot.position.y = lerpf(camera_pivot.position.y, 1.35, minf(1.0, delta * 10.0))
		return
	camera.fov = lerpf(camera.fov, 72.0 if sprinting else 68.0, minf(1.0, delta * 5.5))
	camera_bob_clock += delta * lerpf(2.0, 8.0, clampf(planar_speed / SPRINT_SPEED, 0.0, 1.0))
	var bob := sin(camera_bob_clock) * 0.022 * clampf(planar_speed / WALK_SPEED, 0.0, 1.0)
	camera_pivot.position.y = lerpf(camera_pivot.position.y, 1.35 + bob, minf(1.0, delta * 9.0))

func is_large_direction_change(from_direction: Vector3, to_direction: Vector3) -> bool:
	return DirectionRules.is_large_change(from_direction, to_direction)

func _begin_turn_around(target_direction: Vector3) -> void:
	turn_requested_direction_world = target_direction.normalized()
	# The authored one-shot is exactly 180 degrees. For a 150-degree request,
	# finish the authored reversal first and smoothly steer the remaining 30
	# degrees on following frames; otherwise the atomic pose switch would snap.
	turn_target_direction_world = -facing_direction_world.normalized()
	turn_time_remaining = character_visual.start_turn_around()
	if turn_time_remaining <= 0.0:
		facing_direction_world = turn_target_direction_world
		_apply_visual_facing()
		return
	turning_around = true
	velocity.x = 0.0
	velocity.z = 0.0
	DebugLog.info("movement", "turn_180_start requested_angle_deg=%.2f authored_target=%s requested_target=%s" % [rad_to_deg(facing_direction_world.angle_to(turn_requested_direction_world)), turn_target_direction_world, turn_requested_direction_world])

func _update_turn_around(delta: float, current_direction: Vector3) -> void:
	velocity.x = 0.0
	velocity.z = 0.0
	if not is_on_floor():
		velocity.y -= gravity * delta
	move_and_slide()
	turn_time_remaining -= delta
	_apply_visual_facing()
	character_visual.set_motion(0.0, not is_on_floor())
	_update_camera_motion(delta, 0.0, false)
	_find_nearby_target()
	if turn_time_remaining <= 0.0:
		turning_around = false
		turn_time_remaining = 0.0
		facing_direction_world = turn_target_direction_world.normalized()
		_apply_visual_facing()
		# Always leave Turn 180 through the phase-matched Walk cycle. Sprint can
		# blend to Run after acceleration; the authored Run has no close-enough
		# contact phase at the turn endpoint.
		var resume_speed := WALK_SPEED if current_direction.length_squared() > DIRECTION_EPSILON_SQUARED and current_direction.dot(turn_requested_direction_world) > 0.7 else 0.0
		character_visual.finish_turn_around(resume_speed)
		DebugLog.info("movement", "turn_180_complete facing=%s resume_speed=%.3f phase=%s" % [facing_direction_world, resume_speed, character_visual.turn_to_locomotion_phase_seconds])

func _steer_facing_toward(target_direction: Vector3, delta: float) -> void:
	var previous_facing := facing_direction_world
	facing_direction_world = DirectionRules.rotate_toward_planar(facing_direction_world, target_direction, SMALL_TURN_ANGULAR_SPEED * delta)
	# Preserve momentum in the character's local forward direction while its yaw
	# changes, rather than leaving velocity on the old heading for one frame.
	var applied_angle := DirectionRules.signed_planar_angle(previous_facing, facing_direction_world)
	var planar_velocity := Vector3(velocity.x, 0.0, velocity.z)
	if planar_velocity.length_squared() > 0.0001:
		planar_velocity = planar_velocity.rotated(Vector3.UP, applied_angle)
		velocity.x = planar_velocity.x
		velocity.z = planar_velocity.z

func _update_jump_anticipation(delta: float) -> void:
	# The source action is a standing jump. Brake during the planted crouch so
	# the feet do not slide, but only launch when the measured foot marker fires.
	velocity.x = move_toward(velocity.x, 0.0, ACCELERATION * 1.5 * delta)
	velocity.z = move_toward(velocity.z, 0.0, ACCELERATION * 1.5 * delta)
	velocity.y = 0.0 if is_on_floor() else velocity.y - gravity * delta
	if character_visual.is_jump_takeoff_due():
		jump_authored_lift = character_visual.get_jump_authored_airborne_lift_m()
		var desired_total_height := JUMP_VELOCITY * JUMP_VELOCITY / (2.0 * maxf(0.01, gravity))
		jump_physical_height = maxf(0.25, desired_total_height - jump_authored_lift)
		jump_physical_impulse = sqrt(2.0 * maxf(0.01, gravity) * jump_physical_height)
		velocity.y = jump_physical_impulse
		jump_anticipating = false
		jump_airborne_sequence = true
		jump_has_left_floor = false
		character_visual.mark_jump_launched(2.0 * jump_physical_impulse / maxf(0.01, gravity))
		DebugLog.info("movement", "jump_takeoff impulse=%.3f physical_height=%.3f authored_lift=%.3f" % [jump_physical_impulse, jump_physical_height, jump_authored_lift])
	move_and_slide()
	_update_jump_landing_state()
	_apply_visual_facing()
	var planar_speed := Vector2(velocity.x, velocity.z).length()
	character_visual.set_motion(planar_speed, not is_on_floor())
	_update_camera_motion(delta, planar_speed, false)
	_find_nearby_target()

func _try_start_buffered_jump() -> bool:
	if jump_buffer_remaining <= 0.0 or not is_on_floor() or jump_anticipating:
		return false
	jump_buffer_remaining = 0.0
	var previous_chain_count := character_visual.jump_chain_count if character_visual != null else 0
	if character_visual != null and character_visual.start_jump_sequence():
		jump_anticipating = true
		velocity.y = 0.0
		var chained := character_visual.jump_chain_count > previous_chain_count
		DebugLog.info("movement", "jump_sequence_start chained=%s chain_count=%d entry_time=%.3f" % [chained, character_visual.jump_chain_count, character_visual.jump_chain_entry_time if chained else 0.0])
		return true
	# Retain the physics-only fallback for a missing animation asset, but never
	# launch through an already-active visual jump state.
	if character_visual == null or not character_visual.jump_active:
		velocity.y = JUMP_VELOCITY
		DebugLog.info("movement", "jump_sequence_fallback impulse=%.3f" % JUMP_VELOCITY)
	return false

func _update_jump_landing_state() -> void:
	if not jump_airborne_sequence:
		return
	if not is_on_floor():
		jump_has_left_floor = true
	elif jump_has_left_floor:
		jump_airborne_sequence = false
		jump_has_left_floor = false
		character_visual.mark_jump_landed()
		DebugLog.info("movement", "jump_landing")

func _apply_visual_facing() -> void:
	if character_visual == null or facing_direction_world.length_squared() <= DIRECTION_EPSILON_SQUARED:
		return
	# CharacterVisual's authored forward is local -Z. Keep this yaw independent
	# from the CharacterBody3D yaw, which belongs to the third-person camera.
	character_visual.rotation.y = DirectionRules.local_yaw_for_world_direction(global_transform.basis, facing_direction_world)

func interaction_prompt(device := "keyboard", device_id := -1) -> String:
	if not is_instance_valid(nearby_target):
		return ""
	return nearby_target.get_interaction_prompt(device, toggle_to_talk, device_id) if nearby_target.has_method("get_interaction_prompt") else ""

func current_target_name() -> String:
	return nearby_target.display_name if is_instance_valid(nearby_target) else tr("NEARBY_RESIDENT")

func set_speech_toggle_mode(active: bool) -> void:
	toggle_to_talk = active
	speech_mode_changed.emit(toggle_to_talk)
	interaction_prompt_changed.emit(interaction_prompt())

func set_reduce_motion(active: bool) -> void:
	reduce_motion = active
	for candidate in get_tree().get_nodes_in_group("interactable"):
		if candidate.has_method("set_reduce_motion"):
			candidate.set_reduce_motion(active)

func set_debug_frozen(active: bool) -> void:
	debug_frozen = active
	if active:
		velocity.x = 0.0
		velocity.z = 0.0

func get_animation_debug_state() -> Dictionary:
	return {
		"global_position": global_position,
		"velocity": velocity,
		"planar_speed": Vector2(velocity.x, velocity.z).length(),
		"debug_frozen": debug_frozen,
		"facing_direction": facing_direction_world,
		"requested_move_direction": requested_move_direction_world,
		"turn_target_direction": turn_target_direction_world,
		"turn_requested_direction": turn_requested_direction_world,
		"turning_around": turning_around,
		"turn_time_remaining": turn_time_remaining,
		"facing_error_degrees": rad_to_deg(facing_direction_world.angle_to(requested_move_direction_world)) if requested_move_direction_world.length_squared() > DIRECTION_EPSILON_SQUARED else 0.0,
		"jump_anticipating": jump_anticipating,
		"jump_airborne_sequence": jump_airborne_sequence,
		"jump_physical_impulse": jump_physical_impulse,
		"jump_physical_height": jump_physical_height,
		"jump_authored_lift": jump_authored_lift,
		"jump_buffer_remaining": jump_buffer_remaining,
		"gesture_rejection_count": gesture_rejection_count,
		"visual_yaw_degrees": rad_to_deg(character_visual.rotation.y) if character_visual != null else 0.0,
	}

func _can_trigger_gesture() -> bool:
	return is_on_floor() and not jump_anticipating and not jump_airborne_sequence and character_visual != null and character_visual.can_play_reaction()

func _find_nearby_target() -> void:
	var old_target := nearby_target
	nearby_target = null
	var best_distance := INTERACTION_DISTANCE
	for candidate in get_tree().get_nodes_in_group("interactable"):
		if not candidate is Node3D or not candidate.visible:
			continue
		var offset: Vector3 = global_position - candidate.global_position
		var distance := Vector2(offset.x, offset.z).length()
		if distance < best_distance:
			best_distance = distance
			nearby_target = candidate
	var current_target_id := nearby_target.get_instance_id() if is_instance_valid(nearby_target) else 0
	if current_target_id != previous_target_id:
		if SpeechAdapter.is_interaction_active():
			SpeechAdapter.cancel_recording()
		if is_instance_valid(old_target) and old_target.has_method("set_highlighted"):
			old_target.set_highlighted(false)
		if is_instance_valid(nearby_target) and nearby_target.has_method("set_highlighted"):
			nearby_target.set_highlighted(true)
		previous_target_id = current_target_id
		interaction_prompt_changed.emit(interaction_prompt())

func _attempt_interaction(communication: String) -> void:
	if is_instance_valid(nearby_target) and nearby_target.has_method("interact"):
		if communication == "gesture":
			character_visual.play_reaction("point")
		elif nearby_target.interaction_kind == "npc":
			character_visual.play_reaction("offer" if nearby_target.target_id == "rowan" and GameState.water > 0 else "greet")
		else:
			character_visual.play_environment_interaction(String(nearby_target.interaction_kind))
		nearby_target.interact(communication)
	elif communication == "gesture":
		# No target nearby: still play the user-authored pointing gesture so the
		# player can see/demo the gesture animation standalone.
		character_visual.play_reaction("point")

func _start_voice_interaction() -> void:
	if not SpeechAdapter.is_available():
		return
	if not is_instance_valid(nearby_target) or nearby_target.interaction_kind != "npc":
		GameState.message_requested.emit(tr("MSG_NEAR_NPC_TO_SPEAK"), "neutral")
		return
	if not SpeechAdapter.start_recording(nearby_target.target_id):
		if not SpeechAdapter.is_interaction_active():
			GameState.message_requested.emit(tr("MSG_SPEECH_BUSY"), "neutral")

func _on_recognition_finished(target_id: String, accepted: bool, transcript: String, reason: String) -> void:
	if not accepted:
		for candidate in get_tree().get_nodes_in_group("interactable"):
			if candidate.target_id == target_id and candidate.interaction_kind == "npc":
				var candidate_visual := candidate.get_node_or_null("CharacterVisual") as CharacterVisual
				if candidate_visual:
					candidate_visual.play_reaction("clarify")
				break
		return
	for candidate in get_tree().get_nodes_in_group("interactable"):
		if candidate.target_id == target_id and candidate.interaction_kind == "npc":
			character_visual.play_reaction("offer" if target_id == "rowan" and GameState.water > 0 else "greet")
			candidate.interact("voice")
			return

func _build_character() -> void:
	character_visual = CharacterVisual.new()
	character_visual.name = "CharacterVisual"
	add_child(character_visual)
	character_visual.configure(Color("bfa982"), Color("5a3f58"), 0, true)
