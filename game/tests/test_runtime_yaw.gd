extends SceneTree
func _init() -> void:
	var pc = load("res://scripts/player_controller.gd").new()
	root.add_child(pc)
	await process_frame
	await process_frame
	await process_frame
	await process_frame
	var visual = _find(pc, "CharacterVisual")
	if visual == null:
		print("no CharacterVisual under player"); quit(1); return
	var sk = _find(visual, "Skeleton3D") as Skeleton3D
	var ap = _find(visual, "AnimationPlayer") as AnimationPlayer
	if sk == null or ap == null:
		print("no skel/AP"); quit(1); return
	var idx := {}
	for i in sk.get_bone_count():
		idx[sk.get_bone_name(i)] = i
	if not ap.has_animation("anim_chr_player_walk_forward"):
		print("walk anim missing; have: ", ap.get_animation_list()); quit(1); return
	ap.play("anim_chr_player_walk_forward")
	var samples := []
	for f in 31:
		await process_frame
		if f % 5 == 0:
			var hq: Quaternion = sk.get_bone_global_pose(idx["Head"]).basis.get_rotation_quaternion()
			var pq: Quaternion = sk.get_bone_global_pose(idx["Hips"]).basis.get_rotation_quaternion()
			samples.append(snapped(rad_to_deg((pq.inverse() * hq).get_euler().y), 1))
	print("RUNTIME walk Head-vs-Hips yaw (deg): ", samples)
	quit(0)
func _find(n, t):
	if n.is_class(t): return n
	for c in n.get_children():
		var r = _find(c, t)
		if r: return r
	return null
