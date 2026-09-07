extends RefCounted
## FR-44: concrete role-card aliases resolve here, never via an NPC resource bucket.

const SPECS := [
	["food_burger", "汉堡", "Burger", ["burger", "hamburger"], "food", 45, 20, 0, "burger"],
	["food_cheeseburger", "芝士汉堡", "Cheeseburger", ["cheeseburger"], "food", 48, 18, 0, "burger"],
	["food_sandwich", "三明治", "Sandwich", ["sandwich"], "food", 40, 12, 0, "wrap"],
	["food_bread", "面包", "Bread", ["bread"], "food", 30, 0, 8, "wrap"],
	["food_pizza", "披萨", "Pizza", ["pizza"], "food", 48, 20, 0, "wrap"],
	["food_taco", "塔可", "Taco", ["taco"], "food", 38, 20, 0, "wrap"],
	["food_burrito", "卷饼", "Burrito", ["burrito"], "food", 48, 20, 0, "wrap"],
	["food_fries", "薯条", "Fries", ["fries"], "food", 30, 14, 0, "wrap"],
	["drink_coffee", "热咖啡", "Hot coffee", ["coffee"], "drink", 0, 24, 28, "drink"],
	["drink_soda", "汽水", "Soda", ["soda"], "drink", 0, 0, 32, "drink"],
	["drink_bottled_water", "瓶装水", "Bottled water", ["water", "bottle of water", "bottled water", "water bottle"], "drink", 0, 0, 35, "drink"],
	["drink_juice", "果汁", "Juice", ["juice"], "drink", 8, 0, 28, "drink"],
	["drink_canteen", "水壶", "Canteen", ["canteen"], "drink", 0, 0, 25, "drink"],
	["food_chips", "薯片", "Chips", ["chips"], "food", 25, 0, 5, "wrap"],
	["food_gum", "口香糖", "Gum", ["gum"], "food", 0, 0, 8, "wrap"],
	["home_batteries", "电池", "Batteries", ["batteries"], "home_consumable", 0, 0, 25, "battery"],
	["home_blanket", "毯子", "Blanket", ["blanket", "extra blanket"], "durable", 0, 20, 0, "blanket"],
	["component_alloy_part", "合金零件", "Alloy part", ["alloy", "alloy parts", "scrap", "metal", "heater part"], "component", 0, 0, 0, "part"],
	["food_legacy_berries", "旧档打包食物", "Packed berries", [], "food", 30, 0, 0, "wrap"],
]
const HOME_SLOTS := {
	"home_bed": {"category": "durable", "name": ["床铺", "Bed"], "position": [-5.0, 0.65, 14.0]},
	"home_heater": {"category": "component", "name": ["加热器维修位", "Heater workbench"], "position": [-3.2, 0.8, 6.6]},
	"home_power": {"category": "home_consumable", "name": ["住所电力位", "Home power station"], "position": [-4.8, 0.8, 11.6]},
	"home_storage": {"category": "storage", "name": ["住处领取箱", "Home delivery chest"], "position": [-10.7, 0.6, 9.5]},
}

static func definitions() -> Dictionary:
	var result := {}
	for spec in SPECS:
		var category: String = spec[4]
		var household := category in ["durable", "component", "home_consumable"]
		result[spec[0]] = {
			"id": spec[0], "name": [spec[1], spec[2]], "aliases": spec[3], "category": category,
			"carry_category": "residence" if household else "consumable", "stack_limit": 1 if category == "durable" or spec[0] == "drink_canteen" else 2,
			"slot_cost": 1, "effects": {"food": float(spec[5]), "warmth": float(spec[6]), "energy": float(spec[7])},
			"visual": spec[8], "uses": 2 if spec[0] == "drink_canteen" else 1,
			"reward": "entitlement" if category == "durable" else ("need_capped" if category == "component" else "quantity"),
			"stock": "unique" if category == "durable" else ("unlimited" if category == "component" else "daily"),
			"stock_limit": 6, "loss_allowed": category != "durable", "loss_priority": 1 if household else 0,
			"home_slot": "home_bed" if category == "durable" else ("home_heater" if category == "component" else "home_power"),
			"can_reclaim": household, "transfer_to": ["rowan"] if spec[0] == "drink_bottled_water" else [],
			"progress": 1 if category == "component" else 0,
		}
	return result

static func label(names: Array) -> String:
	return str(names[0] if TranslationServer.get_locale().begins_with("zh") else names[1])
