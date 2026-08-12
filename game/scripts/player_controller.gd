class_name PlayerController
extends CharacterBody3D

signal interaction_prompt_changed(prompt: String)
signal speech_mode_changed(toggle_mode: bool)

const WALK_SPEED := 5.4
const SPRINT_SPEED := 8.2
const ACCELERATION := 18.0
const AIR_ACCELERATION := 5.0
const JUMP_VELOCITY := 7.0
const INTERACTION_DISTANCE := 3.2
const GAMEPAD_LOOK_SPEED := 2.35

@onready var camera_pivot: Node3D = $CameraPivot
@onready var camera: Camera3D = $CameraPivot/SpringArm3D/Camera3D

var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var nearby_target: Node3D
var character_visual: CharacterVisual
var previous_target_id := 0
var camera_bob_clock := 0.0
var toggle_to_talk := false
var reduce_motion := false

func _ready() -> void:
	add_to_group("player")
	_build_character()
	SpeechAdapter.recognition_finished.connect(_on_recognition_finished)
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _unhandled_input(event: InputEvent) -> void:
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
		SpeechAdapter.cancel_recording()
		_attempt_interaction("gesture")
	if event.is_action_pressed("push_to_talk"):
		if toggle_to_talk and SpeechAdapter.is_recording():
			SpeechAdapter.finish_recording()
		else:
			_start_voice_interaction()
	if event.is_action_released("push_to_talk") and not toggle_to_talk:
		SpeechAdapter.finish_recording()

func _physics_process(delta: float) -> void:
	var look_vector := Input.get_vector("camera_left", "camera_right", "camera_up", "camera_down")
	if look_vector.length_squared() > 0.01:
		rotate_y(-look_vector.x * GAMEPAD_LOOK_SPEED * delta)
		camera_pivot.rotation.x = clampf(camera_pivot.rotation.x - look_vector.y * GAMEPAD_LOOK_SPEED * 0.72 * delta, -0.8, 0.45)
	var input_vector := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var direction := (transform.basis * Vector3(input_vector.x, 0.0, input_vector.y)).normalized()
	var target_speed := SPRINT_SPEED if Input.is_action_pressed("sprint") else WALK_SPEED
	var accel := ACCELERATION if is_on_floor() else AIR_ACCELERATION
	velocity.x = move_toward(velocity.x, direction.x * target_speed, accel * delta)
	velocity.z = move_toward(velocity.z, direction.z * target_speed, accel * delta)
	if not is_on_floor():
		velocity.y -= gravity * delta
	elif Input.is_action_just_pressed("jump"):
		velocity.y = JUMP_VELOCITY
	if direction.length_squared() > 0.01 and not SpeechAdapter.is_interaction_active():
		GameState.energy = maxf(0.0, GameState.energy - delta * (0.7 if target_speed == SPRINT_SPEED else 0.12))
	move_and_slide()
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

func _find_nearby_target() -> void:
	var old_target := nearby_target
	nearby_target = null
	var best_distance := INTERACTION_DISTANCE
	for candidate in get_tree().get_nodes_in_group("interactable"):
		if not candidate is Node3D or not candidate.visible:
			continue
		var distance := global_position.distance_to(candidate.global_position)
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
		var reaction := "offer" if nearby_target.target_id == "rowan" and GameState.water > 0 else "greet"
		character_visual.play_reaction(reaction)
		nearby_target.interact(communication)

func _start_voice_interaction() -> void:
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
	character_visual.configure(Color("bfa982"), Color("5a3f58"), 0, true)
	add_child(character_visual)
