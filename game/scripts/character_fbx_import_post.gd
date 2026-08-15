@tool
extends EditorScenePostImport
## Post-import hook for the runtime player FBX.
##
## The Tencent FBX carries cloud action names like
## "Armature|87863..._remap". Map them to the contract animation names
## (game/tests/test_character_asset.gd) and set loop mode on locomotion.
## The -90°X root rotation Godot applies on FBX import is already correct
## (Z-up → Y-up), so we leave transforms alone.

const IDLE_ACTION_HASH := "87863afffd9fcbef3afb7f04b6005c1d"
const WALK_ACTION_HASH := "32795ddb244644eac67ccfd8b84060c3"
const RUN_ACTION := "anim_chr_player_run_forward"
const POINT_ACTION := "anim_chr_player_gesture_point"
const OBSERVE_ACTION := "anim_chr_player_interact_observe"
const GATHER_ACTION := "anim_chr_player_interact_gather"

const RENAME_MAP := {
	IDLE_ACTION_HASH: "anim_chr_player_idle_neutral",
	WALK_ACTION_HASH: "anim_chr_player_walk_forward",
	RUN_ACTION: RUN_ACTION,
	POINT_ACTION: POINT_ACTION,
	OBSERVE_ACTION: OBSERVE_ACTION,
	GATHER_ACTION: GATHER_ACTION,
}


func _post_import(scene: Node) -> Object:
	var player := _find_first(scene, "AnimationPlayer") as AnimationPlayer
	if player == null:
		return scene
	var lib := player.get_animation_library("") as AnimationLibrary
	if lib == null:
		return scene
	for anim_name in lib.get_animation_list():
		if anim_name == "RESET":
			continue
		var mapped := _map_name(anim_name)
		var anim := lib.get_animation(anim_name)
		if anim == null:
			continue
		if mapped != anim_name:
			lib.remove_animation(anim_name)
			anim.resource_name = mapped
			lib.add_animation(mapped, anim)
		# loop locomotion whether the name needed a rename or was already the
		# contract name (assembly exports contract names, so rename may be a no-op)
		if mapped.ends_with("idle_neutral") or mapped.ends_with("walk_forward") or mapped.ends_with("run_forward"):
			anim.loop_mode = Animation.LOOP_LINEAR
		_strip_transform_tracks(anim)
	return scene


func _strip_transform_tracks(animation: Animation) -> void:
	# Blender's FBX bake can emit an Armature scale track with a value of 100
	# because of centimeter conversion. Remove object-level transforms, but keep
	# Armature/Skeleton3D:Hips position: it is the authored in-place weight shift
	# and vertical bounce that makes the walk read as human.
	for track_index in range(animation.get_track_count() - 1, -1, -1):
		var track_type := animation.track_get_type(track_index)
		if track_type == Animation.TYPE_SCALE_3D:
			animation.remove_track(track_index)
			continue
		if track_type == Animation.TYPE_POSITION_3D:
			var path := animation.track_get_path(track_index)
			if path.get_name_count() <= 1 and not _is_safe_in_place_position(animation, track_index):
				animation.remove_track(track_index)

func _is_safe_in_place_position(animation: Animation, track_index: int) -> bool:
	# Godot's FBX importer can represent root-bone Hips translation as an
	# Armature position track. Keep only small, cyclic motion; discard static
	# object transforms and any accumulated gameplay root motion.
	if animation.track_get_key_count(track_index) < 2:
		return false
	var first := animation.track_get_key_value(track_index, 0) as Vector3
	var last := animation.track_get_key_value(track_index, animation.track_get_key_count(track_index) - 1) as Vector3
	var max_offset := 0.0
	for key_index in animation.track_get_key_count(track_index):
		var value := animation.track_get_key_value(track_index, key_index) as Vector3
		max_offset = maxf(max_offset, value.distance_to(first))
	return max_offset > 0.001 and max_offset < 0.5 and last.distance_to(first) < 0.02


func _map_name(name: String) -> String:
	for hash_key in RENAME_MAP:
		if name.contains(hash_key):
			return RENAME_MAP[hash_key]
	return name


func _find_first(node: Node, type_name: String) -> Node:
	if node.is_class(type_name):
		return node
	for child in node.get_children():
		var found := _find_first(child, type_name)
		if found != null:
			return found
	return null
