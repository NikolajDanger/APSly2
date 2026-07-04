from typing import NamedTuple, Optional
from enum import Enum

from BaseClasses import Item, ItemClassification

from .Constants import EPISODES

class Sly2Item(Item):
    game: str = "Sly 2: Band of Thieves"

class Trap(Enum):
    """Trap items. `duration` is in seconds; None means an instant effect."""
    SLY_1        = ("Sly 1 Trap",        None)
    ENERGY_DRAIN = ("Energy Drain Trap", None)
    SLOW_MO      = ("Slow-mo Trap",      10)
    SUGAR_RUSH   = ("Sugar Rush Trap",   10)
    ICE          = ("Ice Trap",          15)
    NOISE        = ("Noise Trap",        10)

    def __init__(self, item_name: str, duration: Optional[int]):
        self.item_name = item_name
        self.duration = duration

    @classmethod
    def from_item_name(cls, name: str) -> "Trap":
        for trap in cls:
            if trap.item_name == name:
                return trap
        raise KeyError(name)

class Sly2ItemData(NamedTuple):
    name: str
    code: int
    category: str
    classification: ItemClassification

# The way I chose to do this is super nice-looking, but it also won't play nice
# with multiworlds generated with a version with a different order of items.

filler_list = [
    ("Coins",                   ItemClassification.filler,      "Filler"),
]

sly_powerups = [
    ("Smoke Bomb",              ItemClassification.useful,      "Power-Up"),
    ("Combat Dodge",            ItemClassification.useful,      "Power-Up"),
    ("Stealth Slide",           ItemClassification.useful,      "Power-Up"),
    ("Alarm Clock",             ItemClassification.progression, "Power-Up"),
    ("Paraglider",              ItemClassification.progression, "Power-Up"),
    ("Silent Obliteration",     ItemClassification.useful,      "Power-Up"),
    ("Thief Reflexes",          ItemClassification.useful,      "Power-Up"),
    ("Feral Pounce",            ItemClassification.progression, "Power-Up"),
    ("Knockout Dive",           ItemClassification.useful,      "Power-Up"),
    ("Insanity Strike",         ItemClassification.useful,      "Power-Up"),
    ("Voltage Attack",          ItemClassification.useful,      "Power-Up"),
    ("Long Toss",               ItemClassification.useful,      "Power-Up"),
    ("Rage Bomb",               ItemClassification.useful,      "Power-Up"),
    ("Music Box",               ItemClassification.useful,      "Power-Up"),
    ("Lightning Spin",          ItemClassification.useful,      "Power-Up"),
    ("Shadow Power",            ItemClassification.useful,      "Power-Up"),
    ("TOM",                     ItemClassification.useful,      "Power-Up"),
    ("Mega Jump",               ItemClassification.progression, "Power-Up"),
    ("Time Rush",               ItemClassification.useful,      "Power-Up"),
]

bentley_powerups = [
    ("Trigger Bomb",            ItemClassification.useful,      "Power-Up"),
    ("Size Destabilizer",       ItemClassification.useful,      "Power-Up"),
    ("Snooze Bomb",             ItemClassification.useful,      "Power-Up"),
    ("Adrenaline Burst",        ItemClassification.useful,      "Power-Up"),
    ("Health Extractor",        ItemClassification.useful,      "Power-Up"),
    ("Hover Pack",              ItemClassification.progression, "Power-Up"),
    ("Reduction Bomb",          ItemClassification.useful,      "Power-Up"),
    ("Temporal Lock",           ItemClassification.useful,      "Power-Up"),
]

murray_powerups = [
    ("Fists of Flame",          ItemClassification.useful,      "Power-Up"),
    ("Turnbuckle Launch",       ItemClassification.progression, "Power-Up"),
    ("Juggernaut Throw",        ItemClassification.useful,      "Power-Up"),
    ("Atlas Strength",          ItemClassification.useful,      "Power-Up"),
    ("Raging Inferno Flop",     ItemClassification.useful,      "Power-Up"),
    ("Berserker Charge",        ItemClassification.useful,      "Power-Up"),
    ("Guttural Roar",           ItemClassification.useful,      "Power-Up"),
    ("Diablo Fire Slam",        ItemClassification.useful,      "Power-Up"),
]

powerup_list = sly_powerups + bentley_powerups + murray_powerups

clockwerk_parts_list = [
    (f"Clockwerk {s}",           ItemClassification.progression, "Clockwerk Part")
    for s in [
        "Tail Feathers",
        "Wing (Right)",
        "Wing (Left)",
        "Heart (Right Half)",
        "Heart (Left Half)",
        "Eye (Right)",
        "Eye (Left)",
        "Lung (Right)",
        "Lung (Left)",
        "Stomach",
        "Talons",
        "Hate Chip",
        "Brain",

        "Beak",
        "Ribcage",
        "Skull",
        "Leg (Right)",
        "Leg (Left)",
        "Neck",
        "Pelvis",

        "Feather"
    ]
]

bottle_list = [
    (f"Bottle - {e}",           ItemClassification.progression, "Bottles")
    for e in EPISODES.keys()
] + [
    (f"{i} bottles - {e}",      ItemClassification.progression, "Bottles")
    for e in EPISODES.keys() for i in range(2,31)
]

progressive_episode_list = [
    (f"Progressive {e}",        ItemClassification.progression, "Episode")
    for e in EPISODES.keys()
]

# Appended last so existing item IDs stay stable.
trap_list = [
    (trap.item_name,            ItemClassification.trap,        "Trap")
    for trap in Trap
]

item_list = (
    filler_list+
    powerup_list+
    clockwerk_parts_list+
    bottle_list+
    progressive_episode_list+
    trap_list
)

base_code = 123_000

item_dict = {
    name: Sly2ItemData(name, base_code+code, category, classification)
    for code, (name, classification, category) in enumerate(item_list)
}

item_groups = {
    key: {item.name for item in item_dict.values() if item.category == key}
    for key in [
        "Filler",
        "Power-Up",
        "Bottles",
        "Episode",
        "Clockwerk Part",
        "Trap"
    ]
}

item_groups.update({
    "Episodes":          item_groups["Episode"],
    "Gadgets":           item_groups["Power-Up"],
    "Clockwerk Parts":   item_groups["Clockwerk Part"],
    "Sly's Gadgets":     {name for name, _, _ in sly_powerups},
    "Bentley's Gadgets": {name for name, _, _ in bentley_powerups},
    "Murray's Gadgets":  {name for name, _, _ in murray_powerups},
})

def from_id(item_id: int) -> Sly2ItemData:
    matching = [item for item in item_dict.values() if item.code == item_id]
    if len(matching) == 0:
        raise ValueError(f"No item data for item id '{item_id}'")
    assert len(matching) < 2, f"Multiple item data with id '{item_id}'. Please report."
    return matching[0]
