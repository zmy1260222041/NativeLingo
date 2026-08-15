extends SceneTree
## Runtime smoke test for the user-authored Mixamo action overlay.
##
## Retargeting quality is measured offline by
## ``blender/retarget_mixamo_actions.py``. This Godot test verifies that the
## selected actions survive FBX import, have the expected loop semantics, and
## remain in-place so PlayerController owns world movement.

const REQUIRED := [
	"anim_chr_player_idle_neutral",
	"anim_chr_player_walk_forward",
	"anim_chr_player_run_forward",
	"anim_chr_player_gesture_point",
	"anim_chr_player_interact_observe",
	"anim_chr_player_interact_gather",
	"anim_chr_player_turn_180",
	"anim_chr_player_jump",
]
const RETARGET_REPORT := "res://assets/characters/chr_player_juvenile_mixamo_retarget.json"
const PROBE_PHASES := [0.0, 0.25, 0.5, 0.75]

func _init() -> void:
	var visual := CharacterVisual.new()
	root.add_child(visual)
	visual.configure(Color("bfa982"), Color("5a3f58"), 0, true)
	for _i in 6:
		await process_frame

	var ap := _find(visual, "AnimationPlayer") as AnimationPlayer
	if ap == null:
		print("FAIL: no AnimationPlayer under CharacterVisual")
		quit(1)
		return

	var failures: Array[String] = []
	if not FileAccess.file_exists(RETARGET_REPORT):
		failures.append("retarget fidelity report missing")
	else:
		var report = JSON.parse_string(FileAccess.get_file_as_string(RETARGET_REPORT))
		if not report is Dictionary:
			failures.append("retarget fidelity report is invalid JSON")
		else:
			var actions: Dictionary = report.get("actions", {})
			for name in REQUIRED:
				var action_report: Dictionary = actions.get(name, {})
				if action_report.get("selected_algorithm", "") != "pose_direction":
					failures.append("%s did not select pose_direction" % name)
				var candidates: Dictionary = action_report.get("candidates", {})
				var selected: Dictionary = candidates.get("pose_direction", {})
				var metrics: Dictionary = selected.get("metrics", {})
				if float(metrics.get("direction_p95_deg", 999.0)) > 0.5:
					failures.append("%s source pose direction error exceeds 0.5 degrees" % name)
				if float(metrics.get("endpoint_max_m", 999.0)) > 0.005:
					failures.append("%s endpoint error exceeds 5 mm" % name)
			var jump_report: Dictionary = actions.get("anim_chr_player_jump", {})
			var jump_markers: Dictionary = jump_report.get("motion_markers", {})
			var takeoff_frame := int(jump_markers.get("takeoff_frame", -1))
			var landing_frame := int(jump_markers.get("landing_frame", -1))
			if takeoff_frame != 40 or landing_frame != 59:
				failures.append("jump foot contacts changed: expected takeoff 40 / landing 59, got %d / %d" % [takeoff_frame, landing_frame])
			if float(jump_markers.get("authored_airborne_lift_m", 0.0)) <= 0.0:
				failures.append("jump report is missing positive authored airborne lift")
	for name in REQUIRED:
		if not ap.has_animation(name):
			failures.append("missing %s" % name)
		else:
			var animation := ap.get_animation(name)
			var has_dynamic_hips_position := false
			for track_index in animation.get_track_count():
				var track_type := animation.track_get_type(track_index)
				if track_type == Animation.TYPE_SCALE_3D:
					failures.append("%s contains a scale track" % name)
				if track_type == Animation.TYPE_POSITION_3D:
					var path: NodePath = animation.track_get_path(track_index)
					var subname: String = path.get_subname(path.get_subname_count() - 1) if path.get_subname_count() > 0 else ""
					if subname != "Hips":
						failures.append("%s contains a non-Hips position track: %s" % [name, path])
					else:
						var first := animation.track_get_key_value(track_index, 0) as Vector3
						var max_offset := 0.0
						for key_index in animation.track_get_key_count(track_index):
							max_offset = maxf(max_offset, (animation.track_get_key_value(track_index, key_index) as Vector3).distance_to(first))
						has_dynamic_hips_position = max_offset > 0.001
			if name in ["anim_chr_player_idle_neutral", "anim_chr_player_walk_forward", "anim_chr_player_run_forward", "anim_chr_player_interact_observe", "anim_chr_player_interact_gather", "anim_chr_player_turn_180", "anim_chr_player_jump"] and not has_dynamic_hips_position:
				failures.append("%s lost dynamic Hips position" % name)
	var idle := ap.get_animation("anim_chr_player_idle_neutral")
	var walk := ap.get_animation("anim_chr_player_walk_forward")
	var run := ap.get_animation("anim_chr_player_run_forward")
	var point := ap.get_animation("anim_chr_player_gesture_point")
	var observe := ap.get_animation("anim_chr_player_interact_observe")
	var gather := ap.get_animation("anim_chr_player_interact_gather")
	var turn := ap.get_animation("anim_chr_player_turn_180")
	var jump := ap.get_animation("anim_chr_player_jump")
	if idle == null or idle.loop_mode == Animation.LOOP_NONE:
		failures.append("standing idle is not looping")
	if walk == null or walk.loop_mode == Animation.LOOP_NONE:
		failures.append("walk is not looping")
	if run == null or run.loop_mode == Animation.LOOP_NONE:
		failures.append("run is not looping")
	if point != null and point.loop_mode != Animation.LOOP_NONE:
		failures.append("pointing gesture should be non-looping")
	if observe != null and observe.loop_mode != Animation.LOOP_NONE:
		failures.append("observe interaction should be non-looping")
	if gather != null and gather.loop_mode != Animation.LOOP_NONE:
		failures.append("gather interaction should be non-looping")
	if turn != null and turn.loop_mode != Animation.LOOP_NONE:
		failures.append("180 turn should be non-looping")
	if jump != null and jump.loop_mode != Animation.LOOP_NONE:
		failures.append("jump should be non-looping")
	if walk != null and walk.length <= 0.0:
		failures.append("walk has no duration")
	if run != null and run.length <= 0.0:
		failures.append("run has no duration")

	var armature := visual.get_node_or_null("OrganicPlayerModel/Armature") as Node3D
	if armature == null:
		failures.append("runtime armature missing")
	else:
		for action_name in REQUIRED:
			ap.play(action_name)
			await process_frame
			if armature.scale.distance_to(Vector3.ONE) > 0.01:
				failures.append("%s changes armature scale to %s" % [action_name, armature.scale])

	var environment_expectations := {
		"berry": "anim_chr_player_interact_gather",
		"scrap": "anim_chr_player_interact_gather",
		"water": "anim_chr_player_interact_gather",
		"heater": "anim_chr_player_interact_observe",
		"shelter": "anim_chr_player_interact_observe",
	}
	for interaction_kind in environment_expectations:
		visual.gesture_clock = -1.0
		if not visual.play_environment_interaction(interaction_kind):
			failures.append("environment interaction rejected: %s" % interaction_kind)
			continue
		var actual_animation := String(visual.get_animation_debug_state().get("animation", ""))
		if actual_animation != environment_expectations[interaction_kind]:
			failures.append("%s maps to %s instead of %s" % [interaction_kind, actual_animation, environment_expectations[interaction_kind]])

	var skeleton := _find(visual, "Skeleton3D") as Skeleton3D
	if skeleton == null or walk == null:
		failures.append("runtime skeleton missing for limb probe")
	else:
		ap.play("anim_chr_player_walk_forward")
		for phase in PROBE_PHASES:
			ap.seek(walk.length * phase, true)
			await process_frame
			var left_hand := _bone_global_position(skeleton, "LeftHand")
			var right_hand := _bone_global_position(skeleton, "RightHand")
			var left_knee := _bone_global_position(skeleton, "LeftLeg")
			var right_knee := _bone_global_position(skeleton, "RightLeg")
			var left_foot := _bone_global_position(skeleton, "LeftFoot")
			var right_foot := _bone_global_position(skeleton, "RightFoot")
			if left_hand.x - right_hand.x < 0.35:
				failures.append("walk phase %.2f folds hands across the body" % phase)
			if left_knee.x - right_knee.x < 0.05:
				failures.append("walk phase %.2f crosses left/right knees" % phase)
			if left_foot.x - right_foot.x < 0.06:
				failures.append("walk phase %.2f crosses left/right feet" % phase)

	if failures.is_empty():
		print("PASS: Mixamo idle/locomotion/interaction/turn/jump actions imported with safe tracks and loop semantics")
		quit(0)
	else:
		print("FAIL: ", failures)
		quit(1)

func _bone_global_position(skeleton: Skeleton3D, bone_name: String) -> Vector3:
	var index := skeleton.find_bone(bone_name)
	return skeleton.get_bone_global_pose(index).origin if index >= 0 else Vector3.ZERO

func _find(node: Node, type_name: String) -> Node:
	if node.is_class(type_name):
		return node
	for child in node.get_children():
		var found := _find(child, type_name)
		if found:
			return found
	return null
