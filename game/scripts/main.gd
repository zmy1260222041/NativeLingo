extends Node3D

const InteractableScript = preload("res://scripts/interactable.gd")
const EnvLodScript := preload("res://scripts/env_lod.gd")
const ENV_DIR := "res://assets/environment/"
const CEL_SHADER_PATH := "res://shaders/cel_base.gdshader"
const MIRA_MODEL_PATH := "res://assets/characters/chr_npc_mira.glb"
const MIRA_MODEL_SOURCE_HEIGHT_M := 1.117689013
const MIRA_RUNTIME_HEIGHT_M := 1.72

var palette := {
	"sand": Color("a97d68"),
	"rock": Color("4b5268"),
	"coral": Color("d8665b"),
	"teal": Color("2f8c87"),
	"cream": Color("b87a42"),
	"night": Color("34335e"),
}

var environment: Environment
var sky_material: ProceduralSkyMaterial
var sun: DirectionalLight3D
var _day_cycle := DayCycleLighting.new()
var _cel_shader: Shader
var _white_tex: Texture2D
var _used_market_stall := false
var _used_lanterns := false
var _used_glow_plants := false
var _used_shelter := false
var _used_ground := false
var _glow_lanterns: Array[ShaderMaterial] = []
var _glow_heaters: Array[ShaderMaterial] = []
var _glow_plants: Array[ShaderMaterial] = []
var _glow_windows: Array[ShaderMaterial] = []
var _glow_relics: Array[ShaderMaterial] = []
var _lantern_lights: Array[OmniLight3D] = []
var _heater_light: OmniLight3D

func _ready() -> void:
	GameState.load_game()
	_cel_shader = load(CEL_SHADER_PATH) as Shader
	_white_tex = _make_white_texture()
	_build_lighting()
	_build_ground()
	_build_authored_environment()
	_build_settlement()
	_build_alien_greens()
	_build_landmarks()
	_build_interactables()

func _process(_delta: float) -> void:
	_update_daylight()

func _build_lighting() -> void:
	environment = Environment.new()
	environment.background_mode = Environment.BG_SKY
	sky_material = ProceduralSkyMaterial.new()
	var sky := Sky.new()
	sky.sky_material = sky_material
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var world_environment := WorldEnvironment.new()
	world_environment.environment = environment
	add_child(world_environment)
	sun = DirectionalLight3D.new()
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 35.0
	sun.shadow_bias = 0.04
	add_child(sun)
	environment.fog_enabled = true
	environment.fog_light_energy = 1.0
	environment.glow_enabled = true
	environment.glow_intensity = 0.36
	environment.glow_bloom = 0.0
	environment.glow_hdr_threshold = 1.08
	environment.glow_hdr_scale = 1.2
	_update_daylight()

func _update_daylight() -> void:
	if environment == null or sky_material == null or sun == null:
		return
	var hours := GameState.clock_hours()
	var glow := _day_cycle.apply(environment, sky_material, sun, hours)
	_update_authored_glow(glow)

func _build_ground() -> void:
	# 80m 步行基座 + 28m 市场地表；山谷地板从市场边接到左右山脚（§3.4）
	var ground := _add_static_box("Ground", Vector3(80, 0.5, 80), Vector3(0, -0.25, 0), palette.sand)
	_used_ground = _try_load_env("env_ground_market_a.glb", Vector3.ZERO, false, Vector3.ZERO) != null
	var _used_tufts := _try_load_env("fol_ground_tufts_a.glb", Vector3.ZERO, false, Vector3.ZERO)
	if _used_ground:
		_hide_meshes(ground)
		_apply_ground_tile()
	var terrace := _try_load_env("env_terrace_market_a.glb", Vector3(-3.2, 0, 1.6), true, Vector3.ZERO)
	if terrace != null:
		_add_fitted_collision(terrace)
		_enable_mesh_shadows(terrace)
		_add_asset_outlines(terrace, 2)
	else:
		push_error("Main: missing env_terrace_market_a.glb")
	for data in [
		[Vector3(-13, 0.5, -11), "env_rock_facet_b.glb", Vector3(1.6, 0, 0.8)],
		[Vector3(12, 0.7, -10), "env_rock_facet_a.glb", Vector3(1.6, 0, 0.8)],
		[Vector3(-12, 0.4, 12), "env_rock_facet_b.glb", Vector3(1.6, 0, 0.8)],
	]:
		var rock_visual := _try_load_env(
			data[1],
			data[0] * Vector3(1, 0, 1) + data[2],
			false,
			Vector3.ZERO
		)
		if rock_visual == null:
			push_error("Main: missing faceted rock %s" % data[1])
			continue
		_add_visual_mesh_collision(rock_visual)
		_enable_mesh_shadows(rock_visual)
		_add_asset_outlines(rock_visual, 2)
	# 边缘采集区的两处新切面岩（§5.2 边缘只放功能设施，制造路线选择）
	for accent in [
		["env_rock_facet_b.glb", Vector3(14.6, 0, 3.2), 1.9],
		["env_rock_facet_a.glb", Vector3(-14.8, 0, 3.8), 0.3],
	]:
		var edge_rock := _try_load_env(accent[0], accent[1], false, Vector3.ZERO)
		if edge_rock != null:
			edge_rock.rotation.y = accent[2]
			_add_visual_mesh_collision(edge_rock)
			_enable_mesh_shadows(edge_rock)
			_add_asset_outlines(edge_rock, 2)

func _build_authored_environment() -> void:
	var stall := _try_load_env(
		"env_market_stall_a.glb",
		Vector3(-1.8, 0, -2.2),
		true,
		Vector3.ZERO
	)
	_used_market_stall = stall != null
	if stall != null:
		_add_fitted_collision(stall)
		_enable_mesh_shadows(stall)
		_ground_stall_counter(stall)
		_detail_stall_bowls(stall)
		for offset in [Vector3(-0.65, 1.12, 0.15), Vector3(0.65, 1.12, -0.1)]:
			var token: Node3D = _instantiate_env("prp_food_token_c.glb")
			if token != null:
				stall.add_child(token)
				token.position = offset
				token.rotation.y = 0.7 if offset.x < 0 else -0.3
				_enable_mesh_shadows(token)
	var shelter := _try_load_env(
		"env_shelter_distant_a.glb",
		Vector3(-7, 0, 8.5),
		false,
		Vector3.ZERO
	)
	_used_shelter = shelter != null
	if shelter != null:
		_add_fitted_collision(shelter)
		_enable_mesh_shadows(shelter)
		_add_asset_outlines(shelter, 3)
	var lantern_ok := 0
	for position in [
		Vector3(-3.2, 0, -2.2),
		Vector3(3.2, 0, -0.2),
		Vector3(-4.5, 0, 1.8),
		Vector3(4.6, 0, -1.0),
		Vector3(-1.7, 0, -7.5),
	]:
		var lantern := _try_load_env("prp_lantern_market_a.glb", position, false, Vector3.ZERO)
		if lantern != null:
			_add_fitted_collision(lantern)
			_enable_mesh_shadows(lantern)
			_add_lantern_light(position + Vector3(0, 1.8, 0))
			lantern_ok += 1
	_used_lanterns = lantern_ok > 0
	_used_glow_plants = _add_authored_glow_plants()

func _build_settlement() -> void:
	# §5.3 住宅构造：GLB 优先（陶基座+壳板墙+合金补片），缺失才回退图元
	_add_residence("env_hut_residential_a.glb", Vector3(-6, 0, -5), PI, Vector3(4.7, 3.5, 3.9), palette.coral)
	_add_residence("env_hut_residential_b.glb", Vector3(5, 0, -7), PI, Vector3(4.5, 4.5, 3.5), palette.teal)
	_add_residence("env_hut_residential_c.glb", Vector3(8, 0, 3), 0.35, Vector3(3.4, 4.2, 4.3), palette.coral)
	if not _used_shelter:
		_add_residence("env_hut_residential_b.glb", Vector3(-7, 0, 6), 0.0, Vector3(4.5, 4.5, 3.5), palette.night)
	_build_usage_traces()
	_build_stylized_flora()
	if not _used_glow_plants:
		push_error("Main: fol_glowplant_a.glb missing; ring primitive fallback removed (art-bible §8.8)")


func _add_residence(file: String, position: Vector3, rotation_y: float, _collision_size: Vector3, _fallback_color: Color) -> void:
	var hut := _try_load_env(file, position, true, Vector3.ZERO)
	if hut == null:
		push_error("Main: missing residence %s (primitive hut fallback removed, art-bible §8.8)" % file)
		return
	hut.rotation.y = rotation_y
	_add_fitted_collision(hut)
	_enable_mesh_shadows(hut)
	_add_asset_outlines(hut, 3)


## §3.7.A 球形法线异星树：英雄树近广场 + 边缘树围出天际线（§5.2 边缘采集区）
func _build_stylized_flora() -> void:
	var trees := [
		[Vector3(2.2, 0, 5.6), 0.4],
		[Vector3(-10.5, 0, -6.5), 1.2],
		[Vector3(10.8, 0, -3.6), -0.9],
		[Vector3(-3.4, 0, 12.2), 2.4],
		[Vector3(12.6, 0, 9.6), 0.7],
		[Vector3(-5.5, 0, -9.5), 1.7],
	]
	for entry in trees:
		var tree := _try_load_env("fol_tree_stranger_a.glb", entry[0], true, Vector3.ZERO)
		if tree == null:
			push_error("Main: missing fol_tree_stranger_a.glb (primitive tree fallback removed)")
			continue
		tree.rotation.y = entry[1]
		_add_fitted_collision(tree, PackedStringArray(["canopy", "leaf"]))
		_enable_mesh_shadows(tree)
		_enable_tree_sway(tree)
	# §3.4 远景轮廓层：左右山谷山脊 + 谷地地板，带碰撞
	var ridge := _try_load_env("env_ridge_distant_a.glb", Vector3.ZERO, false, Vector3.ZERO)
	if ridge != null:
		_add_fitted_collision(ridge)
		_apply_valley_ground_tile(ridge)
	else:
		push_error("Main: missing env_ridge_distant_a.glb")


## 树冠切到 cel_foliage（§5.4 风动，振幅随高度）；树冠描边壳同步风摆参数，
## 避免 inverted-hull 与摆动树冠分离（§3.7.A 验收）。材质经 material_override
## 逐树实例化，phase 取自树位，保证各树相位错开。
func _enable_tree_sway(tree: Node3D) -> void:
	_attach_foliage_sway(tree, 0.035, 4.0)


## §5.6 绿地外星点缀：卷蕨簇 / 光苇 / 遗迹独石。成组摆放不成阵列，
## 只进绿地空档，不与市场核心抢轮廓。
func _build_alien_greens() -> void:
	for entry in [
		[Vector3(-8.6, 0, -12.4), 0.7, 1.0],
		[Vector3(7.2, 0, -12.6), 2.1, 0.9],
		[Vector3(-15.4, 0, -2.6), 1.4, 1.05],
		[Vector3(-16.2, 0, 8.4), 0.3, 0.95],
		[Vector3(15.8, 0, -7.6), 1.9, 1.0],
		[Vector3(5.6, 0, 12.8), 0.9, 0.9],
		[Vector3(-0.9, 0, 14.2), 2.6, 1.1],
		[Vector3(13.6, 0, 12.6), 1.2, 0.85],
	]:
		var frond := _try_load_env("fol_frond_alien_a.glb", entry[0], false, Vector3.ZERO)
		if frond == null:
			push_error("Main: missing fol_frond_alien_a.glb")
			continue
		frond.rotation.y = entry[1]
		frond.scale = Vector3.ONE * entry[2]
		_add_fitted_collision(frond, PackedStringArray(["canopy"]))
		_enable_mesh_shadows(frond)
		_attach_foliage_sway(frond, 0.055, 1.4)
	for entry in [
		[Vector3(-12.2, 0, -4.0), 0.4, 1.0],
		[Vector3(12.4, 0, 6.2), 1.7, 0.9],
		[Vector3(3.0, 0, -13.5), 0.9, 0.8],
		[Vector3(-5.2, 0, -13.2), 2.3, 1.1],
		[Vector3(16.4, 0, 0.2), 0.6, 0.85],
		[Vector3(-16.0, 0, -7.4), 1.5, 0.75],
		[Vector3(10.4, 0, -12.4), 2.8, 1.0],
	]:
		var reed := _try_load_env("fol_reed_glow_a.glb", entry[0], false, Vector3.ZERO)
		if reed == null:
			push_error("Main: missing fol_reed_glow_a.glb")
			continue
		reed.rotation.y = entry[1]
		reed.scale = Vector3.ONE * entry[2]
		_enable_mesh_shadows(reed)
	# 遗迹角：西绿地主标（一立一倒），东侧远处立一块小的呼应
	var mono_a := _try_load_env("prp_monolith_a.glb", Vector3(-16.8, 0, -10.8), false, Vector3.ZERO)
	if mono_a != null:
		mono_a.rotation = Vector3(0.0, 0.6, 0.05)
		_add_fitted_collision(mono_a)
		_enable_mesh_shadows(mono_a)
		_add_asset_outlines(mono_a, 2)
	else:
		push_error("Main: missing prp_monolith_a.glb")
	# v2 倒石板：恢复原先“斜插倾倒”姿态（姿态烘焙进资产：基座轮深埋接地、
	# 铭文朝上、头端翘起），护坡碎 石全部半埋——无悬浮件、无接地闪黑
	var mono_b := _try_load_env("prp_monolith_fallen_a.glb", Vector3(-14.9, 0, -12.9), false, Vector3.ZERO)
	if mono_b != null:
		mono_b.rotation.y = 0.7
		_add_fitted_collision(mono_b)
		_enable_mesh_shadows(mono_b)
	var mono_c := _try_load_env("prp_monolith_a.glb", Vector3(16.2, 0, -12.0), false, Vector3.ZERO)
	if mono_c != null:
		mono_c.rotation = Vector3(0.0, -0.9, -0.04)
		mono_c.scale = Vector3.ONE * 0.9
		_add_fitted_collision(mono_c)
		_enable_mesh_shadows(mono_c)
		_add_asset_outlines(mono_c, 2)


func _attach_foliage_sway(node: Node3D, sway_amp: float, canopy_height: float) -> void:
	var foliage := load("res://shaders/cel_foliage.gdshader") as Shader
	if foliage == null:
		push_warning("Main: cel_foliage shader missing, sway disabled")
		return
	var phase := node.position.x * 3.1 + node.position.z * 2.3
	_apply_tree_sway(node, foliage, phase, sway_amp, canopy_height)


func _apply_tree_sway(
	node: Node, foliage: Shader, phase: float,
	sway_amp := 0.035, canopy_height := 4.0,
) -> void:
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		var lower := String(mi.name).to_lower()
		var is_trunk := "trunk" in lower
		if "canopy" in lower or is_trunk:
			if lower.ends_with("_outline"):
				var om := mi.material_override as ShaderMaterial
				if om != null:
					om.set_shader_parameter("sway_amp", sway_amp)
					om.set_shader_parameter("canopy_height", canopy_height)
					om.set_shader_parameter("phase_offset", phase)
			else:
				var mat := ShaderMaterial.new()
				mat.shader = foliage
				mat.set_shader_parameter("base_color", Color(1, 1, 1))
				var src := mi.material_override
				if src == null and mi.mesh != null and mi.mesh.get_surface_count() > 0:
					src = mi.mesh.surface_get_material(0)
				if src is ShaderMaterial:
					for pname in ["albedo_tex", "normal_tex", "orm_tex"]:
						var tex = (src as ShaderMaterial).get_shader_parameter(pname)
						if tex != null:
							mat.set_shader_parameter(pname, tex)
				mat.set_shader_parameter("sway_amp", sway_amp)
				mat.set_shader_parameter("canopy_height", canopy_height)
				mat.set_shader_parameter("phase_offset", phase)
				# 树干与树冠同一光照模型（cel_foliage 禁环境光 + 暗影量化），
				# 修复树干夜里被环境光洗白、与树冠色调脱节（v04 复查）。
				mat.set_shader_parameter("vcol_strength", 0.92 if is_trunk else 0.55)
				mi.material_override = mat
	for child in node.get_children():
		_apply_tree_sway(child, foliage, phase, sway_amp, canopy_height)


## §5.5 使用痕迹 + §5.2 密度：每个 NPC 驻点 ≥1 组道具，市场核心 ≥2 组
func _build_usage_traces() -> void:
	var traces := [
		["prp_crate_stack_a.glb", Vector3(-3.9, 0, -1.0), 0.6, Vector3(1.1, 0.9, 0.9)],
		["prp_amphora_cluster_a.glb", Vector3(1.6, 0, -0.4), -0.4, Vector3(1.0, 1.1, 0.9)],
		["prp_drying_rack_a.glb", Vector3(-3.8, 0, -0.6), 0.25, Vector3(1.5, 0.4, 0.5)],
		["prp_crate_stack_a.glb", Vector3(2.6, 0, -8.2), 2.2, Vector3(1.1, 0.9, 0.9)],
		["prp_drying_rack_a.glb", Vector3(-8.9, 0, 2.1), -0.9, Vector3(1.5, 0.4, 0.5)],
		["prp_amphora_cluster_a.glb", Vector3(9.2, 0, 8.3), 1.3, Vector3(1.0, 1.1, 0.9)],
		["prp_crate_stack_a.glb", Vector3(10.9, 0, 7.0), -0.5, Vector3(1.1, 0.9, 0.9)],
		# v1.5 密度补组（§5.2 住宅带每 6×6 m ≤1 组、市场核心补前景锚）：
		["prp_crate_stack_a.glb", Vector3(-4.2, 0, -7.6), 1.1, Vector3(1.1, 0.9, 0.9)],
		["prp_amphora_cluster_a.glb", Vector3(3.4, 0, -8.6), 0.8, Vector3(1.0, 1.1, 0.9)],
		["prp_crate_stack_a.glb", Vector3(6.4, 0, 4.4), -1.2, Vector3(1.1, 0.9, 0.9)],
		["prp_amphora_cluster_a.glb", Vector3(1.2, 0, 3.4), 2.0, Vector3(1.0, 1.1, 0.9)],
		["prp_drying_rack_a.glb", Vector3(-5.6, 0, 4.6), 0.9, Vector3(1.5, 0.4, 0.5)],
		["prp_crate_stack_a.glb", Vector3(2.0, 0, -4.6), 0.35, Vector3(1.1, 0.9, 0.9)],
		["prp_amphora_cluster_a.glb", Vector3(-8.6, 0, 6.8), -0.2, Vector3(1.0, 1.1, 0.9)],
		["prp_crate_stack_a.glb", Vector3(9.6, 0, 5.4), 2.6, Vector3(1.1, 0.9, 0.9)],
	]
	for trace in traces:
		var prop := _try_load_env(trace[0], trace[1], false, Vector3.ZERO)
		if prop == null:
			continue
		prop.rotation.y = trace[2]
		_enable_mesh_shadows(prop)
		_add_fitted_collision(prop)

func _build_landmarks() -> void:
	var plaza := _try_load_env("env_plaza_market_a.glb", Vector3.ZERO, false, Vector3.ZERO)
	if plaza == null:
		push_error("Main: missing env_plaza_market_a.glb; primitive plaza removed")
	else:
		_add_fitted_collision(plaza)
	if not _used_market_stall:
		push_error("Main: env_market_stall_a.glb missing; primitive canopy fallback removed (art-bible §8.8)")
	var beacon := _try_load_env("prp_beacon_market_a.glb", Vector3(4.4, 0, 4.4), true, Vector3.ZERO)
	if beacon != null:
		_add_fitted_collision(beacon)
		_enable_mesh_shadows(beacon)
		_add_asset_outlines(beacon, 2)
	else:
		push_error("Main: missing prp_beacon_market_a.glb")
	if not _used_lanterns:
		push_error("Main: prp_lantern_market_a.glb missing; primitive lantern fallback removed (art-bible §8.8)")

func _build_interactables() -> void:
	_add_npc("mira", tr("NPC_MIRA"), Vector3(-1.7, 1.0, -0.55), Color("f2a65a"), 0)
	_add_npc("rowan", tr("NPC_ROWAN"), Vector3(3, 1.0, 0.5), Color("a56cc1"), 1)
	_add_npc("tavi", tr("NPC_TAVI"), Vector3(-8, 1.0, 3), Color("ed6a5a"), 2)
	_add_npc("vesh", tr("NPC_VESH"), Vector3(2, 1.0, -9), Color("6cc3a0"), 3)
	_add_npc("ori", tr("NPC_ORI"), Vector3(10, 1.0, 8), Color("e6c84f"), 4)
	_add_pickup("berry", "berry_a", tr("ITEM_BERRY"), Vector3(-10, 0.65, -2), Color("5364c9"))
	_add_pickup("berry", "berry_b", tr("ITEM_BERRY"), Vector3(-13, 0.65, 5), Color("5364c9"))
	_add_pickup("scrap", "scrap_a", tr("ITEM_SCRAP"), Vector3(11, 0.45, -5), Color("b8c1c8"), "box")
	_add_pickup("scrap", "scrap_b", tr("ITEM_SCRAP"), Vector3(14, 0.45, 2), Color("b8c1c8"), "box")
	_add_station("water", "reservoir", tr("STATION_RESERVOIR"), Vector3(10, 1.0, 9), Color("4fb6d3"))
	# v03: 加热器移出庇护所基座（庇护所 x∈[-9.9,-4.1]，此前 -6 处整台埋进台基里）
	_add_station("heater", "heater", tr("STATION_HEATER"), Vector3(-3.2, 0.7, 6.0), Color("e1724d"))
	_add_station("shelter", "shelter", tr("STATION_SHELTER"), Vector3(-7, 0.8, 8.5), Color("f0d49b"))

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
	if npc_id == "mira" and not actor_visual.use_authored_static_model(
		MIRA_MODEL_PATH,
		MIRA_MODEL_SOURCE_HEIGHT_M,
		MIRA_RUNTIME_HEIGHT_M,
		-position.y,
	):
		push_warning("Main: authored Mira model unavailable; using procedural fallback")
	npc.add_child(actor_visual)

func _add_pickup(kind: String, target_id: String, label: String, position: Vector3, color: Color, shape := "sphere") -> void:
	var pickup := WorldInteractable.new()
	pickup.interaction_kind = kind
	pickup.target_id = target_id
	pickup.display_name = label
	pickup.one_shot = true
	pickup.position = position
	add_child(pickup)
	var token := ""
	if kind == "berry":
		token = "prp_food_token_a.glb" if target_id.ends_with("a") else "prp_food_token_b.glb"
	if token != "" and _attach_env_visual(pickup, token):
		_enable_mesh_shadows(pickup)
		return
	var mesh: PrimitiveMesh = BoxMesh.new() if shape == "box" else SphereMesh.new()
	_add_child_mesh(pickup, mesh, Vector3.ZERO, color, Vector3(0.55, 0.55, 0.55))

func _add_station(kind: String, target_id: String, label: String, position: Vector3, color: Color) -> void:
	var station := WorldInteractable.new()
	station.interaction_kind = kind
	station.target_id = target_id
	station.display_name = label
	station.position = position
	add_child(station)
	if kind == "shelter" and _used_shelter:
		return
	var file := ""
	if kind == "heater":
		file = "prp_heater_old.glb"
	elif kind == "water":
		file = "prp_reservoir_a.glb"
	if file != "" and _attach_env_visual(station, file):
		var vis := station.get_child(station.get_child_count() - 1) as Node3D
		if vis != null:
			vis.position.y = -station.position.y
		_enable_mesh_shadows(station)
		_add_asset_outlines(station, 2)
		_add_fitted_collision(station)
		if kind == "heater":
			_add_heater_light(station)
		return
	push_error("Main: missing station visual %s; primitive cylinder fallback removed" % kind)

func _add_static_box(node_name: String, size: Vector3, position: Vector3, color: Color) -> StaticBody3D:
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
	return body

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
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	instance.material_override = _material(color)
	parent.add_child(instance)

func _material(color: Color, emission := Color.TRANSPARENT) -> ShaderMaterial:
	var material := ShaderMaterial.new()
	if _cel_shader != null:
		material.shader = _cel_shader
		material.set_shader_parameter("base_color", color)
		material.set_shader_parameter("albedo_tex", _white_tex)
		material.set_shader_parameter("rough", 0.85)
		if emission.a > 0.0:
			material.set_shader_parameter("functional_rim", true)
			material.set_shader_parameter("rim_color", emission)
			material.set_shader_parameter("rim_strength", 0.55)
		return material
	var fallback := StandardMaterial3D.new()
	fallback.albedo_color = color
	fallback.roughness = 0.9
	if emission.a > 0.0:
		fallback.emission_enabled = true
		fallback.emission = emission
		fallback.emission_energy_multiplier = 0.36
	var wrapped := ShaderMaterial.new()
	wrapped.next_pass = fallback
	return wrapped


func _try_load_env(file: String, position: Vector3, hero: bool, collision_size: Vector3) -> Node3D:
	var inst := _instantiate_env(file)
	if inst == null:
		return null
	inst.position = position
	add_child(inst)
	if hero:
		var lod := EnvLodScript.new()
		lod.configure(true)
		inst.add_child(lod)
	if collision_size != Vector3.ZERO:
		_add_env_collision(inst, collision_size)
	return inst


func _attach_env_visual(parent: Node3D, file: String) -> bool:
	var inst := _instantiate_env(file)
	if inst == null:
		return false
	inst.position = Vector3.ZERO
	parent.add_child(inst)
	return true


func _instantiate_env(file: String) -> Node3D:
	var path := ENV_DIR + file
	if not ResourceLoader.exists(path):
		return null
	var packed := load(path) as PackedScene
	if packed == null:
		push_warning("Main: failed to load env asset ", path)
		return null
	var inst := packed.instantiate() as Node3D
	if inst != null:
		inst.name = file.get_basename()
		_paint_env_asset(inst, file)
		_mirror_lod_materials(inst)
	return inst


func _mirror_lod_materials(host: Node) -> void:
	var groups := {}
	_index_lod_meshes(host, groups)
	for suffix in groups:
		var pack: Dictionary = groups[suffix]
		if not pack.has(0):
			continue
		var src := pack[0] as MeshInstance3D
		if src == null or src.mesh == null:
			continue
		for lod in [1, 2]:
			if not pack.has(lod):
				continue
			var dst := pack[lod] as MeshInstance3D
			if dst == null or dst.mesh == null:
				continue
			var count := mini(src.mesh.get_surface_count(), dst.mesh.get_surface_count())
			for s in range(count):
				var mat := src.mesh.surface_get_material(s)
				if mat != null:
					dst.mesh.surface_set_material(s, mat)
			if src.material_override != null:
				dst.material_override = src.material_override


func _index_lod_meshes(node: Node, groups: Dictionary) -> void:
	if node is MeshInstance3D:
		var raw := String(node.name)
		var lower := raw.to_lower()
		for lod in range(3):
			var token := "lod%d__" % lod
			if token in lower:
				var suffix := lower.substr(lower.find(token) + token.length())
				if not groups.has(suffix):
					groups[suffix] = {}
				groups[suffix][lod] = node
				break
	for child in node.get_children():
		_index_lod_meshes(child, groups)


func _add_env_collision(host: Node3D, size: Vector3) -> void:
	var body := StaticBody3D.new()
	body.name = "EnvCollision"
	body.collision_layer = 1
	body.position.y = size.y * 0.5
	host.add_child(body)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)


func _add_authored_glow_plants() -> bool:
	var packed := load(ENV_DIR + "fol_glowplant_a.glb") as PackedScene
	if packed == null:
		return false
	var probe := packed.instantiate() as Node3D
	_paint_env_asset(probe, "fol_glowplant_a.glb")
	var source_mesh := _find_mesh(probe)
	if source_mesh == null:
		probe.queue_free()
		return false
	# §5.6 clusters: irregular groups, never i/N * TAU rings.
	var clusters := [
		[Vector3(-3.5, 0, -3.7), [Vector3(0.2, 0, 0.15), Vector3(-0.45, 0, 0.4), Vector3(0.55, 0, -0.35)]],
		[Vector3(2.6, 0, 2.1), [Vector3(0.0, 0, 0.0), Vector3(0.7, 0, 0.35), Vector3(-0.4, 0, 0.55)]],
		[Vector3(-5.0, 0, 5.2), [Vector3(0.15, 0, -0.2), Vector3(-0.6, 0, 0.25)]],
		[Vector3(6.4, 0, 1.2), [Vector3(0.1, 0, 0.3), Vector3(0.55, 0, -0.4), Vector3(-0.35, 0, -0.15)]],
		[Vector3(0.6, 0, -6.0), [Vector3(0.0, 0, 0.2), Vector3(-0.5, 0, -0.3)]],
		[Vector3(9.1, 0, 6.4), [Vector3(0.25, 0, 0.1), Vector3(-0.4, 0, 0.45)]],
	]
	var root := Node3D.new()
	root.name = "AuthoredGlowPlants"
	add_child(root)
	var idx := 0
	for cluster in clusters:
		var origin: Vector3 = cluster[0]
		var offsets: Array = cluster[1]
		for offset in offsets:
			var xf := Transform3D(Basis(Vector3.UP, float(idx) * 0.7), origin + offset)
			var inst := MultiMeshInstance3D.new()
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = source_mesh.mesh
			mm.instance_count = 1
			mm.set_instance_transform(0, Transform3D.IDENTITY)
			inst.multimesh = mm
			inst.transform = xf
			inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			root.add_child(inst)
			idx += 1
		var rock_file := "env_rock_facet_a.glb" if idx % 2 == 0 else "env_rock_facet_b.glb"
		var anchor := _instantiate_env(rock_file)
		if anchor != null:
			root.add_child(anchor)
			anchor.position = origin + Vector3(0.85, 0, -0.4)
			anchor.scale = Vector3(0.28, 0.22, 0.28)
			anchor.rotation.y = float(idx) * 0.5
	probe.queue_free()
	return true


func _apply_ground_tile() -> void:
	var ground := _find_named_child(self, "env_ground_market_a")
	if ground == null:
		return
	var tex := load("res://assets/environment/tex_ground_packed_1k.png") as Texture2D
	if tex == null:
		return
	_apply_ground_tex(ground, tex)


func _apply_valley_ground_tile(ridge: Node) -> void:
	var tex := load("res://assets/environment/tex_ground_packed_1k.png") as Texture2D
	if tex == null:
		return
	_apply_named_ground_tex(ridge, tex, PackedStringArray(["valley_floor", "valley_foothill"]))


func _apply_named_ground_tex(node: Node, tex: Texture2D, names: PackedStringArray) -> void:
	if node is MeshInstance3D:
		var lower := String(node.name).to_lower()
		for token in names:
			if String(token) in lower:
				_apply_ground_tex(node, tex)
				return
	for child in node.get_children():
		_apply_named_ground_tex(child, tex, names)


func _apply_ground_tex(node: Node, tex: Texture2D) -> void:
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		if mi.material_override is ShaderMaterial:
			var sm := mi.material_override as ShaderMaterial
			sm.set_shader_parameter("albedo_tex", tex)
			sm.set_shader_parameter("use_triplanar", true)
			sm.set_shader_parameter("base_color", Color(1, 1, 1))
		if mi.mesh != null:
			for s in range(mi.mesh.get_surface_count()):
				var mat := mi.mesh.surface_get_material(s)
				if mat is ShaderMaterial:
					var sm2 := mat as ShaderMaterial
					sm2.set_shader_parameter("albedo_tex", tex)
					sm2.set_shader_parameter("use_triplanar", true)
					sm2.set_shader_parameter("base_color", Color(1, 1, 1))
	for child in node.get_children():
		_apply_ground_tex(child, tex)


func _add_lantern_light(position: Vector3) -> void:
	var light := OmniLight3D.new()
	light.name = "LanternLight"
	light.position = position
	light.light_color = Color("ffcb78")
	light.light_energy = 0.12
	light.omni_range = 3.4
	light.shadow_enabled = false
	add_child(light)
	_lantern_lights.append(light)


func _add_heater_light(station: Node3D) -> void:
	var light := OmniLight3D.new()
	light.name = "HeaterGlow"
	light.position = Vector3(0.0, 0.35, 0.0)
	light.light_color = Color("ff9a5c")
	light.light_energy = 0.28
	light.omni_range = 4.2
	light.shadow_enabled = false
	station.add_child(light)
	_heater_light = light


func _register_glow_mat(bucket: Array[ShaderMaterial], mat: ShaderMaterial) -> void:
	if mat != null and bucket.find(mat) < 0:
		bucket.append(mat)


func _update_authored_glow(evening: float) -> void:
	for mat in _glow_lanterns:
		mat.set_shader_parameter("fill", lerpf(0.28, 0.85, evening))
	for mat in _glow_heaters:
		mat.set_shader_parameter("fill", lerpf(0.55, 0.90, evening))
	for mat in _glow_plants:
		mat.set_shader_parameter("fill", lerpf(0.06, 0.80, evening))
	for mat in _glow_windows:
		mat.set_shader_parameter("fill", lerpf(0.22, 0.70, evening))
	for mat in _glow_relics:
		mat.set_shader_parameter("fill", lerpf(0.10, 0.42, evening))
	for light in _lantern_lights:
		light.light_energy = lerpf(0.10, 0.42, evening)
	if _heater_light != null:
		_heater_light.light_energy = lerpf(0.26, 0.55, evening)


func _paint_env_asset(node: Node, file: String) -> void:
	var stem := file.get_file().get_basename().to_lower()
	_paint_env_node(node, stem)


func _paint_env_node(node: Node, stem: String) -> void:
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		if mi.material_override is ShaderMaterial:
			_paint_shader_material(mi.material_override as ShaderMaterial, stem, String(mi.name))
		if mi.mesh != null:
			for s in range(mi.mesh.get_surface_count()):
				var mat := mi.mesh.surface_get_material(s)
				if mat is ShaderMaterial:
					_paint_shader_material(mat as ShaderMaterial, stem, String(mi.name) + " " + mat.resource_name)
	for child in node.get_children():
		_paint_env_node(child, stem)


func _paint_shader_material(mat: ShaderMaterial, stem: String, hint: String) -> void:
	var key := (stem + " " + hint).to_lower()
	var color := Color("c4a574")
	var rim := Color.TRANSPARENT
	var is_floor := "ground" in key or "path" in key or "plaza" in key \
			or "valley" in key or "foothill" in key
	mat.set_shader_parameter("contact_enabled", not is_floor)
	if "hut" in key or "shelter" in key or "terrace" in key or "plaza" in key \
			or "heater" in key or "reservoir" in key or "beacon" in key \
			or "crate" in key or "drying" in key or "amphora" in key \
			or "tufts" in key or "tree" in key or "rock_facet" in key \
			or "frond" in key or "monolith" in key:
		# 住宅/庇护所/绿地组件走贴图 × 顶点色 tint，禁止再染成暮靛黑块。
		mat.set_shader_parameter("base_color", Color(1, 1, 1))
		if "tree" in key:
			mat.set_shader_parameter("vcol_strength", 0.92)
		if "amber" in key or "window" in key:
			mat.set_shader_parameter("functional_rim", true)
			mat.set_shader_parameter("rim_color", Color("f2a85b"))
			mat.set_shader_parameter("rim_strength", 0.45)
			mat.set_shader_parameter("fill", 0.28)
			_register_glow_mat(_glow_windows, mat)
		if "monolith" in key and "glyph" in key:
			mat.set_shader_parameter("functional_rim", true)
			mat.set_shader_parameter("rim_color", Color("9a6acb"))
			mat.set_shader_parameter("rim_strength", 0.5)
			mat.set_shader_parameter("fill", 0.14)
			_register_glow_mat(_glow_relics, mat)
		if "heater" in key:
			mat.set_shader_parameter("fill", 0.55)
			_register_glow_mat(_glow_heaters, mat)
		return
	if "stall" in key:
		if "bowl" in key:
			color = Color("8a5538")
		elif "cap" in key:
			color = Color("c49a52")
		else:
			return
	elif "ground" in key or "path" in key or "valley" in key or "ridge" in key:
		color = Color(1, 1, 1)
	elif "grate" in key:
		color = Color("17243b")
	elif "rock" in key:
		color = Color("4b5268")
	elif "bulb" in key:
		color = Color("f2a85b")
		rim = Color("ff9e63")
		mat.set_shader_parameter("fill", 0.45)
		_register_glow_mat(_glow_lanterns, mat)
	elif "lantern" in key or "alloy" in key:
		color = Color("2a3144")
		if "lantern" in key:
			mat.set_shader_parameter("fill", 0.32)
			_register_glow_mat(_glow_lanterns, mat)
	elif "glow" in key or "plant" in key:
		color = Color("4aa888")
		rim = Color("78c9a4")
		mat.set_shader_parameter("fill", 0.08)
		_register_glow_mat(_glow_plants, mat)
	elif "token" in key or "food" in key:
		color = Color("78c9a4")
		rim = Color("78c9a4")
	mat.set_shader_parameter("base_color", color)
	if rim.a > 0.0:
		mat.set_shader_parameter("functional_rim", true)
		mat.set_shader_parameter("rim_color", rim)
		mat.set_shader_parameter("rim_strength", 0.45)


func _find_named_child(node: Node, stem: String) -> Node:
	if stem.to_lower() in String(node.name).to_lower():
		return node
	for child in node.get_children():
		var found := _find_named_child(child, stem)
		if found != null:
			return found
	return null


func _ground_stall_counter(stall: Node3D) -> void:
	var leg_color := Color("2a3144")
	for x in [-1.42, 1.42]:
		for z in [-0.36, 0.36]:
			var mesh := CylinderMesh.new()
			mesh.top_radius = 0.055
			mesh.bottom_radius = 0.075
			mesh.height = 0.82
			var leg := MeshInstance3D.new()
			leg.name = "CounterLeg"
			leg.mesh = mesh
			leg.position = Vector3(x, 0.41, z)
			leg.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			leg.material_override = _material(leg_color)
			stall.add_child(leg)
			_add_inverted_outline(leg)


func _detail_stall_bowls(stall: Node3D) -> void:
	var bowls: Array[MeshInstance3D] = []
	_collect_named_meshes(stall, "bowl", bowls)
	for bowl in bowls:
		bowl.material_override = _material(Color("8a5538"))
		_add_inverted_outline(bowl)
		var inner := CylinderMesh.new()
		inner.top_radius = 0.11
		inner.bottom_radius = 0.11
		inner.height = 0.016
		var disc := MeshInstance3D.new()
		disc.name = "BowlInterior"
		disc.mesh = inner
		disc.position = Vector3(0.0, 0.04, 0.0)
		disc.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		disc.material_override = _material(Color("3a2116"))
		bowl.add_child(disc)


func _collect_named_meshes(node: Node, stem: String, out: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D and stem in String(node.name).to_lower():
		if not String(node.name).ends_with("_outline"):
			out.append(node as MeshInstance3D)
	for child in node.get_children():
		_collect_named_meshes(child, stem, out)


func _disable_collisions(node: Node) -> void:
	if node is CollisionShape3D:
		(node as CollisionShape3D).disabled = true
	if node is CollisionObject3D:
		(node as CollisionObject3D).collision_layer = 0
		(node as CollisionObject3D).collision_mask = 0
	for child in node.get_children():
		_disable_collisions(child)


func _enable_mesh_shadows(node: Node) -> void:
	if node is MeshInstance3D and not String(node.name).ends_with("_outline"):
		(node as MeshInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	for child in node.get_children():
		_enable_mesh_shadows(child)


func _add_visual_mesh_collision(host: Node3D) -> void:
	_add_fitted_collision(host)


func _add_fitted_collision(host: Node3D, skip_tokens: PackedStringArray = PackedStringArray()) -> void:
	var meshes: Array[MeshInstance3D] = []
	_collect_meshes(host, meshes)
	if meshes.is_empty():
		return
	var body := StaticBody3D.new()
	body.name = "FittedCollision"
	body.collision_layer = 1
	body.collision_mask = 0
	host.add_child(body)
	var added := 0
	for mi in meshes:
		var lower := String(mi.name).to_lower()
		var skip := false
		for token in skip_tokens:
			if String(token) in lower:
				skip = true
				break
		if skip or mi.mesh == null:
			continue
		var shape: Shape3D = mi.mesh.create_trimesh_shape()
		if shape == null:
			shape = mi.mesh.create_convex_shape(true, true)
		if shape == null:
			continue
		var collision := CollisionShape3D.new()
		collision.name = String(mi.name) + "_col"
		collision.shape = shape
		body.add_child(collision)
		collision.global_transform = mi.global_transform
		added += 1
	if added == 0:
		body.queue_free()


func _add_asset_outlines(host: Node, limit: int) -> void:
	var meshes: Array[MeshInstance3D] = []
	_collect_meshes(host, meshes)
	meshes.sort_custom(func(a, b): return _mesh_vertex_count(a) > _mesh_vertex_count(b))
	var count := mini(limit, meshes.size())
	for i in range(count):
		_add_inverted_outline(meshes[i])


func _collect_meshes(node: Node, out: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D and not String(node.name).ends_with("_outline"):
		var lower := String(node.name).to_lower()
		if "lod1__" in lower or "lod2__" in lower:
			return
		out.append(node as MeshInstance3D)
	for child in node.get_children():
		_collect_meshes(child, out)


func _mesh_vertex_count(mi: MeshInstance3D) -> int:
	if mi.mesh == null:
		return 0
	var total := 0
	for s in range(mi.mesh.get_surface_count()):
		total += mi.mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX].size()
	return total


func _add_inverted_outline(mi: MeshInstance3D) -> void:
	if mi == null or mi.mesh == null or mi.get_parent() == null:
		return
	var shader := load("res://shaders/cel_outline.gdshader") as Shader
	if shader == null:
		return
	var outline := mi.duplicate() as MeshInstance3D
	outline.name = String(mi.name) + "_outline"
	var mat := ShaderMaterial.new()
	mat.shader = shader
	outline.material_override = mat
	outline.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.get_parent().add_child(outline)


func _hide_meshes(node: Node) -> void:
	if node is MeshInstance3D:
		(node as MeshInstance3D).visible = false
	for child in node.get_children():
		_hide_meshes(child)


func _find_mesh(node: Node) -> MeshInstance3D:
	if node is MeshInstance3D:
		return node as MeshInstance3D
	for child in node.get_children():
		var found := _find_mesh(child)
		if found != null:
			return found
	return null


func _make_white_texture() -> Texture2D:
	var image := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	image.fill(Color.WHITE)
	return ImageTexture.create_from_image(image)
