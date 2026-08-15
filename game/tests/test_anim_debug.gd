extends SceneTree
func _init() -> void:
	var visual := CharacterVisual.new()
	root.add_child(visual)
	visual.configure(Color("bfa982"), Color("5a3f58"), 0, true)
	await process_frame
	await process_frame
	await process_frame
	await process_frame
	var ap := _find(visual, "AnimationPlayer") as AnimationPlayer
	var anim := ap.get_animation("anim_chr_player_walk_forward")
	print("walk tracks after fix:")
	for ti in anim.get_track_count():
		print("  [", ti, "] type=", anim.track_get_type(ti), " path=", anim.track_get_path(ti), " keys=", anim.track_get_key_count(ti))
	# sample a rotation track value
	for ti in anim.get_track_count():
		if anim.track_get_type(ti) == 1 and anim.track_get_key_count(ti) > 0:
			var v = anim.track_get_key_value(ti, anim.track_get_key_count(ti) / 2)
			print("  rot track sample: ", v)
			break
	# play and sample LeftLeg bone
	var sk := _find(visual, "Skeleton3D") as Skeleton3D
	var leg_i := -1
	for i in sk.get_bone_count():
		if sk.get_bone_name(i) == "LeftLeg": leg_i = i
	ap.play("anim_chr_player_walk_forward")
	await process_frame
	# let it play a few frames then sample
	for f in 5:
		await process_frame
	var p1 := sk.get_bone_pose_rotation(leg_i)
	print("LeftLeg pose after play: ", p1)
	await process_frame
	await process_frame
	await process_frame
	var p2 := sk.get_bone_pose_rotation(leg_i)
	print("LeftLeg pose later: ", p2, " changed=", (p1 - p2).length() > 0.001)
	var probe_bones := ["LeftShoulder", "LeftHand", "RightShoulder", "RightHand",
		"LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot"]
	for phase in [0.0, 0.25, 0.5, 0.75]:
		ap.seek(anim.length * phase, true)
		await process_frame
		var sample := {"phase": phase}
		for bone_name in probe_bones:
			var bone_index := sk.find_bone(bone_name)
			if bone_index >= 0:
				sample[bone_name] = sk.get_bone_global_pose(bone_index).origin
		print("POSE_SAMPLE ", sample)
	quit(0)
func _find(n, t):
	if n.is_class(t): return n
	for c in n.get_children():
		var r = _find(c, t)
		if r: return r
	return null
