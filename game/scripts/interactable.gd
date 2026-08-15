class_name WorldInteractable
extends Node3D

@export var interaction_kind := ""
@export var target_id := ""
@export var display_name := ""
@export var one_shot := false

var base_height := 0.0
var animation_phase := 0.0
var highlighted := false
var reduce_motion := false
var marker: Node3D
var marker_tween: Tween

func _ready() -> void:
	base_height = position.y
	animation_phase = float(abs(target_id.hash()) % 100) * 0.17
	if one_shot and GameState.completed_steps.has(target_id):
		visible = false
		return
	add_to_group("interactable")
	_build_marker()

func _process(delta: float) -> void:
	animation_phase += delta
	if one_shot:
		position.y = base_height + (sin(animation_phase * 1.8) * 0.02 if highlighted and not reduce_motion else 0.0)
	if interaction_kind == "npc":
		var player := get_tree().get_first_node_in_group("player") as Node3D
		if player and global_position.distance_to(player.global_position) < 5.0:
			var direction := player.global_position - global_position
			var target_angle := atan2(-direction.x, -direction.z)
			rotation.y = lerp_angle(rotation.y, target_angle, minf(1.0, delta * 2.4))

func set_reduce_motion(active: bool) -> void:
	reduce_motion = active
	if reduce_motion and marker_tween and marker_tween.is_valid():
		marker_tween.kill()
	if marker:
		marker.scale = Vector3.ONE

func set_highlighted(active: bool) -> void:
	highlighted = active
	if marker:
		marker.visible = active
		if active and not reduce_motion:
			if marker_tween and marker_tween.is_valid():
				marker_tween.kill()
			marker.scale = Vector3.ONE * 0.86
			marker_tween = create_tween()
			marker_tween.tween_property(marker, "scale", Vector3.ONE, 0.16).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)

func _build_marker() -> void:
	marker = Node3D.new()
	marker.name = "InteractionArc"
	marker.position.y = -0.92 if interaction_kind == "npc" else -0.38
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("78c9a4")
	material.emission_enabled = true
	material.emission = Color("78c9a4")
	material.emission_energy_multiplier = 0.36
	var radius := 0.56 if interaction_kind == "npc" else 0.38
	for index in range(9):
		var angle := deg_to_rad(-135.0 + float(index) * 33.75)
		var arc_segment := MeshInstance3D.new()
		arc_segment.name = "ArcSegment%02d" % index
		var segment_mesh := BoxMesh.new()
		segment_mesh.size = Vector3(radius * 0.42, 0.025, 0.055)
		arc_segment.mesh = segment_mesh
		arc_segment.position = Vector3(cos(angle) * radius, 0, sin(angle) * radius)
		arc_segment.rotation.y = -angle
		arc_segment.material_override = material
		marker.add_child(arc_segment)
	marker.visible = false
	add_child(marker)

func get_interaction_prompt(device := "keyboard", speech_toggle_mode := false, device_id := -1) -> String:
	var gamepad := device == "gamepad"
	var interact_glyph := InputGlyphs.for_action("interact", gamepad, device_id)
	if interaction_kind == "npc":
		var gesture_glyph := InputGlyphs.for_action("gesture", gamepad, device_id)
		if not SpeechAdapter.is_available():
			return (tr("PROMPT_NPC_NO_VOICE") % [display_name, gesture_glyph, interact_glyph]).replace("\\n", "\n")
		var talk_glyph := InputGlyphs.for_action("push_to_talk", gamepad, device_id)
		var talk_verb := tr("PROMPT_TALK_TOGGLE") if speech_toggle_mode else tr("PROMPT_TALK_HOLD")
		return (tr("PROMPT_NPC") % [display_name, talk_glyph, talk_verb, gesture_glyph, interact_glyph]).replace("\\n", "\n")
	return tr("PROMPT_OBJECT") % [display_name, interact_glyph]

func interact(communication: String) -> void:
	if interaction_kind != "npc" and communication != "action":
		return
	var actor_visual := get_node_or_null("CharacterVisual") as CharacterVisual
	if actor_visual:
		var reaction := "offer" if target_id == "rowan" and GameState.water > 0 else ("greet" if communication in ["voice", "gesture"] else "clarify")
		actor_visual.play_reaction(reaction)
	GameState.interact(interaction_kind, target_id, communication)
	if one_shot:
		visible = false
		remove_from_group("interactable")
