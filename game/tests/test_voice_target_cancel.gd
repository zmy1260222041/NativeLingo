extends Node

var failures := 0

func _ready() -> void:
	await get_tree().process_frame
	await get_tree().physics_frame
	var player := $Main/Player as PlayerController
	var target := _first_target()
	_expect(target != null, "World exposes an interaction target")
	_test_recording_cancel(player, target)
	_test_pending_cancel(player, target)
	_test_recovery_cancel(player, target)
	if failures == 0:
		print("PASS: Stranger voice target-cancel suite")
	get_tree().quit(failures)

func _test_recording_cancel(player: PlayerController, target: Node3D) -> void:
	var effect := AudioEffectRecord.new()
	SpeechAdapter.record_effect = effect
	SpeechAdapter.recording_session_active = true
	SpeechAdapter.session_generation += 1
	SpeechAdapter.active_generation = SpeechAdapter.session_generation
	SpeechAdapter.active_target_id = target.target_id
	GameState.set_interaction_time_frozen(true)
	_leave_target(player, target)
	_expect(not SpeechAdapter.is_recording() and SpeechAdapter.session_target_id().is_empty() and not GameState.interaction_time_frozen, "Leaving range cancels Listening and unfreezes time")

func _test_pending_cancel(player: PlayerController, target: Node3D) -> void:
	SpeechAdapter.session_generation += 1
	SpeechAdapter.pending_target_id = target.target_id
	SpeechAdapter.request_generation = SpeechAdapter.session_generation
	GameState.set_interaction_time_frozen(true)
	_leave_target(player, target)
	_expect(SpeechAdapter.pending_target_id.is_empty() and SpeechAdapter.session_target_id().is_empty() and not GameState.interaction_time_frozen, "Leaving range cancels Transcribing and invalidates its target")

func _test_recovery_cancel(player: PlayerController, target: Node3D) -> void:
	SpeechAdapter.session_generation += 1
	SpeechAdapter.recovery_active = true
	SpeechAdapter.recovery_target_id = target.target_id
	GameState.set_interaction_time_frozen(true)
	_leave_target(player, target)
	_expect(not SpeechAdapter.is_recovery_active() and SpeechAdapter.session_target_id().is_empty() and not GameState.interaction_time_frozen, "Leaving range cancels recovery and unfreezes time")

func _leave_target(player: PlayerController, target: Node3D) -> void:
	player.nearby_target = target
	player.previous_target_id = target.get_instance_id()
	# Interaction range uses the XZ plane; move out horizontally, not vertically.
	player.position = Vector3(80, 0, 0)
	player._find_nearby_target()

func _first_target() -> Node3D:
	for candidate in get_tree().get_nodes_in_group("interactable"):
		if candidate is Node3D:
			return candidate
	return null

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
