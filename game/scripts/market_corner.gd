extends Node3D
## 「白昼市场角落」独立验收场景（art-bible §9.5 frame #1，固定机位）。
##
## 固定 §3.2 白昼行动灯光（不跑 main.gd 的日制 lerp，镜头可复现）。资产经
## _try_load_env 加载 GLB + 挂 EnvLod；GLB 缺失时 push_warning（本场景是验收
## 场景，不要求玩法回退——回退是 main.gd 的职责）。
##
## 内容（计划 Phase 5）：主角(CharacterVisual player model) + 烘焙材质 Mira +
## env_market_stall_a @(-1.8,0,-2.2) + 2×灯笼 + 发光植物 MultiMesh 环 +
## env_ground_market_a + 岩石 + env_shelter_distant_a @(-7,0,8.5)。

const EnvLodScript := preload("res://scripts/env_lod.gd")
const ENV_DIR := "res://assets/environment/"
const MIRA_MODEL_PATH := "res://assets/characters/chr_npc_mira.glb"
const MIRA_MODEL_SOURCE_HEIGHT_M := 1.117689013
const MIRA_RUNTIME_HEIGHT_M := 1.72

var sky_material: ProceduralSkyMaterial
var sun: DirectionalLight3D


func _ready() -> void:
	_build_lighting()
	_build_environment()
	_build_characters()


## §3.2 白昼行动 (10:00-17:00)：5200K 骨白主光 ~0.95 + 6200K 潮青环境 ~0.50。
## 固定值，不跑 _update_daylight，保证镜头与 §9.5 可复现。
func _build_lighting() -> void:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	sky_material = ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color("2b86dc")
	sky_material.sky_horizon_color = Color("c7e4f8")
	sky_material.ground_horizon_color = Color("e4c48c")
	sky_material.ground_bottom_color = Color("9a7348")
	sky_material.sky_curve = 0.09
	sky_material.sun_angle_max = 58.0
	sky_material.sun_curve = 0.09
	sky_material.energy_multiplier = 1.28
	var sky := Sky.new()
	sky.sky_material = sky_material
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("cfe3f4")
	environment.ambient_light_energy = 0.62
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var world_environment := WorldEnvironment.new()
	world_environment.environment = environment
	add_child(world_environment)
	sun = DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-62, -26, 0)
	sun.light_color = Color("fff4cc")
	sun.light_energy = 1.32
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 35.0
	sun.shadow_bias = 0.04
	add_child(sun)
	environment.fog_enabled = true
	environment.fog_light_color = Color("cde3f2")
	environment.fog_density = 0.0034
	environment.fog_sky_affect = 0.08
	environment.fog_aerial_perspective = 0.06
	environment.fog_height = 16.0
	environment.fog_height_density = -0.0018
	environment.glow_enabled = true
	environment.glow_intensity = 0.42
	environment.glow_bloom = 0.0
	environment.glow_hdr_threshold = 1.05
	environment.glow_hdr_scale = 1.35


func _build_environment() -> void:
	_try_load_env("env_ground_market_a.glb", Vector3(0, 0, 0), false)
	_try_load_env("env_market_stall_a.glb", Vector3(-1.8, 0, -2.2), true)
	_try_load_env("prp_lantern_market_a.glb", Vector3(-3.2, 0, -2.2), false)
	_try_load_env("prp_lantern_market_a.glb", Vector3(3.2, 0, -0.2), false)
	_try_load_env("env_shelter_distant_a.glb", Vector3(-7, 0, 8.5), false)
	_try_load_env("env_rock_market_a.glb", Vector3(-7.5, 0, 3.0), false)
	_try_load_env("env_rock_market_b.glb", Vector3(7.0, 0, -1.5), false)
	_add_glow_plants()


func _try_load_env(file: String, position: Vector3, hero: bool) -> void:
	var path := ENV_DIR + file
	if not ResourceLoader.exists(path):
		push_warning("MarketCorner: env asset missing: ", path)
		return
	var packed := load(path) as PackedScene
	if packed == null:
		push_warning("MarketCorner: failed to load: ", path)
		return
	var inst := packed.instantiate() as Node3D
	inst.position = position
	add_child(inst)
	if hero:
		var lod := EnvLodScript.new()
		lod.configure(true)
		inst.add_child(lod)


func _add_glow_plants() -> void:
	var packed := load(ENV_DIR + "fol_glowplant_a.glb") as PackedScene
	if packed == null:
		push_warning("MarketCorner: glow plant asset missing")
		return
	var probe := packed.instantiate() as Node3D
	var source_mesh := _find_mesh(probe)
	if source_mesh == null:
		probe.queue_free()
		return
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = source_mesh.mesh
	mm.instance_count = 24
	for i in range(24):
		var a := TAU * float(i) / 24.0
		var r := 4.2 + fmod(float(i) * 0.73, 2.4)
		var basis := Basis(Vector3.UP, a + PI)
		mm.set_instance_transform(i, Transform3D(basis, Vector3(cos(a) * r, 0.0, sin(a) * r)))
	var inst := MultiMeshInstance3D.new()
	inst.multimesh = mm
	inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(inst)
	probe.queue_free()


func _build_characters() -> void:
	var player := CharacterVisual.new()
	player.name = "PlayerVisual"
	player.configure(Color("bfa982"), Color("5a3f58"), 4, true)
	player.position = Vector3(2.3, 0, 3.0)
	add_child(player)
	var mira := CharacterVisual.new()
	mira.name = "MiraVisual"
	mira.configure(Color("f2a85b"), Color("d8665b"), 0, false)
	if not mira.use_authored_static_model(
		MIRA_MODEL_PATH,
		MIRA_MODEL_SOURCE_HEIGHT_M,
		MIRA_RUNTIME_HEIGHT_M,
		-1.0,
	):
		push_warning("MarketCorner: authored Mira model unavailable; using procedural fallback")
	mira.position = Vector3(-1.7, 1.0, -0.55)
	add_child(mira)


func _find_mesh(node: Node) -> MeshInstance3D:
	if node is MeshInstance3D:
		return node as MeshInstance3D
	for child in node.get_children():
		var found := _find_mesh(child)
		if found != null:
			return found
	return null
