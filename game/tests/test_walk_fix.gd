extends SceneTree
## Automated test for the walk-animation fix (issue: head yaws ~90° and hips
## ~180° while walking, feet normal).
##
## The walk source FBX is a different cloud generation with a different
## skeleton rest pose; its keys played on the runtime rig twist the torso.
## CharacterVisual._add_walk_from_source re-bases the walk cycle neutral onto
## the idle pose (WalkAnimFix "rebase"). This test plays idle and walk on the
## real CharacterVisual runtime rig, compares their cycle-mean poses, and
## asserts the walk neutral sits near the idle standing pose.
##
## Run: Godot --headless -s res://tests/test_walk_fix.gd

const TORSO := ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"]
const LIMBS := ["LeftArm", "LeftForeArm", "LeftHand", "RightArm", "RightForeArm", "RightHand",
	"LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot"]
const TORSO_LIMIT := 35.0
const LIMB_LIMIT := 40.0
const FRAMES := 100
const EVERY := 4

const DebugLog := preload("res://scripts/debug_log.gd")

func _init() -> void:
	DebugLog.set_file("user://logs/test_walk_fix.log")
	DebugLog.info("test", "start")
	var visual := CharacterVisual.new()
	root.add_child(visual)
	visual.configure(Color("bfa982"), Color("5a3f58"), 0, true)
	for i in 6:
		await process_frame
	var sk := _find(visual, "Skeleton3D") as Skeleton3D
	var ap := _find(visual, "AnimationPlayer") as AnimationPlayer
	if sk == null or ap == null:
		print("FAIL: no skeleton/animplayer under CharacterVisual")
		DebugLog.error("test", "missing skeleton or animation player")
		quit(1)
		return
	if not ap.has_animation("anim_chr_player_idle_neutral"):
		print("FAIL: idle anim missing; have ", ap.get_animation_list())
		quit(1)
		return
	if not ap.has_animation("anim_chr_player_walk_forward"):
		print("FAIL: walk anim missing; have ", ap.get_animation_list())
		quit(1)
		return
	var idle_means := await _pose_means(ap, sk, "anim_chr_player_idle_neutral")
	var walk_means := await _pose_means(ap, sk, "anim_chr_player_walk_forward")
	var torso_mean := _pose_mean_angle(idle_means, walk_means, TORSO)
	var limb_mean := _pose_mean_angle(idle_means, walk_means, LIMBS)
	print("walk fix: torsoMean=%.1f limbMean=%.1f (limits %.0f/%.0f)" % [torso_mean, limb_mean, TORSO_LIMIT, LIMB_LIMIT])
	DebugLog.info("test", "torso=%s limb=%s" % [torso_mean, limb_mean])
	if torso_mean < TORSO_LIMIT and limb_mean < LIMB_LIMIT:
		print("PASS: walk neutral aligns with idle standing pose")
		DebugLog.info("test", "PASS")
		quit(0)
	else:
		print("FAIL: walk neutral drifts from idle pose")
		DebugLog.error("test", "FAIL torso=%s limb=%s" % [torso_mean, limb_mean])
		quit(1)

## Cycle-mean global pose per bone while an animation plays.
func _pose_means(ap: AnimationPlayer, sk: Skeleton3D, anim_name: String) -> Dictionary:
	ap.play(anim_name)
	await process_frame
	var acc: Dictionary = {}
	var sign_ref: Dictionary = {}
	for i in sk.get_bone_count():
		acc[sk.get_bone_name(i)] = Vector4.ZERO
		sign_ref[sk.get_bone_name(i)] = Quaternion.IDENTITY
	var count := 0
	for f in FRAMES:
		await process_frame
		if f % EVERY != 0:
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
	return out

func _pose_mean_angle(idle: Dictionary, other: Dictionary, bones: Array) -> float:
	var sum := 0.0
	var count := 0
	for bone in bones:
		if idle.has(bone) and other.has(bone):
			var a: Quaternion = idle[bone]
			var b: Quaternion = other[bone]
			var rel := a.inverse() * b
			sum += rad_to_deg(2.0 * acos(clampf(absf(rel.w), 0.0, 1.0)))
			count += 1
	return sum / maxf(1.0, float(count))

func _find(n: Node, t: String) -> Node:
	if n.is_class(t):
		return n
	for c in n.get_children():
		var r := _find(c, t)
		if r:
			return r
	return null
