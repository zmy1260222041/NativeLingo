extends SceneTree
## Regression coverage for movement-facing, large-angle turns, and jump timing.

const TURN := "anim_chr_player_turn_180"
const JUMP := "anim_chr_player_jump"
const DirectionRules := preload("res://scripts/directional_movement.gd")

func _init() -> void:
	var failures: Array[String] = []
	_test_direction_threshold(failures)

	var visual := CharacterVisual.new()
	root.add_child(visual)
	visual.configure(Color("bfa982"), Color("5a3f58"), 0, true)
	for _i in 6:
		await process_frame
	var ap := _find(visual, "AnimationPlayer") as AnimationPlayer
	var skeleton := _find(visual, "Skeleton3D") as Skeleton3D
	if ap == null or skeleton == null:
		failures.append("runtime player animation nodes are missing")
	else:
		await _test_turn_action(visual, ap, skeleton, failures)
		_test_jump_action(visual, ap, skeleton, failures)

	if failures.is_empty():
		print("PASS: turns are continuous; jump uses contact markers, chain-pose blending, input locking")
		quit(0)
	else:
		print("FAIL: ", failures)
		quit(1)

func _test_direction_threshold(failures: Array[String]) -> void:
	var forward := Vector3.FORWARD
	var back := Vector3.BACK
	var left := Vector3.LEFT
	var right := Vector3.RIGHT
	if not DirectionRules.is_large_change(forward, back):
		failures.append("front-to-back reversal did not request Turn 180")
	if not DirectionRules.is_large_change(back, forward):
		failures.append("back-to-front reversal did not request Turn 180")
	if not DirectionRules.is_large_change(left, right):
		failures.append("left-to-right reversal did not request Turn 180")
	if not DirectionRules.is_large_change(right, left):
		failures.append("right-to-left reversal did not request Turn 180")
	if DirectionRules.is_large_change(forward, left):
		failures.append("90-degree change incorrectly requested Turn 180")
	var smooth_step := DirectionRules.rotate_toward_planar(forward, right, deg_to_rad(12.0))
	var smooth_step_degrees := rad_to_deg(forward.angle_to(smooth_step))
	if absf(smooth_step_degrees - 12.0) > 0.1:
		failures.append("small turn did not advance by a bounded 12-degree step")
	if smooth_step.angle_to(right) >= forward.angle_to(right):
		failures.append("small turn did not continuously approach its target")
	var angle_120 := Vector3.FORWARD.rotated(Vector3.UP, deg_to_rad(120.0))
	if DirectionRules.is_large_change(forward, angle_120):
		failures.append("120-degree change should rotate directly")
	var angle_150 := Vector3.FORWARD.rotated(Vector3.UP, deg_to_rad(150.0))
	if not DirectionRules.is_large_change(forward, angle_150):
		failures.append("150-degree change should request Turn 180")
	var identity := Basis.IDENTITY
	if absf(rad_to_deg(DirectionRules.local_yaw_for_world_direction(identity, Vector3.RIGHT)) + 90.0) > 0.01:
		failures.append("rightward movement does not rotate the visual toward +X")
	if absf(rad_to_deg(DirectionRules.local_yaw_for_world_direction(identity, Vector3.LEFT)) - 90.0) > 0.01:
		failures.append("leftward movement does not rotate the visual toward -X")

func _test_turn_action(visual: CharacterVisual, ap: AnimationPlayer, skeleton: Skeleton3D, failures: Array[String]) -> void:
	if not ap.has_animation(TURN):
		failures.append("Turn 180 action is missing")
		return
	var duration := visual.start_turn_around()
	if duration <= 0.0 or not visual.turn_active:
		failures.append("Turn 180 one-shot did not start")
		return
	var hips_index := skeleton.find_bone("Hips")
	ap.seek(0.0, true)
	await process_frame
	var start_rotation := skeleton.get_bone_global_pose(hips_index).basis.get_rotation_quaternion()
	ap.seek(duration, true)
	await process_frame
	var end_rotation := skeleton.get_bone_global_pose(hips_index).basis.get_rotation_quaternion()
	var relative := (start_rotation.inverse() * end_rotation).normalized()
	var turn_degrees := rad_to_deg(relative.get_angle())
	turn_degrees = minf(turn_degrees, absf(360.0 - turn_degrees))
	# The authored clip also bends the pelvis, so the full 3D quaternion delta
	# is about 167 degrees even though the visible horizontal facing reverses.
	if turn_degrees < 160.0:
		failures.append("Turn action only rotates Hips %.2f degrees" % turn_degrees)
	var foot_names := ["LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]
	var turn_end_positions: Array[Vector3] = []
	for foot_name in foot_names:
		var foot_index := skeleton.find_bone(foot_name)
		turn_end_positions.append(skeleton.to_global(skeleton.get_bone_global_pose(foot_index).origin))
	# PlayerController hands the authored skeleton yaw to CharacterVisual's
	# outer yaw in the same physics frame.
	visual.rotate_y(PI)
	visual.finish_turn_around(5.4)
	if visual.turn_active or visual.runtime_animation != CharacterVisual.RUNTIME_WALK:
		failures.append("held movement did not phase-match directly into Walk")
	var mean_foot_error := 0.0
	for foot_index in foot_names.size():
		var bone_index := skeleton.find_bone(foot_names[foot_index])
		var matched_walk_position := skeleton.to_global(skeleton.get_bone_global_pose(bone_index).origin)
		mean_foot_error += turn_end_positions[foot_index].distance_to(matched_walk_position)
	mean_foot_error /= float(foot_names.size())
	var reported_error := float(visual.turn_to_locomotion_aligned_foot_error_m.get(CharacterVisual.RUNTIME_WALK, INF))
	if mean_foot_error > 0.12 or absf(mean_foot_error - reported_error) > 0.01:
		failures.append("Turn-to-Walk foot phase error is %.4f m (reported %.4f m)" % [mean_foot_error, reported_error])
	await create_timer(CharacterVisual.TURN_TRANSITION_CORRECTION_DURATION + 0.05).timeout
	if visual.turn_transition_correction.length() > 0.0001 or visual.runtime_root.position.distance_to(visual.runtime_root_base_position) > 0.0001:
		failures.append("Turn-to-Walk inertial correction did not decay to zero")

func _test_jump_action(visual: CharacterVisual, ap: AnimationPlayer, skeleton: Skeleton3D, failures: Array[String]) -> void:
	if not ap.has_animation(JUMP):
		failures.append("jump action is missing")
		return
	if not visual.start_jump_sequence():
		failures.append("jump anticipation did not start")
		return
	if visual.jump_stage != "anticipation" or absf(ap.speed_scale - CharacterVisual.JUMP_ANTICIPATION_SPEED) > 0.01:
		failures.append("jump did not begin in authored crouch anticipation")
	if visual.play_reaction("point"):
		failures.append("gesture was allowed during jump anticipation")
	if visual.runtime_animation != JUMP:
		failures.append("rejected anticipation gesture replaced the jump animation")
	ap.seek(visual.jump_takeoff_time, true, true)
	if not visual.is_jump_takeoff_due():
		failures.append("jump takeoff marker did not fire at measured animation time")
	var expected_airtime := 1.4
	visual.mark_jump_launched(expected_airtime)
	var expected_speed := clampf((visual.jump_landing_time - visual.jump_takeoff_time) / expected_airtime, 0.2, 2.0)
	if absf(ap.speed_scale - expected_speed) > 0.01:
		failures.append("authored airborne segment is not aligned to physical airtime")
	if visual.get_jump_authored_airborne_lift_m() <= 0.0:
		failures.append("jump report did not provide authored airborne lift compensation")
	if visual.play_reaction("point"):
		failures.append("gesture was allowed while airborne")
	if visual.runtime_animation != JUMP:
		failures.append("rejected airborne gesture replaced the jump animation")
	visual.set_motion(0.0, true)
	visual.set_motion(0.0, false)
	# Reproduce the former corrupt state directly: a Point clip overwrote Jump
	# while jump_active stayed true. Landing must repair the owned animation.
	ap.play(CharacterVisual.RUNTIME_POINT, 0.0)
	visual.runtime_animation = CharacterVisual.RUNTIME_POINT
	visual.mark_jump_landed()
	if visual.jump_stage != "recovery" or not visual.jump_active:
		failures.append("jump landing did not enter the authored recovery segment")
	if not visual._is_jump_animation(visual.runtime_animation):
		failures.append("landing guard did not restore Jump after a foreign one-shot")

	# Chain at the landing contact. The first evaluated frame must remain at the
	# outgoing recovery pose while the closest anticipation phase blends in.
	ap.seek(visual.jump_landing_time + 0.03, true, true)
	ap.advance(0.0)
	var tracked_bones := ["Hips", "LeftFoot", "RightFoot", "LeftHand", "RightHand"]
	var before_positions: Array[Vector3] = []
	for bone_name in tracked_bones:
		before_positions.append(skeleton.get_bone_global_pose(skeleton.find_bone(bone_name)).origin)
	if not visual.start_jump_sequence():
		failures.append("landing recovery did not accept a chained jump")
		return
	if visual.jump_stage != "anticipation" or visual.jump_chain_count != 1:
		failures.append("chained jump did not enter matched anticipation")
	if visual.runtime_animation != CharacterVisual.RUNTIME_JUMP_CHAIN:
		failures.append("chained jump did not use the alternate blend animation")
	if visual.jump_chain_entry_time < 0.0 or visual.jump_chain_entry_time >= visual.jump_takeoff_time:
		failures.append("chained jump phase match is outside anticipation")
	var max_initial_displacement := 0.0
	for bone_index in tracked_bones.size():
		var after_position := skeleton.get_bone_global_pose(skeleton.find_bone(tracked_bones[bone_index])).origin
		max_initial_displacement = maxf(max_initial_displacement, before_positions[bone_index].distance_to(after_position))
	if max_initial_displacement > 0.02:
		failures.append("chain jump hard-cut %.4f m on its first blended frame" % max_initial_displacement)
	if visual.play_reaction("point"):
		failures.append("gesture was allowed during chained anticipation")
	ap.seek(visual.jump_takeoff_time, true, true)
	if not visual.is_jump_takeoff_due():
		failures.append("alternate chain animation did not fire its takeoff marker")
	visual.mark_jump_launched(expected_airtime)
	visual.mark_jump_landed()
	ap.seek(visual.jump_landing_time + 0.03, true, true)
	if not visual.start_jump_sequence():
		failures.append("a third consecutive jump could not leave alternate recovery")
	elif visual.runtime_animation != JUMP or visual.jump_chain_count != 2:
		failures.append("consecutive chain jumps did not alternate blend animation names")

func _find(node: Node, type_name: String) -> Node:
	if node.is_class(type_name):
		return node
	for child in node.get_children():
		var found := _find(child, type_name)
		if found != null:
			return found
	return null
