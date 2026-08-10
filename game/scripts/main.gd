extends Node3D

const InteractableScript = preload("res://scripts/interactable.gd")

var palette := {
	"sand": Color("9f7258"),
	"rock": Color("5d5a73"),
	"coral": Color("d55d6d"),
	"teal": Color("3d8f95"),
	"cream": Color("e6c894"),
	"night": Color("18233b"),
}

func _ready() -> void:
	GameState.load_game()
	_build_lighting()
	_build_ground()
	_build_settlement()
	_build_interactables()

func _build_lighting() -> void:
	var environment := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("152037")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("7fa9b6")
	env.ambient_light_energy = 0.48
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	environment.environment = env
	add_child(environment)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52, -28, 0)
	sun.light_color = Color("ffd7a0")
	sun.light_energy = 0.82
	sun.shadow_enabled = true
	add_child(sun)

func _build_ground() -> void:
	_add_static_box("Ground", Vector3(34, 0.5, 34), Vector3(0, -0.25, 0), palette.sand)
	for data in [
		[Vector3(-13, 0.5, -11), Vector3(4, 1, 7)],
		[Vector3(12, 0.7, -10), Vector3(6, 1.4, 4)],
		[Vector3(-12, 0.4, 12), Vector3(5, 0.8, 5)],
	]:
		_add_static_box("Rock", data[1], data[0], palette.rock)

func _build_settlement() -> void:
	_add_hut(Vector3(-6, 0, -5), palette.coral)
	_add_hut(Vector3(5, 0, -7), palette.teal)
	_add_hut(Vector3(8, 0, 3), palette.cream)
	_add_hut(Vector3(-7, 0, 6), palette.night)
	for i in range(9):
		var angle := TAU * float(i) / 9.0
		var position := Vector3(cos(angle) * 14.0, 0.8, sin(angle) * 14.0)
		_add_mesh("GlowPlant", SphereMesh.new(), Vector3(0.35, 1.2, 0.35), position, Color("78dba9"), false)

func _build_interactables() -> void:
	_add_npc("mira", "米拉 / Mira", Vector3(-3, 1.0, -2), Color("f2a65a"))
	_add_npc("rowan", "罗文 / Rowan", Vector3(6, 1.0, 1), Color("a56cc1"))
	_add_npc("tavi", "塔维 / Tavi", Vector3(-8, 1.0, 3), Color("ed6a5a"))
	_add_npc("vesh", "维什 / Vesh", Vector3(2, 1.0, -9), Color("6cc3a0"))
	_add_npc("ori", "奥里 / Ori", Vector3(10, 1.0, 8), Color("e6c84f"))
	_add_pickup("berry", "berry_a", "蓝莓果", Vector3(-10, 0.65, -2), Color("5364c9"))
	_add_pickup("berry", "berry_b", "蓝莓果", Vector3(-13, 0.65, 5), Color("5364c9"))
	_add_pickup("scrap", "scrap_a", "合金零件", Vector3(11, 0.45, -5), Color("b8c1c8"), "box")
	_add_pickup("scrap", "scrap_b", "合金零件", Vector3(14, 0.45, 2), Color("b8c1c8"), "box")
	_add_station("water", "reservoir", "聚落蓄水器", Vector3(10, 1.0, 9), Color("4fb6d3"))
	_add_station("heater", "heater", "旧加热器", Vector3(-6, 0.7, 7), Color("e1724d"))
	_add_station("shelter", "shelter", "你的庇护所", Vector3(-7, 0.8, 8.5), Color("f0d49b"))

func _add_hut(position: Vector3, color: Color) -> void:
	_add_static_box("Hut", Vector3(4.5, 2.8, 3.6), position + Vector3(0, 1.4, 0), color)
	var roof := CylinderMesh.new()
	roof.top_radius = 0.7
	roof.bottom_radius = 3.0
	roof.height = 1.8
	_add_mesh("Roof", roof, Vector3.ONE, position + Vector3(0, 3.55, 0), color.darkened(0.28), false)

func _add_npc(npc_id: String, npc_name: String, position: Vector3, color: Color) -> void:
	var npc := WorldInteractable.new()
	npc.interaction_kind = "npc"
	npc.target_id = npc_id
	npc.display_name = npc_name
	npc.position = position
	add_child(npc)
	var body := CapsuleMesh.new()
	body.radius = 0.38
	body.height = 1.55
	_add_child_mesh(npc, body, Vector3(0, 0, 0), color)
	var head := SphereMesh.new()
	head.radius = 0.33
	head.height = 0.66
	_add_child_mesh(npc, head, Vector3(0, 0.82, 0), color.lightened(0.12))

func _add_pickup(kind: String, target_id: String, label: String, position: Vector3, color: Color, shape := "sphere") -> void:
	var pickup := WorldInteractable.new()
	pickup.interaction_kind = kind
	pickup.target_id = target_id
	pickup.display_name = label
	pickup.one_shot = true
	pickup.position = position
	add_child(pickup)
	var mesh: PrimitiveMesh = BoxMesh.new() if shape == "box" else SphereMesh.new()
	_add_child_mesh(pickup, mesh, Vector3.ZERO, color, Vector3(0.55, 0.55, 0.55))

func _add_station(kind: String, target_id: String, label: String, position: Vector3, color: Color) -> void:
	var station := WorldInteractable.new()
	station.interaction_kind = kind
	station.target_id = target_id
	station.display_name = label
	station.position = position
	add_child(station)
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.65
	mesh.bottom_radius = 0.8
	mesh.height = 1.4
	_add_child_mesh(station, mesh, Vector3.ZERO, color)

func _add_static_box(node_name: String, size: Vector3, position: Vector3, color: Color) -> void:
	var body := StaticBody3D.new()
	body.name = node_name
	body.position = position
	add_child(body)
	var mesh := BoxMesh.new()
	mesh.size = size
	_add_child_mesh(body, mesh, Vector3.ZERO, color)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)

func _add_mesh(node_name: String, mesh: PrimitiveMesh, scale_value: Vector3, position: Vector3, color: Color, cast_shadow: bool) -> void:
	var instance := MeshInstance3D.new()
	instance.name = node_name
	instance.mesh = mesh
	instance.scale = scale_value
	instance.position = position
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if cast_shadow else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	instance.material_override = _material(color)
	add_child(instance)

func _add_child_mesh(parent: Node3D, mesh: PrimitiveMesh, position: Vector3, color: Color, scale_value := Vector3.ONE) -> void:
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = position
	instance.scale = scale_value
	instance.material_override = _material(color)
	parent.add_child(instance)

func _material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.9
	return material
