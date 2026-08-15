class_name WalkAnimFix
## Static helpers that repair the cloud walk animation so it plays correctly
## on the runtime player rig (chr_player_juvenile.fbx).
##
## Problem: the walk source FBX is a different cloud generation with a
## different skeleton rest pose. Its rotation keys are baked relative to the
## source rest, so playing them on the model rig twists Hips ~130° and the
## head ~75° off the pelvis (see tools/debug_cli.gd `selftest`).
##
## Fixes (per bone rotation track, key := Quaternion):
##   "centered"  — subtract the walk cycle's own mean rotation:
##                 key' = walk_mean⁻¹ · key
##                 -> cycle swings around the model rest pose.
##   "translate" — retarget keys via global rest poses G_model⁻¹·G_source·key.
##                 Exact pose transfer, but the source skeleton's own rest is
##                 twisted (hips yaw 166° vs the model's 35°), so this only
##                 reproduces the source's (wrong-looking) pose. Diagnostic.
##   "rebase"    — re-center the cycle neutral on the idle pose, the correct
##                 standing reference authored on the model rig:
##                 key' = idle_mean · walk_mean⁻¹ · key
##                 The walk oscillation is preserved as a delta on top of the
##                 idle standing pose. This is the production fix.
## All preserve the walk-cycle oscillation; only the constant offset moves.

static func build_fixed_walk(walk_anim: Animation, idle_anim: Animation, method: String, g_model: Dictionary = {}, g_source: Dictionary = {}) -> Animation:
	## Returns a NEW Animation with rotation tracks re-based. Non-rotation
	## tracks are copied verbatim. `method` is "centered", "translate" or
	## "rebase". g_model/g_source map bone name -> GLOBAL rest rotation
	## quaternion (see global_rest_rotations); only "translate" uses them.
	var fixed := Animation.new()
	fixed.length = walk_anim.length
	fixed.loop_mode = walk_anim.loop_mode
	var idle_means := _track_means(idle_anim)
	for ti in walk_anim.get_track_count():
		var path: NodePath = walk_anim.track_get_path(ti)
		var ttype := walk_anim.track_get_type(ti)
		var nt := fixed.add_track(ttype)
		fixed.track_set_path(nt, path)
		var bone := path.get_subname(path.get_subname_count() - 1) as String
		var walk_mean := Quaternion.IDENTITY
		var idle_mean := Quaternion.IDENTITY
		var gm := Quaternion.IDENTITY
		var gs := Quaternion.IDENTITY
		if ttype == Animation.TYPE_ROTATION_3D:
			walk_mean = _cycle_mean(walk_anim, ti)
			idle_mean = idle_means.get(path, Quaternion.IDENTITY) as Quaternion
			gm = g_model.get(bone, Quaternion.IDENTITY) as Quaternion
			gs = g_source.get(bone, Quaternion.IDENTITY) as Quaternion
		for ki in walk_anim.track_get_key_count(ti):
			var t: float = walk_anim.track_get_key_time(ti, ki)
			var v: Variant = walk_anim.track_get_key_value(ti, ki)
			if ttype == Animation.TYPE_ROTATION_3D:
				var q: Quaternion = v
				match method:
					"centered":
						q = walk_mean.inverse() * q
					"translate":
						q = gm.inverse() * gs * q
					"rebase":
						q = idle_mean * walk_mean.inverse() * q
				v = q
			fixed.track_insert_key(nt, t, v)
	return fixed

static func global_rest_rotations(skeleton: Skeleton3D) -> Dictionary:
	## bone name -> GLOBAL rest rotation quaternion (includes parent chain),
	## used to retarget animation keys between skeletons.
	var out: Dictionary = {}
	for i in skeleton.get_bone_count():
		out[skeleton.get_bone_name(i)] = skeleton.get_bone_global_rest(i).basis.get_rotation_quaternion()
	return out

static func _track_means(anim: Animation) -> Dictionary:
	## Map NodePath -> cycle-mean quaternion for every rotation track.
	var out: Dictionary = {}
	for ti in anim.get_track_count():
		if anim.track_get_type(ti) == Animation.TYPE_ROTATION_3D:
			out[anim.track_get_path(ti)] = _cycle_mean(anim, ti)
	return out

## Spherical average of all keyframe quaternions on a rotation track.
## Aligns each sample to the first key's sign to avoid double-cover cancel.
static func _cycle_mean(anim: Animation, track: int) -> Quaternion:
	var acc := Vector4.ZERO
	var sign_ref := Quaternion.IDENTITY
	var count := anim.track_get_key_count(track)
	if count == 0:
		return Quaternion.IDENTITY
	for ki in count:
		var q: Quaternion = anim.track_get_key_value(track, ki)
		if ki == 0:
			sign_ref = q
		if q.dot(sign_ref) < 0.0:
			q = Quaternion(-q.x, -q.y, -q.z, -q.w)
		acc += Vector4(q.x, q.y, q.z, q.w)
	var m := acc / float(count)
	var len := m.length()
	if len < 0.0001:
		return Quaternion.IDENTITY
	return Quaternion(m.x / len, m.y / len, m.z / len, m.w / len).normalized()
