class_name EnvMaterialFactory
extends RefCounted
## Shared import/runtime contract. White ORM is not a neutral nonmetal map.
const SHADER := preload("res://shaders/cel_base.gdshader")
static var _white: ImageTexture
static var _flat: ImageTexture
static var _neutral: ImageTexture

static func solid_texture(color: Color) -> ImageTexture:
	var image := Image.create(2, 2, false, Image.FORMAT_RGBA8)
	image.fill(color)
	return ImageTexture.create_from_image(image)

static func from_material(source: Material) -> ShaderMaterial:
	if _white == null:
		_white = solid_texture(Color.WHITE)
		_flat = solid_texture(Color(0.5, 0.5, 1.0))
		_neutral = solid_texture(Color(1.0, 1.0, 0.0))
	var mat := ShaderMaterial.new()
	mat.shader = SHADER
	mat.resource_name = source.resource_name if source != null and not source.resource_name.is_empty() else "mat_env_default"
	mat.set_shader_parameter("albedo_tex", _white)
	mat.set_shader_parameter("normal_tex", _flat)
	mat.set_shader_parameter("orm_tex", _neutral)
	mat.set_shader_parameter("soft_surface", true)
	mat.set_shader_parameter("fill", 0.0)
	mat.set_shader_parameter("vcol_strength", 1.0)
	if source is BaseMaterial3D:
		var src := source as BaseMaterial3D
		mat.set_shader_parameter("base_color", src.albedo_color)
		mat.set_shader_parameter("rough", src.roughness)
		mat.set_shader_parameter("metal", src.metallic)
		mat.set_shader_parameter("orm_rough_factor", src.roughness)
		mat.set_shader_parameter("orm_metal_factor", src.metallic)
		if src.albedo_texture != null:
			mat.set_shader_parameter("albedo_tex", src.albedo_texture)
		if src.normal_texture != null:
			mat.set_shader_parameter("normal_tex", src.normal_texture)
			mat.set_shader_parameter("normal_strength", src.normal_scale)
		if source is ORMMaterial3D and (source as ORMMaterial3D).orm_texture != null:
			mat.set_shader_parameter("orm_tex", (source as ORMMaterial3D).orm_texture)
			mat.set_shader_parameter("orm_strength", 1.0)
		elif src.roughness_texture != null:
			mat.set_shader_parameter("orm_tex", src.roughness_texture)
			mat.set_shader_parameter("orm_strength", 1.0)
		if src.ao_texture != null:
			mat.set_shader_parameter("ao_tex", src.ao_texture)
			mat.set_shader_parameter("separate_ao", true)
	elif source is ShaderMaterial:
		for entry in SHADER.get_shader_uniform_list():
			var value = (source as ShaderMaterial).get_shader_parameter(entry.name)
			if value != null:
				mat.set_shader_parameter(entry.name, value)
	apply_family(mat)
	return mat

static func apply_family(mat: ShaderMaterial) -> void:
	var key := mat.resource_name.to_lower()
	var highlight := 0.20
	if "alloy" in key or "metal" in key:
		highlight = 0.55
	elif "clay" in key or "ceramic" in key or "amphora" in key:
		highlight = 0.42
	elif "fiber" in key or "bark" in key:
		highlight = 0.06
	mat.set_shader_parameter("specular_strength", highlight)
