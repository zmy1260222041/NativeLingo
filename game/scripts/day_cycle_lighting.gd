class_name DayCycleLighting
extends RefCounted
## Encapsulated day-cycle lighting. Clock hours come from GameState (08:00–22:00).
## Sunny warm daylight holds through 18:00, then eases into sunset and night.

const SUNNY_UNTIL_HOUR := 18.0
const NIGHT_FROM_HOUR := 20.5

enum Phase { SUNNY, SUNSET, NIGHT }


class Look:
	var sky_top := Color.WHITE
	var sky_horizon := Color.WHITE
	var ground_horizon := Color.WHITE
	var ground_bottom := Color.WHITE
	var sky_curve := 0.09
	var sun_angle_max := 58.0
	var sun_curve := 0.09
	var sky_energy := 1.28
	var ambient := Color.WHITE
	var ambient_energy := 0.62
	var sun_color := Color.WHITE
	var sun_energy := 1.32
	var sun_altitude := -62.0
	var sun_azimuth := -26.0
	var fog := Color("cde3f2")
	var fog_density := 0.0034
	var fog_sky_affect := 0.08
	var fog_aerial := 0.06
	var fog_sun_scatter := 0.05
	var fog_height := 16.0
	var fog_height_density := -0.0018

	func blend(other: Look, t: float) -> Look:
		var out := Look.new()
		var k := clampf(t, 0.0, 1.0)
		out.sky_top = sky_top.lerp(other.sky_top, k)
		out.sky_horizon = sky_horizon.lerp(other.sky_horizon, k)
		out.ground_horizon = ground_horizon.lerp(other.ground_horizon, k)
		out.ground_bottom = ground_bottom.lerp(other.ground_bottom, k)
		out.sky_curve = lerpf(sky_curve, other.sky_curve, k)
		out.sun_angle_max = lerpf(sun_angle_max, other.sun_angle_max, k)
		out.sun_curve = lerpf(sun_curve, other.sun_curve, k)
		out.sky_energy = lerpf(sky_energy, other.sky_energy, k)
		out.ambient = ambient.lerp(other.ambient, k)
		out.ambient_energy = lerpf(ambient_energy, other.ambient_energy, k)
		out.sun_color = sun_color.lerp(other.sun_color, k)
		out.sun_energy = lerpf(sun_energy, other.sun_energy, k)
		out.sun_altitude = lerpf(sun_altitude, other.sun_altitude, k)
		out.sun_azimuth = lerpf(sun_azimuth, other.sun_azimuth, k)
		out.fog = fog.lerp(other.fog, k)
		out.fog_density = lerpf(fog_density, other.fog_density, k)
		out.fog_sky_affect = lerpf(fog_sky_affect, other.fog_sky_affect, k)
		out.fog_aerial = lerpf(fog_aerial, other.fog_aerial, k)
		out.fog_sun_scatter = lerpf(fog_sun_scatter, other.fog_sun_scatter, k)
		out.fog_height = lerpf(fog_height, other.fog_height, k)
		out.fog_height_density = lerpf(fog_height_density, other.fog_height_density, k)
		return out

	func apply(env: Environment, sky: ProceduralSkyMaterial, sun: DirectionalLight3D) -> void:
		sky.sky_top_color = sky_top
		sky.sky_horizon_color = sky_horizon
		sky.ground_horizon_color = ground_horizon
		sky.ground_bottom_color = ground_bottom
		sky.sky_curve = sky_curve
		sky.sun_angle_max = sun_angle_max
		sky.sun_curve = sun_curve
		sky.energy_multiplier = sky_energy
		env.ambient_light_color = ambient
		env.ambient_light_energy = ambient_energy
		sun.light_color = sun_color
		sun.light_energy = sun_energy
		sun.rotation_degrees = Vector3(sun_altitude, sun_azimuth, 0.0)
		env.fog_light_color = fog
		env.fog_density = fog_density
		env.fog_sky_affect = fog_sky_affect
		env.fog_aerial_perspective = fog_aerial
		env.fog_sun_scatter = fog_sun_scatter
		env.fog_height = fog_height
		env.fog_height_density = fog_height_density


static func phase_at(hours: float) -> Phase:
	if hours < SUNNY_UNTIL_HOUR:
		return Phase.SUNNY
	if hours < NIGHT_FROM_HOUR:
		return Phase.SUNSET
	return Phase.NIGHT


static func glow_amount(hours: float) -> float:
	return clampf(smoothstep(SUNNY_UNTIL_HOUR, NIGHT_FROM_HOUR, hours), 0.0, 1.0)


func sunny_look(hours: float) -> Look:
	var look := Look.new()
	var noon := sin(clampf((hours - 8.0) / 10.0, 0.0, 1.0) * PI)
	look.sky_top = Color("2b86dc")
	look.sky_horizon = Color("c7e4f8")
	look.ground_horizon = Color("e4c48c")
	look.ground_bottom = Color("9a7348")
	look.sun_altitude = lerpf(-54.0, -66.0, noon)
	return look


func sunset_look() -> Look:
	var look := Look.new()
	look.sky_top = Color("3d5f9a")
	look.sky_horizon = Color("e3a06d")
	look.ground_horizon = Color("d27c68")
	look.ground_bottom = Color("5a3a3a")
	look.sky_curve = 0.16
	look.sun_angle_max = 42.0
	look.sky_energy = 0.92
	look.ambient = Color("c4a090")
	look.ambient_energy = 0.44
	look.sun_color = Color("ffb07a")
	look.sun_energy = 0.62
	look.sun_altitude = -22.0
	look.fog = Color("c9b09a")
	look.fog_density = 0.0042
	look.fog_sky_affect = 0.14
	return look


func night_look() -> Look:
	var look := Look.new()
	look.sky_top = Color("121a35")
	look.sky_horizon = Color("34335e")
	look.ground_horizon = Color("2a2438")
	look.ground_bottom = Color("1a1524")
	look.sky_curve = 0.22
	look.sun_angle_max = 18.0
	look.sky_energy = 0.42
	look.ambient = Color("59618b")
	look.ambient_energy = 0.28
	look.sun_color = Color("8aa0c8")
	look.sun_energy = 0.08
	look.sun_altitude = -6.0
	look.fog = Color("4a4e72")
	look.fog_density = 0.0050
	look.fog_sky_affect = 0.18
	look.fog_aerial = 0.10
	return look


func look_at(hours: float) -> Look:
	if hours <= SUNNY_UNTIL_HOUR:
		return sunny_look(hours)
	var sunset := sunset_look()
	if hours >= NIGHT_FROM_HOUR:
		return night_look()
	var span := NIGHT_FROM_HOUR - SUNNY_UNTIL_HOUR
	var t := clampf((hours - SUNNY_UNTIL_HOUR) / span, 0.0, 1.0)
	# First half of dusk keeps warmth while the sun drops; second half goes night.
	if t < 0.45:
		return sunny_look(SUNNY_UNTIL_HOUR).blend(sunset, t / 0.45)
	return sunset.blend(night_look(), (t - 0.45) / 0.55)


func apply(env: Environment, sky: ProceduralSkyMaterial, sun: DirectionalLight3D, hours: float) -> float:
	look_at(hours).apply(env, sky, sun)
	return glow_amount(hours)
