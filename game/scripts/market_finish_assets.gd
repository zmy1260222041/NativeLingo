extends RefCounted
## Shared Main/MarketCorner dressing. Product bases sit on the baked counter top.
const GOODS := [
	["burger", Vector3(-1.00, 1.10, 0.49), -0.20],
	["wrap", Vector3(-0.54, 1.10, 0.26), 0.35],
	["drink", Vector3(1.05, 1.10, 0.42), -0.25],
]

static func dress_stall(stall: Node3D) -> void:
	if stall.has_node("CounterDisplay"):
		return
	var display := Node3D.new()
	display.name = "CounterDisplay"
	stall.add_child(display)
	for spec in GOODS:
		var packed := load("res://assets/environment/prp_market_%s_v01.glb" % spec[0]) as PackedScene
		if packed == null:
			push_error("Missing baked counter product: " + spec[0])
			continue
		var item := packed.instantiate() as Node3D
		display.add_child(item)
		item.position = spec[1]
		item.rotation.y = spec[2]
		_set_shadows(item)

static func tree_collision(tree: Node3D) -> void:
	var body := StaticBody3D.new()
	body.name = "FittedCollision"
	body.collision_layer = 1
	body.collision_mask = 0
	tree.add_child(body)
	var shape := CollisionShape3D.new()
	var trunk := CylinderShape3D.new()
	trunk.radius = 0.32
	trunk.height = 1.8
	shape.shape = trunk
	shape.position.y = 0.90
	body.add_child(shape)

static func _set_shadows(node: Node) -> void:
	if node is MeshInstance3D:
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	for child in node.get_children():
		_set_shadows(child)
