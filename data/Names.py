"""Name constants and formatters for AP items, locations and regions, so
nothing else builds or matches these names. In-game strings are a separate
and don't belong here."""

VICTORY = "Victory"
MENU_REGION = "Menu"

class ItemName:
  COINS = "Coins"

  SMOKE_BOMB = "Smoke Bomb"
  COMBAT_DODGE = "Combat Dodge"
  STEALTH_SLIDE = "Stealth Slide"
  ALARM_CLOCK = "Alarm Clock"
  PARAGLIDER = "Paraglider"
  SILENT_OBLITERATION = "Silent Obliteration"
  THIEF_REFLEXES = "Thief Reflexes"
  FERAL_POUNCE = "Feral Pounce"
  KNOCKOUT_DIVE = "Knockout Dive"
  INSANITY_STRIKE = "Insanity Strike"
  VOLTAGE_ATTACK = "Voltage Attack"
  LONG_TOSS = "Long Toss"
  RAGE_BOMB = "Rage Bomb"
  MUSIC_BOX = "Music Box"
  LIGHTNING_SPIN = "Lightning Spin"
  SHADOW_POWER = "Shadow Power"
  TOM = "TOM"
  MEGA_JUMP = "Mega Jump"
  TIME_RUSH = "Time Rush"

  TRIGGER_BOMB = "Trigger Bomb"
  SIZE_DESTABILIZER = "Size Destabilizer"
  SNOOZE_BOMB = "Snooze Bomb"
  ADRENALINE_BURST = "Adrenaline Burst"
  HEALTH_EXTRACTOR = "Health Extractor"
  HOVER_PACK = "Hover Pack"
  REDUCTION_BOMB = "Reduction Bomb"
  TEMPORAL_LOCK = "Temporal Lock"

  FISTS_OF_FLAME = "Fists of Flame"
  TURNBUCKLE_LAUNCH = "Turnbuckle Launch"
  JUGGERNAUT_THROW = "Juggernaut Throw"
  ATLAS_STRENGTH = "Atlas Strength"
  RAGING_INFERNO_FLOP = "Raging Inferno Flop"
  BERSERKER_CHARGE = "Berserker Charge"
  GUTTURAL_ROAR = "Guttural Roar"
  DIABLO_FIRE_SLAM = "Diablo Fire Slam"

class ItemCategory:
  FILLER = "Filler"
  POWER_UP = "Power-Up"
  BOTTLES = "Bottles"
  EPISODE = "Episode"
  CLOCKWERK_PART = "Clockwerk Part"
  TRAP = "Trap"

class LocationCategory:
  JOB = "Job"
  BOTTLE = "Bottle"
  VAULT = "Vault"
  TREASURE = "Treasure"
  PURCHASE = "Purchase"
  PICKPOCKET = "Pickpocket"
  TASK = "Task"

class EpisodeName:
  THE_BLACK_CHATEAU = "The Black Chateau"
  A_STARRY_EYED_ENCOUNTER = "A Starry Eyed Encounter"
  THE_PREDATOR_AWAKENS = "The Predator Awakens"
  JAILBREAK = "Jailbreak"
  A_TANGLED_WEB = "A Tangled Web"
  HE_WHO_TAMES_THE_IRON_HORSE = "He Who Tames the Iron Horse"
  MENACE_FROM_THE_NORTH_EH = "Menace from the North, Eh!"
  ANATOMY_FOR_DISASTER = "Anatomy for Disaster"

def clockwerk_part(part: str) -> str:
  return f"Clockwerk {part}"

def bottle_item(count: int, episode: str) -> str:
  if count == 1:
    return f"Bottle - {episode}"
  return f"{count} bottles - {episode}"

def parse_bottle_item(name: str) -> tuple[int, str]:
  amount, sep, episode = name.partition(" - ")
  if not sep:
    raise ValueError(f"Not a bottle item: '{name}'")
  if amount == "Bottle":
    return 1, episode
  count, sep, word = amount.partition(" ")
  if word != "bottles" or not count.isdigit():
    raise ValueError(f"Not a bottle item: '{name}'")
  return int(count), episode

def progressive_episode(episode: str) -> str:
  return f"Progressive {episode}"

def parse_progressive_episode(name: str) -> str:
  prefix = "Progressive "
  if not name.startswith(prefix):
    raise ValueError(f"Not a progressive episode item: '{name}'")
  return name[len(prefix):]

def job_location(episode: str, job: str) -> str:
  return f"{episode} - {job}"

def task_location(episode: str, job: str, task: str) -> str:
  return f"{episode} - {job} - {task}"

def vault_location(episode: str) -> str:
  return f"{episode} - Vault"

def treasure_location(episode: str, treasure: str) -> str:
  return f"{episode} - {treasure}"

def thiefnet_location(number: int) -> str:
  return f"ThiefNet {number:02}"

def pickpocket_location(loot: str) -> str:
  return f"Pickpocket {loot}"

def bottle_location(episode: str, number: int) -> str:
  return f"{episode} - Bottle #{number:02}"

def bottles_collected_location(episode: str, count: int) -> str:
  return f"{episode} - {count:02} bottles collected"

def episode_location_prefix(episode: str) -> str:
  return f"{episode} - "

def episode_region(number: int, section: int) -> str:
  return f"Episode {number} ({section})"
