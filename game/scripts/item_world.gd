extends Node3D
## FR-44: disposable projections of the persistent ledger.
const Catalog := preload("res://scripts/item_catalog.gd")
const Interactable := preload("res://scripts/interactable.gd")
const COUNTERS := {"tavi": Vector3(-1.8, 1.13, -1.35), "ori": Vector3(9.4, 0.9, 7.1), "vesh": Vector3(2, 0.9, -7.8)}
var anchors := {}
var refresh_pending := false
var sound: AudioStreamPlayer

func _ready() -> void:
	name = "ItemWorld"
	add_to_group("item_world")
	for service in COUNTERS:
		_add_anchor(service, "item_counter", COUNTERS[service], GameState._item_text("待领取物品", "Counter pickup"))
	for slot in Catalog.HOME_SLOTS:
		var data: Dictionary = Catalog.HOME_SLOTS[slot]
		var p: Array = data.position
		_add_anchor(slot, "item_home", Vector3(p[0], p[1], p[2]), Catalog.label(data.name))
	sound = AudioStreamPlayer.new()
	sound.volume_db = -24.0
	add_child(sound)
	GameState.items_changed.connect(_queue_refresh)
	GameState.item_feedback.connect(_feedback)
	_refresh()

func _add_anchor(id: String, kind: String, at: Vector3, label: String) -> void:
	var anchor := Interactable.new()
	anchor.name = id
	anchor.target_id = id
	anchor.interaction_kind = kind
	anchor.display_name = label
	anchor.position = at
	anchor.set_meta("item_anchor", true)
	add_child(anchor)
	anchors[id] = anchor
	var tray := MeshInstance3D.new()
	tray.name = "Tray"
	var box := BoxMesh.new()
	box.size = Vector3(0.9, 0.055, 0.48) if kind == "item_counter" else Vector3(0.65, 0.12, 0.55)
	tray.mesh = box
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("6b5148")
	material.roughness = 0.9
	tray.material_override = material
	anchor.add_child(tray)
	if id == "home_bed":
		box.size = Vector3(1.1, 0.12, 1.4)
		for x in [-0.44, 0.44]:
			for z in [-0.56, 0.56]:
				_box(anchor, Vector3(0.09, 0.55, 0.09), Vector3(x, -0.32, z), Color("6b5148"))
		_box(anchor, Vector3(0.96, 0.08, 1.25), Vector3(0, 0.06, 0), Color("c8baa3"))
	elif id == "home_storage":
		_box(anchor, Vector3(0.8, 0.6, 0.65), Vector3(0, -0.3, 0), Color("6b5148"))
	elif id == "home_power":
		_box(anchor, Vector3(0.55, 0.7, 0.4), Vector3(0, -0.4, 0), Color("417f80"))
	var content := Node3D.new()
	content.name = "Contents"
	anchor.add_child(content)

func _queue_refresh() -> void:
	if not refresh_pending:
		refresh_pending = true
		call_deferred("_refresh")

func _refresh() -> void:
	refresh_pending = false
	for id in anchors:
		var anchor: Node3D = anchors[id]
		var content: Node3D = anchor.get_node("Contents")
		for child in content.get_children():
			content.remove_child(child)
			child.queue_free()
		var entries: Array = []
		for record in GameState.items.instances.values():
			if record.location == id and record.state in ["counter", "placed", "active", "storage"]:
				entries.append(record)
		anchor.visible = not entries.is_empty() or anchor.interaction_kind == "item_home"
		if anchor.interaction_kind == "item_counter" and not entries.is_empty():
			var first: Dictionary = entries[0]
			var mixed := entries.any(func(record): return record.item_id != first.item_id)
			var label: String = GameState._item_text("待领取物品", "Counter items") if mixed else Catalog.label(GameState.items.definitions[first.item_id].name)
			anchor.display_name = "%s ×%d" % [label, entries.size()]
		for index in range(mini(entries.size(), 3)):
			var record: Dictionary = entries[index]
			var visual := make_visual(str(record.item_id), record.state == "active", bool(record.packed))
			content.add_child(visual)
			visual.position = Vector3((index - (mini(entries.size(), 3) - 1) * 0.5) * 0.27, 0.06, 0)
		if id == "home_heater" and GameState.heater_repaired:
			var indicator := MeshInstance3D.new()
			var mesh := SphereMesh.new()
			mesh.radius = 0.12
			mesh.height = 0.24
			indicator.mesh = mesh
			indicator.position.y = 0.18
			var mat := StandardMaterial3D.new()
			mat.albedo_color = Color("e3aa63")
			mat.emission_enabled = true
			mat.emission = Color("e3aa63")
			indicator.material_override = mat
			content.add_child(indicator)

func make_visual(item_id: String, active := false, packed := false) -> Node3D:
	var host := Node3D.new()
	host.name = item_id
	var kind: String = GameState.items.definitions[item_id].visual
	if kind in ["burger", "wrap", "drink"]:
		var path := "res://assets/environment/prp_market_%s_v01.glb" % kind
		if ResourceLoader.exists(path):
			var scene := load(path) as PackedScene
			if scene != null:
				var visual := scene.instantiate() as Node3D
				host.add_child(visual)
				visual.scale = Vector3.ONE * 0.75
				if packed:
					_box(host, Vector3(0.38, 0.055, 0.3), Vector3.ZERO, Color("d0b990"))
				return host
	match kind:
		"blanket":
			_box(host, Vector3(0.9 if active else 0.55, 0.045 if active else 0.15, 1.1 if active else 0.24), Vector3(0, 0.08, 0), Color("9e728c"))
			_box(host, Vector3(0.55, 0.016, 0.035), Vector3(0, 0.165 if not active else 0.108, 0.07), Color("dbc2a0"))
		"battery":
			for x in [-0.08, 0.08]:
				_box(host, Vector3(0.09, 0.24, 0.09), Vector3(x, 0.13, 0), Color("417f80"))
				_box(host, Vector3(0.05, 0.03, 0.05), Vector3(x, 0.26, 0), Color("c5beb0"))
		_:
			_box(host, Vector3(0.32, 0.1, 0.16), Vector3(0, 0.08, 0), Color("859c9d"))
			_box(host, Vector3(0.12, 0.14, 0.18), Vector3(0.06, 0.16, 0), Color("b4bcb5"))
	return host

func _box(parent: Node3D, size_value: Vector3, at: Vector3, color: Color) -> void:
	var instance := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size_value
	instance.mesh = mesh
	instance.position = at
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.88
	instance.material_override = material
	parent.add_child(instance)

func _feedback(action: String, _item_id: String) -> void:
	# Short, quiet one-shot cues; ledger restore never emits feedback.
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = 22050
	var frames := 2205
	var samples := PackedByteArray()
	samples.resize(frames * 2)
	var frequency := 260.0 if action in ["place", "install", "activate"] else 420.0
	for index in range(frames):
		var envelope := pow(1.0 - float(index) / frames, 3.0)
		samples.encode_s16(index * 2, int(2400.0 * sin(TAU * frequency * index / 22050.0) * envelope))
	stream.data = samples
	sound.stream = stream
	sound.play()
