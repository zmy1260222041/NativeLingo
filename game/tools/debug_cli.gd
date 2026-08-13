extends SceneTree
## CLI debug interface for the runtime character pipeline.
##
## Usage (from the game/ directory):
##   /Applications/Godot-4.6.app/Contents/MacOS/Godot --headless \
##       -s res://tools/debug_cli.gd -- <command> [args...]
##
## Commands:
##   rest [fbx]                Print bone rest rotations (default: model FBX)
##   anim [fbx]                Print animation track/keyframe summary
##   keys <bone> [fbx] [--method=raw|centered|rebase]
##                             Print rotation keyframes (time, deg) for a bone
##   probe [--method=raw|centered|rebase] [--frames=N] [--every=M]
##                             Play walk on the model rig and sample
##                             Hips/Head/Foot yaw per frame
##   compare [--frames=N] [--every=M]
##                             Compare idle vs walk (all methods): per-bone
##                             cycle-mean pose angle against the idle pose
##   selftest                  Evaluate all fix methods + raw, print metrics
##   help                      This help
##
## Every command also writes a log via DebugLog (user://logs/debug_cli.log).

const MODEL_FBX := "res://assets/characters/chr_player_juvenile_mixamo.fbx"
const WALK_FBX := "res://assets/characters/chr_player_walk_source.fbx"

const DebugLog := preload("res://scripts/debug_log.gd")
const WalkAnimFix := preload("res://scripts/walk_anim_fix.gd")

func _init() -> void:
	DebugLog.set_file("user://logs/debug_cli.log")
	DebugLog.set_mirror_stdout(false)
	var args := OS.get_cmdline_user_args()
	var cmd := "help"
	var rest := PackedStringArray()
	if args.size() > 0:
		cmd = args[0]
		rest = args.slice(1)
	match cmd:
		"rest":
			_cmd_rest(_fbx_arg(rest, 0))
		"anim":
			_cmd_anim(_fbx_arg(rest, 0))
		"keys":
			_cmd_keys(rest)
		"probe":
			await _cmd_probe(rest)
		"compare":
			await _cmd_compare(rest)
		"selftest":
			await _cmd_selftest()
		_:
			_help()
	quit(0)

func _fbx_arg(args: PackedStringArray, index: int) -> String:
	if index < args.size() and not args[index].begins_with("--"):
		return args[index]
	return MODEL_FBX

## ---- commands ------------------------------------------------------------

func _cmd_rest(fbx: String) -> void:
	DebugLog.info("cli", "rest %s" % fbx)
	var inst := _instantiate(fbx)
	if inst == null:
		return
	var sk := _find(inst, "Skeleton3D") as Skeleton3D
	if sk == null:
		print("no Skeleton3D in ", fbx)
		return
	for i in sk.get_bone_count():
		var rest: Transform3D = sk.get_bone_rest(i)
		var e := _euler_deg(rest.basis.get_rotation_quaternion())
		print("%-16s rest=%s pos=%s" % [sk.get_bone_name(i), e,
			Vector3(snapped(rest.origin.x, 0.001), snapped(rest.origin.y, 0.001), snapped(rest.origin.z, 0.001))])
	inst.free()

func _cmd_anim(fbx: String) -> void:
	DebugLog.info("cli", "anim %s" % fbx)
	var inst := _instantiate(fbx)
	if inst == null:
		return
	var ap := _find(inst, "AnimationPlayer") as AnimationPlayer
	if ap == null:
		print("no AnimationPlayer in ", fbx)
		return
	for anim_name in ap.get_animation_list():
		var anim: Animation = ap.get_animation(anim_name)
		print("== %s (len=%.2fs loop=%d)" % [anim_name, anim.length, anim.loop_mode])
		for ti in anim.get_track_count():
			var path: NodePath = anim.track_get_path(ti)
			var ttype := anim.track_get_type(ti)
			var desc := "rot" if ttype == Animation.TYPE_ROTATION_3D else (
				"pos" if ttype == Animation.TYPE_POSITION_3D else (
				"scale" if ttype == Animation.TYPE_SCALE_3D else "type%d" % ttype))
			print("  [%2d] %-5s %-40s keys=%d" % [ti, desc, path, anim.track_get_key_count(ti)])
	inst.free()

func _cmd_keys(args: PackedStringArray) -> void:
	var bone := args[0] if args.size() > 0 and not args[0].begins_with("--") else "Hips"
	var fbx := _fbx_arg(args, 1)
	var method := "raw"
	for a in args:
		if a.begins_with("--method="):
			method = a.trim_prefix("--method=")
	DebugLog.info("cli", "keys bone=%s fbx=%s method=%s" % [bone, fbx, method])
	var inst := _instantiate(fbx)
	if inst == null:
		return
	var ap := _find(inst, "AnimationPlayer") as AnimationPlayer
	if ap == null:
		print("no AnimationPlayer in ", fbx)
		return
	var anim_name := ap.get_animation_list()[0]
	var anim: Animation = ap.get_animation(anim_name)
	if method != "raw":
		var model_inst := _instantiate(MODEL_FBX)
		var ap_m := _find(model_inst, "AnimationPlayer") as AnimationPlayer
		var sk_m := _find(model_inst, "Skeleton3D") as Skeleton3D
		var sk_w := _find(inst, "Skeleton3D") as Skeleton3D
		var idle_anim: Animation = ap_m.get_animation(ap_m.get_animation_list()[0])
		anim = WalkAnimFix.build_fixed_walk(anim, idle_anim, method,
			WalkAnimFix.global_rest_rotations(sk_m), WalkAnimFix.global_rest_rotations(sk_w))
		model_inst.free()
	print("== %s bone=%s method=%s (len=%.2fs)" % [anim_name, bone, method, anim.length])
	for ti in anim.get_track_count():
		if anim.track_get_type(ti) != Animation.TYPE_ROTATION_3D:
			continue
		var path: NodePath = anim.track_get_path(ti)
		if path.get_subname(path.get_subname_count() - 1) != bone:
			continue
		print("  track [%d] %s keys=%d" % [ti, path, anim.track_get_key_count(ti)])
		var count := anim.track_get_key_count(ti)
		for ki in count:
			if ki != 0 and ki != count / 2 and ki != count - 1:
				continue
			var t: float = anim.track_get_key_time(ti, ki)
			var q: Quaternion = anim.track_get_key_value(ti, ki)
			print("    t=%6.2f  rot=%s" % [t, _euler_deg(q)])
		break
	inst.free()

func _cmd_probe(args: PackedStringArray) -> void:
	var method := "raw"
	var frames := 60
	var every := 4
	for a in args:
		if a.begins_with("--method="):
			method = a.trim_prefix("--method=")
		elif a.begins_with("--frames="):
			frames = a.trim_prefix("--frames=").to_int()
		elif a.begins_with("--every="):
			every = maxi(1, a.trim_prefix("--every=").to_int())
	DebugLog.info("cli", "probe method=%s frames=%d every=%d" % [method, frames, every])
	var samples := await _sample_walk(method, frames, every)
	print("method=%s frames=%d" % [method, frames])
	for s in samples:
		print("  f%3d  hipSpin=%6.1f  headVsHip=%6.1f  lfootVsHip=%6.1f  rfootVsHip=%6.1f" % [
			s.frame, s.hips_spin, s.head_vs_hips, s.lfoot_vs_hip, s.rfoot_vs_hip])
	print("  headVsHip drift: mean=%5.1f  max=%5.1f" % [_mean_abs(samples, "head_vs_hips"), _max_abs(samples, "head_vs_hips")])
	print("  hips spin (max-min): %5.1f" % _drift(samples, "hips_spin"))

func _cmd_compare(args: PackedStringArray) -> void:
	var frames := 100
	var every := 4
	for a in args:
		if a.begins_with("--frames="):
			frames = a.trim_prefix("--frames=").to_int()
		elif a.begins_with("--every="):
			every = maxi(1, a.trim_prefix("--every=").to_int())
	DebugLog.info("cli", "compare frames=%d every=%d" % [frames, every])
	var methods := ["raw", "centered", "translate", "rebase"]
	var bones := ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head",
		"LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
		"RightShoulder", "RightArm", "RightForeArm", "RightHand",
		"LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
		"RightUpLeg", "RightLeg", "RightFoot", "RightToeBase"]
	# cycle-mean global pose per bone for idle, then for each walk method
	var idle_means := await _pose_means("idle", frames, every)
	print("%-13s" % "bone", " | ", "idle", " | ", "raw", " ", "centered", " ", "rebase")
	for bone in bones:
		var row := "%-13s" % bone
		row += "  %6.1f" % 0.0
		for method in methods:
			var means := idle_means
			if method != "idle":
				means = await _pose_means(method, frames, every)
			var angle := 999.0
			if means.has(bone) and idle_means.has(bone):
				angle = _quat_angle(idle_means[bone], means[bone])
			row += "  %8.1f" % angle
		print(row)
	DebugLog.info("cli", "compare done")

## Cycle-mean global pose (per bone) of a playing animation on the model rig.
## method: "idle" (model's own anim) or raw/centered/rebase (walk variants).
func _pose_means(method: String, frames: int, every: int) -> Dictionary:
	var model_inst := _instantiate(MODEL_FBX)
	var walk_inst := _instantiate(WALK_FBX)
	var sk := _find(model_inst, "Skeleton3D") as Skeleton3D
	var ap_m := _find(model_inst, "AnimationPlayer") as AnimationPlayer
	var ap_w := _find(walk_inst, "AnimationPlayer") as AnimationPlayer
	var acc: Dictionary = {}  # bone -> Vector4 accumulator
	var sign_ref: Dictionary = {}  # bone -> first-sample quat for sign align
	for i in sk.get_bone_count():
		acc[sk.get_bone_name(i)] = Vector4.ZERO
		sign_ref[sk.get_bone_name(i)] = Quaternion.IDENTITY
	if method == "idle":
		ap_m.play(ap_m.get_animation_list()[0])
	else:
		var lib: AnimationLibrary = ap_m.get_animation_library("")
		var walk_anim: Animation = ap_w.get_animation(ap_w.get_animation_list()[0])
		if method != "raw":
			var idle_anim: Animation = ap_m.get_animation(ap_m.get_animation_list()[0])
			var sk_w := _find(walk_inst, "Skeleton3D") as Skeleton3D
			walk_anim = WalkAnimFix.build_fixed_walk(walk_anim, idle_anim, method,
				WalkAnimFix.global_rest_rotations(sk), WalkAnimFix.global_rest_rotations(sk_w))
		lib.add_animation("probe_anim", walk_anim)
		ap_m.play("probe_anim")
	await process_frame
	var count := 0
	for f in frames:
		await process_frame
		if f % every != 0:
			continue
		count += 1
		for i in sk.get_bone_count():
			var q: Quaternion = sk.get_bone_global_pose(i).basis.get_rotation_quaternion()
			if count == 1:
				sign_ref[sk.get_bone_name(i)] = q
				acc[sk.get_bone_name(i)] = Vector4(q.x, q.y, q.z, q.w)
			else:
				var v: Vector4 = acc[sk.get_bone_name(i)]
				if q.dot(sign_ref[sk.get_bone_name(i)] as Quaternion) < 0.0:
					q = Quaternion(-q.x, -q.y, -q.z, -q.w)
				acc[sk.get_bone_name(i)] = v + Vector4(q.x, q.y, q.z, q.w)
	var out: Dictionary = {}
	for bone in acc:
		var v: Vector4 = acc[bone] / float(count)
		var len := v.length()
		if len > 0.0001:
			out[bone] = Quaternion(v.x / len, v.y / len, v.z / len, v.w / len).normalized()
	model_inst.free()
	walk_inst.free()
	return out

func _cmd_selftest() -> void:
	DebugLog.info("cli", "selftest start")
	var methods := ["raw", "centered", "translate", "rebase"]
	var frames := 100
	var every := 4
	var torso := ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"]
	var limbs := ["LeftArm", "LeftForeArm", "LeftHand", "RightArm", "RightForeArm", "RightHand",
		"LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot"]
	print("=== walk fix selftest (model=" + MODEL_FBX + ") ===")
	print("%-10s %12s %12s %12s" % ["method", "torsoMean", "limbMean", "verdict"])
	var best_score := INF
	var best_method := ""
	var idle_means := await _pose_means("idle", frames, every)
	for method in methods:
		var means := idle_means
		if method != "idle":
			means = await _pose_means(method, frames, every)
		var torso_mean := _pose_mean_angle(idle_means, means, torso)
		var limb_mean := _pose_mean_angle(idle_means, means, limbs)
		var verdict := "FAIL"
		# the walk cycle neutral must sit near the idle standing pose: torso
		# tightly (head/pelvis alignment), limbs loosely (natural pose delta)
		if torso_mean < 35.0 and limb_mean < 40.0:
			verdict = "PASS"
			var score := torso_mean + limb_mean
			if score < best_score:
				best_score = score
				best_method = method
		print("%-10s %12.1f %12.1f %12s" % [method, torso_mean, limb_mean, verdict])
		DebugLog.info("selftest", "%s torso=%s limb=%s %s" % [method, torso_mean, limb_mean, verdict])
	print("best: ", best_method if best_method != "" else "none")
	DebugLog.info("cli", "selftest done")

func _pose_mean_angle(idle: Dictionary, other: Dictionary, bones: Array) -> float:
	var sum := 0.0
	var count := 0
	for bone in bones:
		if idle.has(bone) and other.has(bone):
			sum += _quat_angle(idle[bone] as Quaternion, other[bone] as Quaternion)
			count += 1
	return sum / maxf(1.0, float(count))

func _help() -> void:
	print("""CLI debug interface for the runtime character pipeline.
Usage: Godot --headless -s res://tools/debug_cli.gd -- <command> [args...]
Commands:
  rest [fbx]                Print bone rest rotations (default: model FBX)
  anim [fbx]                Print animation track/keyframe summary
  probe [--method=raw|centered|rebase] [--frames=N] [--every=M]
                            Play walk on the model rig and sample bone yaw
  selftest                  Evaluate all fix methods + raw, print metrics
  help                      This help""")

## ---- sampling -------------------------------------------------------------

class Sample:
	var frame := 0
	var hips_spin := 0.0      # quaternion angle of Hips vs first sample
	var head_vs_hips := 0.0   # quaternion angle of Head vs Hips (deg)
	var lfoot_vs_hip := 0.0   # quaternion angle of LeftFoot vs Hips (deg)
	var rfoot_vs_hip := 0.0   # quaternion angle of RightFoot vs Hips (deg)

func _sample_walk(method: String, frames: int, every: int) -> Array[Sample]:
	var model_inst := _instantiate(MODEL_FBX)
	var walk_inst := _instantiate(WALK_FBX)
	var sk := _find(model_inst, "Skeleton3D") as Skeleton3D
	var ap_m := _find(model_inst, "AnimationPlayer") as AnimationPlayer
	var ap_w := _find(walk_inst, "AnimationPlayer") as AnimationPlayer
	if sk == null or ap_m == null or ap_w == null:
		DebugLog.error("cli", "missing nodes sk=%s apm=%s apw=%s" % [sk, ap_m, ap_w])
		return []
	var idx := {}
	for i in sk.get_bone_count():
		idx[sk.get_bone_name(i)] = i
	if not idx.has("Hips") or not idx.has("Head") or not idx.has("LeftFoot") or not idx.has("RightFoot"):
		DebugLog.error("cli", "required bones missing")
		return []
	var lib: AnimationLibrary = ap_m.get_animation_library("")
	var walk_anim: Animation = ap_w.get_animation(ap_w.get_animation_list()[0])
	var play_anim: Animation = walk_anim
	if method != "raw":
		var idle_anim: Animation = ap_m.get_animation(ap_m.get_animation_list()[0])
		play_anim = WalkAnimFix.build_fixed_walk(walk_anim, idle_anim, method)
	lib.add_animation("probe_anim", play_anim)
	ap_m.play("probe_anim")
	await process_frame
	var out: Array[Sample] = []
	var first_hip := Quaternion.IDENTITY
	for f in frames:
		await process_frame
		if f % every != 0:
			continue
		var s := Sample.new()
		s.frame = f
		var hp: Quaternion = sk.get_bone_global_pose(idx["Hips"]).basis.get_rotation_quaternion()
		var hd: Quaternion = sk.get_bone_global_pose(idx["Head"]).basis.get_rotation_quaternion()
		var lf: Quaternion = sk.get_bone_global_pose(idx["LeftFoot"]).basis.get_rotation_quaternion()
		var rf: Quaternion = sk.get_bone_global_pose(idx["RightFoot"]).basis.get_rotation_quaternion()
		if out.is_empty():
			first_hip = hp
		s.hips_spin = _quat_angle(first_hip, hp)
		s.head_vs_hips = _quat_angle(hp, hd)
		s.lfoot_vs_hip = _quat_angle(hp, lf)
		s.rfoot_vs_hip = _quat_angle(hp, rf)
		out.append(s)
	model_inst.free()
	walk_inst.free()
	return out

func _mean_abs(samples: Array[Sample], field: String) -> float:
	var sum := 0.0
	for s in samples:
		sum += absf(s.get(field))
	return sum / maxf(1.0, float(samples.size()))

func _quat_angle(a: Quaternion, b: Quaternion) -> float:
	## rotation angle (deg) between two quaternions, coordinate-free.
	## Uses |w| so the result is always the minimal angle in [0, 180].
	var rel := a.inverse() * b
	return rad_to_deg(2.0 * acos(clampf(absf(rel.w), 0.0, 1.0)))

func _max_abs(samples: Array[Sample], field: String) -> float:
	var worst := 0.0
	for s in samples:
		worst = maxf(worst, absf(s.get(field)))
	return worst

func _drift(samples: Array[Sample], field: String) -> float:
	var lo := INF
	var hi := -INF
	for s in samples:
		lo = minf(lo, s.get(field))
		hi = maxf(hi, s.get(field))
	return hi - lo if samples.size() > 0 else 0.0

## ---- helpers --------------------------------------------------------------

func _euler_deg(q: Quaternion) -> Vector3:
	var e := q.get_euler() * 180.0 / PI
	return Vector3(snapped(e.x, 0.1), snapped(e.y, 0.1), snapped(e.z, 0.1))

func _instantiate(fbx: String) -> Node3D:
	if not ResourceLoader.exists(fbx):
		DebugLog.error("cli", "missing resource " + fbx)
		return null
	var packed := load(fbx) as PackedScene
	if packed == null:
		DebugLog.error("cli", "failed to load " + fbx)
		return null
	var inst := packed.instantiate() as Node3D
	if inst == null:
		DebugLog.error("cli", "instantiate failed " + fbx)
		return null
	root.add_child(inst)
	return inst

func _find(n: Node, t: String) -> Node:
	if n.is_class(t):
		return n
	for c in n.get_children():
		var r := _find(c, t)
		if r:
			return r
	return null
