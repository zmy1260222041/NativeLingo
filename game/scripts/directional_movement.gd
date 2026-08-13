class_name DirectionalMovement
extends RefCounted
## Pure direction rules shared by PlayerController and standalone tests.

const LARGE_TURN_ANGLE := deg_to_rad(135.0)
const DIRECTION_EPSILON_SQUARED := 0.01

static func is_large_change(from_direction: Vector3, to_direction: Vector3) -> bool:
	var from_planar := Vector3(from_direction.x, 0.0, from_direction.z)
	var to_planar := Vector3(to_direction.x, 0.0, to_direction.z)
	if from_planar.length_squared() <= DIRECTION_EPSILON_SQUARED or to_planar.length_squared() <= DIRECTION_EPSILON_SQUARED:
		return false
	return from_planar.normalized().angle_to(to_planar.normalized()) >= LARGE_TURN_ANGLE

static func signed_planar_angle(from_direction: Vector3, to_direction: Vector3) -> float:
	var from_planar := Vector3(from_direction.x, 0.0, from_direction.z)
	var to_planar := Vector3(to_direction.x, 0.0, to_direction.z)
	if from_planar.length_squared() <= DIRECTION_EPSILON_SQUARED or to_planar.length_squared() <= DIRECTION_EPSILON_SQUARED:
		return 0.0
	from_planar = from_planar.normalized()
	to_planar = to_planar.normalized()
	return atan2(from_planar.cross(to_planar).y, from_planar.dot(to_planar))

static func rotate_toward_planar(from_direction: Vector3, to_direction: Vector3, max_angle: float) -> Vector3:
	var from_planar := Vector3(from_direction.x, 0.0, from_direction.z)
	var to_planar := Vector3(to_direction.x, 0.0, to_direction.z)
	if to_planar.length_squared() <= DIRECTION_EPSILON_SQUARED:
		return from_planar.normalized() if from_planar.length_squared() > DIRECTION_EPSILON_SQUARED else Vector3.FORWARD
	if from_planar.length_squared() <= DIRECTION_EPSILON_SQUARED:
		return to_planar.normalized()
	var signed_angle := signed_planar_angle(from_planar, to_planar)
	var applied_angle := clampf(signed_angle, -absf(max_angle), absf(max_angle))
	return from_planar.normalized().rotated(Vector3.UP, applied_angle).normalized()

static func local_yaw_for_world_direction(body_basis: Basis, world_direction: Vector3) -> float:
	var local_direction := body_basis.inverse() * world_direction
	local_direction.y = 0.0
	if local_direction.length_squared() <= DIRECTION_EPSILON_SQUARED:
		return 0.0
	local_direction = local_direction.normalized()
	# The authored character forward axis is local -Z.
	return atan2(-local_direction.x, -local_direction.z)
