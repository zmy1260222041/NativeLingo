class_name PlayerController
extends CharacterBody3D

const WALK_SPEED := 5.4
const SPRINT_SPEED := 8.2
const ACCELERATION := 18.0
const AIR_ACCELERATION := 5.0
const JUMP_VELOCITY := 7.0
const INTERACTION_DISTANCE := 3.2

@onready var camera_pivot: Node3D = $CameraPivot
@onready var camera: Camera3D = $CameraPivot/SpringArm3D/Camera3D

var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var nearby_target: Node3D

func _ready() -> void:
	add_to_group("player")
	_build_character()
	SpeechAdapter.recognition_finished.connect(_on_recognition_finished)
	SpeechAdapter.recording_state_changed.connect(_on_recording_state_changed)
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * 0.0026)
		camera_pivot.rotation.x = clampf(camera_pivot.rotation.x - event.relative.y * 0.0022, -0.8, 0.45)
	if event.is_action_pressed("pause"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED else Input.MOUSE_MODE_CAPTURED
	if event.is_action_pressed("reset_prototype"):
		GameState.reset_run()
		GameState.save_game()
		get_tree().reload_current_scene()
	if event.is_action_pressed("interact"):
		_attempt_interaction("action")
	if event.is_action_pressed("gesture"):
		_attempt_interaction("gesture")
	if event.is_action_pressed("push_to_talk"):
		_start_voice_interaction()
	if event.is_action_released("push_to_talk"):
		SpeechAdapter.finish_recording()

func _physics_process(delta: float) -> void:
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
	if direction.length_squared() > 0.01:
		GameState.energy = maxf(0.0, GameState.energy - delta * (0.7 if target_speed == SPRINT_SPEED else 0.12))
	move_and_slide()
	_find_nearby_target()

func interaction_prompt() -> String:
	if not is_instance_valid(nearby_target):
		return ""
	return nearby_target.get_interaction_prompt() if nearby_target.has_method("get_interaction_prompt") else ""

func _find_nearby_target() -> void:
	nearby_target = null
	var best_distance := INTERACTION_DISTANCE
	for candidate in get_tree().get_nodes_in_group("interactable"):
		if not candidate is Node3D or not candidate.visible:
			continue
		var distance := global_position.distance_to(candidate.global_position)
		if distance < best_distance:
			best_distance = distance
			nearby_target = candidate

func _attempt_interaction(communication: String) -> void:
	if is_instance_valid(nearby_target) and nearby_target.has_method("interact"):
		nearby_target.interact(communication)

func _start_voice_interaction() -> void:
	if not is_instance_valid(nearby_target) or nearby_target.interaction_kind != "npc":
		GameState.message_requested.emit("靠近一位居民后，按住 V 说英语。", "neutral")
		return
	if not SpeechAdapter.start_recording(nearby_target.target_id):
		GameState.message_requested.emit("麦克风正忙或不可用；按 G 可用手势确认。", "neutral")

func _on_recording_state_changed(active: bool) -> void:
	if active:
		GameState.message_requested.emit("正在听……松开 V 完成。", "neutral")

func _on_recognition_finished(target_id: String, accepted: bool, transcript: String, reason: String) -> void:
	if not accepted:
		var heard := "（听到：%s）" % transcript if not transcript.is_empty() else ""
		GameState.message_requested.emit(reason + heard, "neutral")
		return
	for candidate in get_tree().get_nodes_in_group("interactable"):
		if candidate.target_id == target_id and candidate.interaction_kind == "npc":
			candidate.interact("voice")
			return

func _build_character() -> void:
	var body := MeshInstance3D.new()
	var body_mesh := CapsuleMesh.new()
	body_mesh.radius = 0.44
	body_mesh.height = 1.3
	body.mesh = body_mesh
	body.position.y = 0.05
	body.material_override = _material(Color("6bbbc7"))
	add_child(body)
	var head := MeshInstance3D.new()
	var head_mesh := SphereMesh.new()
	head_mesh.radius = 0.38
	head_mesh.height = 0.76
	head.mesh = head_mesh
	head.position = Vector3(0, 0.78, 0)
	head.scale = Vector3(1.25, 0.85, 1.05)
	head.material_override = _material(Color("84d4d2"))
	add_child(head)
	for side in [-1.0, 1.0]:
		var ear := MeshInstance3D.new()
		var ear_mesh := PrismMesh.new()
		ear_mesh.size = Vector3(0.55, 0.5, 0.12)
		ear.mesh = ear_mesh
		ear.position = Vector3(side * 0.48, 0.88, 0.03)
		ear.rotation.z = side * 0.55
		ear.material_override = _material(Color("4d93a8"))
		add_child(ear)

func _material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.82
	return material
