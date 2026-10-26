from typing import NamedTuple, Optional
from enum import Enum

from BaseClasses import Item, ItemClassification

from .Constants import EPISODES
from .Names import (
  ItemCategory,
  ItemName,
  bottle_item,
  clockwerk_part,
  progressive_episode,
)

class Sly2Item(Item):
  game: str = "Sly 2: Band of Thieves"

class Trap(Enum):
  """Trap items. `duration` is the default in seconds; None is instant."""
  SLY_1        = ("Sly 1 Trap",        None)
  ENERGY_DRAIN = ("Energy Drain Trap", None)
  SLOW_MO      = ("Slow-mo Trap",      15)
  SUGAR_RUSH   = ("Sugar Rush Trap",   15)
  ICE          = ("Ice Trap",          20)
  NOISE        = ("Noise Trap",        10)

  def __init__(self, item_name: str, duration: Optional[int]) -> None:
    self.item_name = item_name
    self.duration = duration

  @property
  def key(self) -> str:
    return self.item_name.lower().replace("-", "_").replace(" ", "_")

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
  (ItemName.COINS, ItemClassification.filler, ItemCategory.FILLER),
]

sly_powerups = [
  (ItemName.SMOKE_BOMB,           ItemClassification.useful),
  (ItemName.COMBAT_DODGE,         ItemClassification.useful),
  (ItemName.STEALTH_SLIDE,        ItemClassification.useful),
  (ItemName.ALARM_CLOCK,          ItemClassification.progression),
  (ItemName.PARAGLIDER,           ItemClassification.progression),
  (ItemName.SILENT_OBLITERATION,  ItemClassification.useful),
  (ItemName.THIEF_REFLEXES,       ItemClassification.useful),
  (ItemName.FERAL_POUNCE,         ItemClassification.progression),
  (ItemName.KNOCKOUT_DIVE,        ItemClassification.useful),
  (ItemName.INSANITY_STRIKE,      ItemClassification.useful),
  (ItemName.VOLTAGE_ATTACK,       ItemClassification.useful),
  (ItemName.LONG_TOSS,            ItemClassification.useful),
  (ItemName.RAGE_BOMB,            ItemClassification.useful),
  (ItemName.MUSIC_BOX,            ItemClassification.useful),
  (ItemName.LIGHTNING_SPIN,       ItemClassification.useful),
  (ItemName.SHADOW_POWER,         ItemClassification.useful),
  (ItemName.TOM,                  ItemClassification.useful),
  (ItemName.MEGA_JUMP,            ItemClassification.progression),
  (ItemName.TIME_RUSH,            ItemClassification.useful),
]

bentley_powerups = [
  (ItemName.TRIGGER_BOMB,         ItemClassification.useful),
  (ItemName.SIZE_DESTABILIZER,    ItemClassification.useful),
  (ItemName.SNOOZE_BOMB,          ItemClassification.useful),
  (ItemName.ADRENALINE_BURST,     ItemClassification.useful),
  (ItemName.HEALTH_EXTRACTOR,     ItemClassification.useful),
  (ItemName.HOVER_PACK,           ItemClassification.progression),
  (ItemName.REDUCTION_BOMB,       ItemClassification.useful),
  (ItemName.TEMPORAL_LOCK,        ItemClassification.useful),
]

murray_powerups = [
  (ItemName.FISTS_OF_FLAME,       ItemClassification.useful),
  (ItemName.TURNBUCKLE_LAUNCH,    ItemClassification.progression),
  (ItemName.JUGGERNAUT_THROW,     ItemClassification.useful),
  (ItemName.ATLAS_STRENGTH,       ItemClassification.useful),
  (ItemName.RAGING_INFERNO_FLOP,  ItemClassification.useful),
  (ItemName.BERSERKER_CHARGE,     ItemClassification.useful),
  (ItemName.GUTTURAL_ROAR,        ItemClassification.useful),
  (ItemName.DIABLO_FIRE_SLAM,     ItemClassification.useful),
]

powerup_list = [
  (name, classification, ItemCategory.POWER_UP)
  for name, classification in (
    sly_powerups + bentley_powerups + murray_powerups
  )
]

# Clockwerk parts are drawn for the pool in tiers (see gen_clockwerk): core
# (in-game) parts fill small pools, additional parts join once core runs out,
# silly parts only join once the pool exceeds 100, and repeatable parts pad
# whatever's left (weighted toward the iconic Feather) so huge pools aren't one
# item repeated.
CLOCKWERK_CORE = [clockwerk_part(s) for s in [
  "Tail Feathers", "Wing (Right)", "Wing (Left)", "Heart (Right Half)",
  "Heart (Left Half)", "Eye (Right)", "Eye (Left)", "Lung (Right)",
  "Lung (Left)", "Stomach", "Talons", "Hate Chip", "Brain",
]]
CLOCKWERK_ADDITIONAL = [clockwerk_part(s) for s in [
  "Beak", "Ribcage", "Skull", "Leg (Right)", "Leg (Left)", "Neck", "Pelvis",
  "Spine", "Jaw",
]]
CLOCKWERK_SILLY = [clockwerk_part(s) for s in [
  "Gizzard", "Wishbone", "Spleen", "Gyroscope", "Power Core", "Servo Motor",
  "Mild Annoyance Chip", "Tongue", "Small Intestines", "Large Intestines",
  "Kidney (Left)", "Kidney (Right)", "Ureter", "Proventriculus", "Cloaca",
  "Cervical Air Sac", "Interclavicular Air Sac", "Anterior Thoracic Air Sac",
  "Posterior Thoracic Air Sac", "Abdominal Air Sac", "CPU Cooling Fan",
  "Circuit Board", "Syrinx", "Uropygial Gland", "Pygostyle", "Keel", "Crop",
  "Nictitating Membrane", "Heat Sink", "Motherboard",
]]
# (name, draw weight); Feather is weighted to ~half of the padding.
CLOCKWERK_REPEATABLE = [
  (clockwerk_part("Feather"), 3), (clockwerk_part("Bone"), 1),
  (clockwerk_part("Screw"), 1), (clockwerk_part("Cog"), 1),
]

clockwerk_parts_list = [
  (name, ItemClassification.progression, ItemCategory.CLOCKWERK_PART)
  for name in (
    CLOCKWERK_CORE + CLOCKWERK_ADDITIONAL + CLOCKWERK_SILLY
    + [n for n, _ in CLOCKWERK_REPEATABLE]
  )
]

bottle_list = [
  (bottle_item(1, e), ItemClassification.progression, ItemCategory.BOTTLES)
  for e in EPISODES.keys()
] + [
  (bottle_item(i, e), ItemClassification.progression, ItemCategory.BOTTLES)
  for e in EPISODES.keys() for i in range(2,31)
]

progressive_episode_list = [
  (progressive_episode(e), ItemClassification.progression,
   ItemCategory.EPISODE)
  for e in EPISODES.keys()
]

# Appended last so existing item IDs stay stable.
trap_list = [
  (trap.item_name, ItemClassification.trap, ItemCategory.TRAP)
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
    ItemCategory.FILLER,
    ItemCategory.POWER_UP,
    ItemCategory.BOTTLES,
    ItemCategory.EPISODE,
    ItemCategory.CLOCKWERK_PART,
    ItemCategory.TRAP
  ]
}

item_groups.update({
  "Episodes":          item_groups[ItemCategory.EPISODE],
  "Gadgets":           item_groups[ItemCategory.POWER_UP],
  "Clockwerk Parts":   item_groups[ItemCategory.CLOCKWERK_PART],
  "Sly's Gadgets":     {name for name, _ in sly_powerups},
  "Bentley's Gadgets": {name for name, _ in bentley_powerups},
  "Murray's Gadgets":  {name for name, _ in murray_powerups},
})

def ordered_group(group: str) -> list[str]:
  """Group members in item_dict order; set iteration order varies between
  processes, which breaks generation determinism."""
  members = item_groups[group]
  return [name for name in item_dict if name in members]

_items_by_id = {item.code: item for item in item_dict.values()}

def from_id(item_id: int) -> Sly2ItemData:
  if item_id not in _items_by_id:
    raise ValueError(f"No item data for item id '{item_id}'")
  return _items_by_id[item_id]
