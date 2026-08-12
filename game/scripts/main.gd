extends Node3D

const InteractableScript = preload("res://scripts/interactable.gd")

var palette := {
	"sand": Color("a97d68"),
	"rock": Color("4b5268"),
	"coral": Color("d8665b"),
	"teal": Color("2f8c87"),
	"cream": Color("c8ae77"),
	"night": Color("34335e"),
}

var environment: Environment
var sky_material: ProceduralSkyMaterial
var sun: DirectionalLight3D

func _ready() -> void:
	GameState.load_game()
	_build_lighting()
	_build_ground()
	_build_settlement()
	_build_landmarks()
	_build_interactables()

func _process(_delta: float) -> void:
	_update_daylight()

func _build_lighting() -> void:
	environment = Environment.new()
	environment.background_mode = Environment.BG_SKY
	sky_material = ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color("121a35")
	sky_material.sky_horizon_color = Color("6a436a")
	sky_material.ground_horizon_color = Color("d27c68")
	sky_material.ground_bottom_color = Color("34233f")
	sky_material.sky_curve = 0.28
	var sky := Sky.new()
	sky.sky_material = sky_material
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("7fa9b6")
	environment.ambient_light_energy = 0.46
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var world_environment := WorldEnvironment.new()
	world_environment.environment = environment
	add_child(world_environment)
	sun = DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52, -28, 0)
	sun.light_color = Color("ffd7a0")
	sun.light_energy = 0.78
	sun.shadow_enabled = true
	add_child(sun)

func _update_daylight() -> void:
	if environment == null or sky_material == null or sun == null:
		return
	var progress := clampf(GameState.day_time / GameState.DAY_DURATION, 0.0, 1.0)
	var daylight := sin(progress * PI)
	var evening := smoothstep(0.55, 1.0, progress)
	var morning_top := Color("28365f")
	var noon_top := Color("315d72")
	var night_top := Color("17243b")
	sky_material.sky_top_color = morning_top.lerp(noon_top, daylight).lerp(night_top, evening)
	sky_material.sky_horizon_color = Color("a65f70").lerp(Color("e3a06d"), daylight).lerp(Color("34335e"), evening)
	environment.ambient_light_color = Color("88a9b5").lerp(Color("9fc2bd"), daylight).lerp(Color("59618b"), evening)
	environment.ambient_light_energy = lerpf(0.40, 0.50, daylight) * lerpf(1.0, 0.72, evening)
	sun.light_color = Color("ffc48a").lerp(Color("fff0ce"), daylight).lerp(Color("ef8a6f"), evening)
	sun.light_energy = lerpf(0.66, 0.85, daylight) * lerpf(1.0, 0.48, evening)
	sun.rotation_degrees.x = lerpf(-26.0, -68.0, daylight) + evening * 18.0

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
	for i in range(12):
		var angle := TAU * float(i) / 12.0
		var position := Vector3(cos(angle) * 14.0, 0.8, sin(angle) * 14.0)
		_add_glow_plant(position, i)

func _build_landmarks() -> void:
	var plaza := CylinderMesh.new()
	plaza.top_radius = 5.2
	plaza.bottom_radius = 5.45
	plaza.height = 0.08
	_add_mesh("MeetingPlaza", plaza, Vector3.ONE, Vector3(0, 0.015, 0), Color("c77a5e"), false)
	for data in [
		[Vector3(-6, 0.045, -5), Vector3(2.3, 0.06, 8.0), -0.85],
		[Vector3(5, 0.045, -7), Vector3(2.2, 0.06, 9.0), 0.62],
		[Vector3(7, 0.045, 4), Vector3(2.0, 0.06, 8.0), -0.92],
		[Vector3(-6, 0.045, 7), Vector3(2.0, 0.06, 8.0), 0.72],
	]:
		var path_mesh := BoxMesh.new()
		path_mesh.size = data[1]
		var path := _add_mesh("SoftPath", path_mesh, Vector3.ONE, data[0] * Vector3(0.52, 1, 0.52), Color("d69a70"), false)
		path.rotation.y = data[2]
	_add_market_canopy(Vector3(-1.8, 0, -2.2))
	_add_beacon(Vector3(4.4, 0, 4.4))
	for position in [Vector3(-4.5, 0, 1.8), Vector3(4.6, 0, -1.0), Vector3(-1.7, 0, -7.5)]:
		_add_lantern(position)

func _add_market_canopy(position: Vector3) -> void:
	for x in [-1.6, 1.6]:
		for z in [-1.15, 1.15]:
			var post_mesh := CylinderMesh.new()
			post_mesh.top_radius = 0.075
			post_mesh.bottom_radius = 0.11
			post_mesh.height = 2.7
			_add_mesh("CanopyPost", post_mesh, Vector3.ONE, position + Vector3(x, 1.35, z), Color("473b55"), true)
	var canopy_mesh := PrismMesh.new()
	canopy_mesh.size = Vector3(4.2, 1.0, 3.1)
	var canopy := _add_mesh("MarketCanopy", canopy_mesh, Vector3.ONE, position + Vector3(0, 2.72, 0), Color("dd5b72"), true)
	canopy.rotation.y = PI * 0.5
	var counter_mesh := BoxMesh.new()
	counter_mesh.size = Vector3(3.2, 0.22, 0.9)
	_add_mesh("MarketCounter", counter_mesh, Vector3.ONE, position + Vector3(0, 0.92, 0), Color("6b5266"), true)

func _add_beacon(position: Vector3) -> void:
	var base_mesh := CylinderMesh.new()
	base_mesh.top_radius = 0.6
	base_mesh.bottom_radius = 0.86
	base_mesh.height = 1.3
	_add_mesh("BeaconBase", base_mesh, Vector3.ONE, position + Vector3(0, 0.65, 0), Color("35445c"), true)
	var crystal_mesh := PrismMesh.new()
	crystal_mesh.size = Vector3(0.78, 1.65, 0.58)
	var crystal := _add_mesh("BeaconCrystal", crystal_mesh, Vector3.ONE, position + Vector3(0, 1.75, 0), Color("78c9a4"), false)
	crystal.material_override = _material(Color("78c9a4"), Color("2f8c87"))

func _add_lantern(position: Vector3) -> void:
	var stem_mesh := CylinderMesh.new()
	stem_mesh.top_radius = 0.055
	stem_mesh.bottom_radius = 0.08
	stem_mesh.height = 1.7
	_add_mesh("LanternStem", stem_mesh, Vector3.ONE, position + Vector3(0, 0.85, 0), Color("30384c"), true)
	var bulb_mesh := SphereMesh.new()
	bulb_mesh.radius = 0.23
	bulb_mesh.height = 0.46
	var bulb := _add_mesh("LanternBulb", bulb_mesh, Vector3.ONE, position + Vector3(0, 1.82, 0), Color("ffcb78"), false)
	bulb.material_override = _material(Color("ffcb78"), Color("ff9e63"))

func _add_glow_plant(position: Vector3, index: int) -> void:
	var stem_mesh := CylinderMesh.new()
	stem_mesh.top_radius = 0.04
	stem_mesh.bottom_radius = 0.08
	stem_mesh.height = 1.25 + float(index % 3) * 0.18
	_add_mesh("GlowStem", stem_mesh, Vector3.ONE, position - Vector3(0, 0.15, 0), Color("315f68"), false)
	var bulb_mesh := SphereMesh.new()
	bulb_mesh.radius = 0.25
	bulb_mesh.height = 0.5
	var tint := Color("78c9a4") if index % 2 == 0 else Color("2f8c87")
	var bulb := _add_mesh("GlowBulb", bulb_mesh, Vector3(1.0, 0.76, 1.0), position + Vector3(0, 0.58, 0), tint, false)
	bulb.material_override = _material(tint, tint)

func _build_interactables() -> void:
	_add_npc("mira", tr("NPC_MIRA"), Vector3(-3, 1.0, -2), Color("f2a65a"), 0)
	_add_npc("rowan", tr("NPC_ROWAN"), Vector3(3, 1.0, 0.5), Color("a56cc1"), 1)
	_add_npc("tavi", tr("NPC_TAVI"), Vector3(-8, 1.0, 3), Color("ed6a5a"), 2)
	_add_npc("vesh", tr("NPC_VESH"), Vector3(2, 1.0, -9), Color("6cc3a0"), 3)
	_add_npc("ori", tr("NPC_ORI"), Vector3(10, 1.0, 8), Color("e6c84f"), 4)
	_add_pickup("berry", "berry_a", tr("ITEM_BERRY"), Vector3(-10, 0.65, -2), Color("5364c9"))
	_add_pickup("berry", "berry_b", tr("ITEM_BERRY"), Vector3(-13, 0.65, 5), Color("5364c9"))
	_add_pickup("scrap", "scrap_a", tr("ITEM_SCRAP"), Vector3(11, 0.45, -5), Color("b8c1c8"), "box")
	_add_pickup("scrap", "scrap_b", tr("ITEM_SCRAP"), Vector3(14, 0.45, 2), Color("b8c1c8"), "box")
	_add_station("water", "reservoir", tr("STATION_RESERVOIR"), Vector3(10, 1.0, 9), Color("4fb6d3"))
	_add_station("heater", "heater", tr("STATION_HEATER"), Vector3(-6, 0.7, 7), Color("e1724d"))
	_add_station("shelter", "shelter", tr("STATION_SHELTER"), Vector3(-7, 0.8, 8.5), Color("f0d49b"))

func _add_hut(position: Vector3, color: Color) -> void:
	_add_static_box("Hut", Vector3(4.5, 2.8, 3.6), position + Vector3(0, 1.4, 0), color)
	var roof := CylinderMesh.new()
	roof.top_radius = 0.7
	roof.bottom_radius = 3.0
	roof.height = 1.8
	_add_mesh("Roof", roof, Vector3.ONE, position + Vector3(0, 3.55, 0), color.darkened(0.28), false)
	var door_mesh := BoxMesh.new()
	door_mesh.size = Vector3(1.0, 1.65, 0.12)
	_add_mesh("HutDoor", door_mesh, Vector3.ONE, position + Vector3(0, 0.9, 1.86), color.darkened(0.46), false)
	var window_mesh := SphereMesh.new()
	window_mesh.radius = 0.28
	window_mesh.height = 0.56
	var window := _add_mesh("HutWindow", window_mesh, Vector3(1.0, 1.0, 0.18), position + Vector3(1.35, 1.72, 1.84), Color("78c9a4"), false)
	window.material_override = _material(Color("78c9a4"), Color("2f8c87"))

func _add_npc(npc_id: String, npc_name: String, position: Vector3, color: Color, profile: int) -> void:
	var npc := WorldInteractable.new()
	npc.interaction_kind = "npc"
	npc.target_id = npc_id
	npc.display_name = npc_name
	npc.position = position
	add_child(npc)
	var actor_visual := CharacterVisual.new()
	actor_visual.name = "CharacterVisual"
	actor_visual.configure(color, color.darkened(0.28), profile, false)
	npc.add_child(actor_visual)

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

func _add_mesh(node_name: String, mesh: PrimitiveMesh, scale_value: Vector3, position: Vector3, color: Color, cast_shadow: bool) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = node_name
	instance.mesh = mesh
	instance.scale = scale_value
	instance.position = position
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if cast_shadow else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	instance.material_override = _material(color)
	add_child(instance)
	return instance

func _add_child_mesh(parent: Node3D, mesh: PrimitiveMesh, position: Vector3, color: Color, scale_value := Vector3.ONE) -> void:
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.position = position
	instance.scale = scale_value
	instance.material_override = _material(color)
	parent.add_child(instance)

func _material(color: Color, emission := Color.TRANSPARENT) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.9
	if emission.a > 0.0:
		material.emission_enabled = true
		material.emission = emission
		material.emission_energy_multiplier = 0.36
	return material
