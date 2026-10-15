from enum import IntEnum
from typing import (
  Optional, NamedTuple, Tuple, Dict, List, Iterator, Generator, Deque
)
import struct
import sys
from contextlib import contextmanager
from logging import Logger
from collections import deque
from time import time
import traceback

from .pcsx2_interface.pine import (
  Pine, PineConnectionError, DuplicateConnectionError
)
from .LootInstall import LootInstaller
from .MenuIcons import MenuIconInstaller
from .data.Constants import (
  MENU_RETURN_DATA,
  ADDRESSES,
  EPISODES,
  TASKS,
  HUB_MAPS,
  LOOT_IDS,
  MEGA_JUMP_GADGET_ID,
  MEGA_JUMP_UNLOAD_CALL,
  STALE_JOB_TRIGGERS,
  PEDESTAL_VTABLE,
  INTERACTABLE_NEXT,
  PEDESTAL_USERS,
  SLY_USER_BIT,
  ENTITY_MANAGER_FREE,
  ENTITY_SLOT,
  ENTITY_NEXT,
  ENTITY_PREV,
  ENTITY_FIRST_CHILD,
  ENTITY_LAST_CHILD,
  ENTITY_CHILD_LINK,
  SLY_BACK_NODE,
  TREASURE_VTABLE,
  CAVE_BLOB,
  CAVE_HOOK_ENTRY,
  CAVE_HOOK_ORIG,
  CAVE_HOOK_ORIG_WORD,
  CAVE_PATCH_SLOTS,
  CAVE_VAULT_MARKER,
  VAULT_MARKER_PATCH_SITE,
  VAULT_MARKER_ORIG,
  CAVE_THIEFNET_COLORS,
  THIEFNET_COLORS_SITE,
  THIEFNET_COLORS_ORIG,
  THIEFNET_TEXT_VANILLA,
  THIEFNET_NAME_COLOR,
  THIEFNET_NAME_COLOR_RELOC,
  THIEFNET_COLORS_FLAG,
  GLYPH_TABLE_ALT,
  MENU_ICON_CAVE,
  MENU_ICON_TABLE,
  COIN_POP_INTERVAL,
  DEATH_INFO_TEMPLATE,
  THIEFNET_DESCRIPTION_FORMAT,
  THIEFNET_DESCRIPTION_FORMAT_VANILLA,
  THIEFNET_NAME_STRIDE,
  THIEFNET_DESCRIPTION_STRIDE,
  INFOBOX_BUFFER_SIZE
)

class Sly2Episode(IntEnum):
  Title_Screen = 0
  The_Black_Chateau = 1
  A_Starry_Eyed_Encounter = 2
  The_Predator_Awakens = 3
  Jailbreak = 4
  A_Tangled_Web = 5
  He_Who_Tames_the_Iron_Horse = 6
  Menace_from_the_North_Eh = 7
  Anatomy_for_Disaster = 8

class PowerUps(NamedTuple):
  trigger_bomb: bool = False
  size_destabilizer: bool = False
  snooze_bomb: bool = False
  adrenaline_burst: bool = False
  health_extractor: bool = False
  hover_pack: bool = False
  reduction_bomb: bool = False
  temporal_lock: bool = False

  fists_of_flame: bool = False
  turnbuckle_launch: bool = False
  juggernaut_throw: bool = False
  atlas_strength: bool = False
  diablo_fire_slam: bool = False
  berserker_charge: bool = False
  guttural_roar: bool = False
  raging_inferno_flop: bool = False

  smoke_bomb: bool = False
  combat_dodge: bool = False
  stealth_slide: bool = False
  alarm_clock: bool = False
  paraglide: bool = False
  silent_obliteration: bool = False
  thief_reflexes: bool = False
  feral_pounce: bool = False

  mega_jump: bool = False
  tornado_strike: bool = False

  knockout_dive: bool = False
  insanity_strike: bool = False
  voltage_attack: bool = False
  long_toss: bool = False
  rage_bomb: bool = False
  music_box: bool = False
  lightning_spin: bool = False
  shadow_power: bool = False

  tom: bool = False
  time_rush: bool = False

# The PS2's main RAM. The first megabyte is kernel space, so a pointer read out
# of the game's heap that lands there is garbage rather than an object. PCSX2
# services a write to an address outside this range with a raw EE write that
# faults inside the emulator itself, so a single bad pointer takes it down
EE_RAM_START = 0x0010_0000
EE_RAM_END = 0x0200_0000
RECENT_WRITES = 64

# No map holds anywhere near this many guards at once; a list longer than this
# is a walk that wandered into freed memory.
MAX_GUARDS = 512
MAX_INTERACTABLES = 64
MAX_ENTITY_CHILDREN = 64

INFOBOX_SECONDS = 10.0
# The string id set_infobox writes; the game uses -1 for none and its own
# ids for the boxes it shows.
INFOBOX_CLIENT_STRING = 1

def in_ee_ram(address: int, size: int = 4) -> bool:
  return EE_RAM_START <= address and address + size <= EE_RAM_END

class CycleCounts(NamedTuple):
  reads: int = 0
  writes: int = 0
  batches: int = 0
  pine_reads: int = 0
  pine_writes: int = 0

class GameInterface():
  """
  Base class for connecting with a pcsx2 game
  """

  pcsx2_interface: Pine = Pine()
  logger: Logger
  game_id_error: Optional[str] = None
  current_game: Optional[str] = None
  addresses: Dict = {}

  def __init__(self, logger: Logger) -> None:
    self.logger = logger
    self.reported_bad_writes = set()
    self.refused_patches = set()
    self._pending_patches: List[Tuple[int, int, int]] = []
    self._defer_patches = False
    self.reported_duplicate = False
    # Dumped when the emulator stops answering. An abort caused by a write can
    # surface a few requests later, so a window is kept rather than just the
    # last write.
    self.recent_writes: Deque[tuple[float, str, str, object, object]] = (
      deque(maxlen=RECENT_WRITES)
    )
    # Values fetched for the current tick, keyed by (address, size) in the
    # 8/4/2/1-byte chunks PINE transfers. Reads are served from here when
    # present, so one batch read at the top of a tick replaces the scattered
    # single reads that would otherwise each cost a round trip.
    self._cache: dict[tuple[int, int], bytes] = {}
    # Memory operations since the last take_cycle_counts. reads/writes count
    # every call whether or not the tick cache served it; the pine_* subset
    # is what actually crossed the socket.
    self.cycle_reads = 0
    self.cycle_writes = 0
    self.cycle_batches = 0
    self.cycle_pine_reads = 0
    self.cycle_pine_writes = 0

  def clear_cache(self) -> None:
    self._cache.clear()

  def take_cycle_counts(self) -> CycleCounts:
    counts = CycleCounts(
      self.cycle_reads, self.cycle_writes, self.cycle_batches,
      self.cycle_pine_reads, self.cycle_pine_writes
    )
    self.cycle_reads = 0
    self.cycle_writes = 0
    self.cycle_batches = 0
    self.cycle_pine_reads = 0
    self.cycle_pine_writes = 0
    return counts

  def prefetch(self, reads: list[tuple[int, int]]) -> None:
    """Batch read (size, address) ranges into the tick cache"""
    chunks = [
      (size, chunk)
      for length, address in reads if in_ee_ram(address, length)
      for size, chunk in Pine._chunks(address, length)
      if (chunk, size) not in self._cache
    ]
    if not chunks:
      return
    self.cycle_batches += 1
    values = self.pcsx2_interface.batch_read(chunks)
    for (size, address), value in zip(chunks, values):
      self._cache[(address, size)] = value.to_bytes(size, "little")

  def invalidate(self, address: int, n: int) -> None:
    """Drop the tick cache for a range the game itself rewrites"""
    end = address + n
    for key in [
      k for k in self._cache if k[0] < end and address < k[0] + k[1]
    ]:
      del self._cache[key]

  def _cache_store(self, address: int, data: bytes) -> None:
    self.invalidate(address, len(data))
    for size, chunk in Pine._chunks(address, len(data)):
      self._cache[(chunk, size)] = data[chunk-address:chunk-address+size]

  def _cached_bytes(self, address: int, n: int) -> Optional[bytes]:
    data = b''
    for size, chunk in Pine._chunks(address, n):
      value = self._cache.get((chunk, size))
      if value is None:
        return None
      data += value
    return data

  def _read_int(self, address: int, size: int) -> int:
    if not in_ee_ram(address, size):
      return 0
    self.cycle_reads += 1
    data = self._cache.get((address, size))
    if data is None:
      self.cycle_pine_reads += 1
      read = {
        1: self.pcsx2_interface.read_int8,
        2: self.pcsx2_interface.read_int16,
        4: self.pcsx2_interface.read_int32
      }[size]
      return read(address)
    return int.from_bytes(data, "little")

  def _batch_read(self, size: int, addresses: list[int]) -> list[int]:
    self.cycle_reads += len(addresses)
    values = {
      a: int.from_bytes(self._cache[(a, size)], "little")
      for a in addresses if (a, size) in self._cache
    }
    missing = [a for a in addresses if a not in values]
    if missing:
      self.cycle_pine_reads += len(missing)
      read = {
        1: self.pcsx2_interface.batch_read_int8,
        2: self.pcsx2_interface.batch_read_int16,
        4: self.pcsx2_interface.batch_read_int32
      }[size]
      values.update(zip(missing, read(missing)))
    return [values[a] for a in addresses]

  def _log_write(
    self, kind: str, address: int | list[int], value: object
  ) -> None:
    # Called exactly when a write is actually issued to PINE.
    # sys._getframe(2) is the method that issued the write, past this
    # helper and the _write primitive, so the report names the actual site.
    if isinstance(address, list):
      self.cycle_pine_writes += len(address)
    else:
      self.cycle_pine_writes += 1
    self.recent_writes.append(
      (time(), sys._getframe(2).f_code.co_name, kind, address, value)
    )

  def crash_report(self) -> list[str]:
    """Recent writes, oldest first. Clears the window so a reconnect loop
    reports each loss once."""
    now = time()
    lines = []
    for at, site, kind, address, value in self.recent_writes:
      if isinstance(address, list):
        where = ", ".join(f"{a:#010x}" for a in address[:4])
        if len(address) > 4:
          where += f", ... ({len(address)} words)"
      else:
        where = f"{address:#010x}"
      lines.append(
        f"  -{now - at:6.3f}s {site} {kind} {where} = "
        f"{self._format_value(value)}"
      )
    self.recent_writes.clear()
    return lines

  @staticmethod
  def _format_value(value: object) -> str:
    if isinstance(value, list):
      shown = ", ".join(
        f"{v:#x}" if isinstance(v, int) else repr(v) for v in value[:4]
      )
      return f"[{shown}{', ...' if len(value) > 4 else ''}]"
    if isinstance(value, str) and len(value) > 32:
      return f"{value[:32]}... ({len(value) // 2} bytes)"
    if isinstance(value, int):
      return f"{value:#x}"
    return repr(value)

  def _writable(self, address: int, size: int = 4) -> bool:
    # Every write path checks writability exactly once per operation, so
    # this doubles as the logical-write counter.
    self.cycle_writes += 1
    if in_ee_ram(address, size):
      return True

    caller = traceback.extract_stack()[-3]
    if caller.name not in self.reported_bad_writes:
      self.reported_bad_writes.add(caller.name)
      self.logger.warning(
        f"Refused write to invalid address {address:#010x} from "
        f"{caller.name} (line {caller.lineno}). "
        "Please tell Nikolaj in the discord channel."
      )
    return False

  def _read8(self, address: int) -> int:
    return self._read_int(address, 1)

  def _read16(self, address: int) -> int:
    return self._read_int(address, 2)

  def _read32(self, address: int) -> int:
    return self._read_int(address, 4)

  def _read_bytes(self, address: int, n: int) -> bytes:
    if not in_ee_ram(address, n):
      return bytes(n)
    self.cycle_reads += 1
    data = self._cached_bytes(address, n)
    if data is None:
      self.cycle_pine_reads += 1
      return self.pcsx2_interface.read_bytes(address, n)
    return data

  def _read_float(self, address: int) -> float:
    return struct.unpack("f", self._read_bytes(address, 4))[0]

  def _batch_read8(self, addresses: list[int]) -> list[int]:
    return self._batch_read(1, addresses)

  def _batch_read16(self, addresses: list[int]) -> list[int]:
    return self._batch_read(2, addresses)

  def _batch_read32(self, addresses: list[int]) -> list[int]:
    return self._batch_read(4, addresses)

  def _needs_write(self, address: int, data: bytes) -> bool:
    """Records the write in the tick cache; False when the cache already
    held exactly these bytes, so the write would be a no-op"""
    if self._cached_bytes(address, len(data)) == data:
      return False
    self._cache_store(address, data)
    return True

  def _write8(self, address: int, value: int) -> None:
    data = (value & 0xFF).to_bytes(1, "little")
    if self._writable(address, 1) and self._needs_write(address, data):
      self._log_write("w8", address, value)
      self.pcsx2_interface.write_int8(address, value)

  def _write16(self, address: int, value: int) -> None:
    data = (value & 0xFFFF).to_bytes(2, "little")
    if self._writable(address, 2) and self._needs_write(address, data):
      self._log_write("w16", address, value)
      self.pcsx2_interface.write_int16(address, value)

  def _write32(self, address: int, value: int) -> None:
    data = (value & 0xFFFF_FFFF).to_bytes(4, "little")
    if self._writable(address) and self._needs_write(address, data):
      self._log_write("w32", address, value)
      self.pcsx2_interface.write_int32(address, value)

  def _write_bytes(self, address: int, value: bytes) -> None:
    if (
      self._writable(address, len(value)) and
      self._needs_write(address, value)
    ):
      self._log_write("wbytes", address, value.hex())
      self.pcsx2_interface.write_bytes(address, value)

  def _write_float(self, address: int, value: float) -> None:
    data = struct.pack("<f", value)
    if self._writable(address) and self._needs_write(address, data):
      self._log_write("wfloat", address, value)
      self.pcsx2_interface.write_float(address, value)

  def safe_patch(self, address: int, value: int, expected: int) -> None:
    """Write a code patch only if the word there is the instruction we mean
    to replace (or already the patch). Refusing on anything else stops a
    wrong address from corrupting code. Inside `batched_patches` the write
    is held back and issued with the others as one PINE message."""
    self._pending_patches.append((address, value, expected))
    if not self._defer_patches:
      self._flush_patches()

  @contextmanager
  def batched_patches(self) -> Generator[None, None, None]:
    """Collect every `safe_patch` in the block into one PINE message, so
    the code patches of one map load reach the cave together."""
    self._defer_patches = True
    try:
      yield
    finally:
      self._defer_patches = False
      self._flush_patches()

  def _flush_patches(self) -> None:
    patches = self._pending_patches
    self._pending_patches = []
    if not patches:
      return
    current = self._batch_read32([address for address, _, _ in patches])
    operations = []
    for (address, value, expected), word in zip(patches, current):
      if word == value:
        continue
      if word == expected:
        operations.append((address, value, expected))
      elif address not in self.refused_patches:
        self.refused_patches.add(address)
        self.logger.warning(
          f"Refused patch at {address:#010x}: found {word:#010x}, "
          f"expected {expected:#010x}. "
          "Please tell Nikolaj in the discord channel."
        )
    if operations:
      # Patches that found no free cave slot are retried next tick.
      self._pending_patches.extend(self._write_patches(operations))

  def flush_patches(self) -> None:
    """Retry any patches deferred because the cave's slots were full."""
    if not self._defer_patches:
      self._flush_patches()

  def _write_patches(
    self, operations: list[tuple[int, int, int]]
  ) -> list[tuple[int, int, int]]:
    self._batch_write32([(a, v) for a, v, _ in operations])
    return []

  def _batch_write32(self, operations: list[tuple[int, int]]) -> None:
    valid = []
    for address, value in operations:
      data = (value & 0xFFFF_FFFF).to_bytes(4, "little")
      if self._writable(address) and self._needs_write(address, data):
        valid.append((address, value))
    if valid:
      self._log_write("bw32", [a for a, _ in valid],
              [v for _, v in valid])
      self.pcsx2_interface.batch_write_int32(valid)

  def _batch_write_float(self, operations: list[tuple[int, float]]) -> None:
    valid = []
    for address, value in operations:
      if (
        self._writable(address) and
        self._needs_write(address, struct.pack("<f", value))
      ):
        valid.append((address, value))
    if valid:
      self._log_write("bwfloat", [a for a, _ in valid],
              [v for _, v in valid])
      self.pcsx2_interface.batch_write_float(valid)

  def connect_to_game(self) -> None:
    """
    Initializes the connection to PCSX2 and verifies it is connected to the
    right game
    """
    if not self.pcsx2_interface.is_connected():
      try:
        self.pcsx2_interface.connect()
      except DuplicateConnectionError:
        if not self.reported_duplicate:
          self.reported_duplicate = True
          self.logger.warning(
            "PCSX2 is not answering; is another PINE client connected on the "
            "same slot?"
          )
        return
      except PineConnectionError:
        return
      self.reported_duplicate = False
      self.logger.info("Connected to PCSX2 Emulator")
    try:
      game_id = self.pcsx2_interface.get_game_id()
      # The first read of the address will be null if the client is faster
      # than the emulator
      self.current_game = None
      if game_id == "":
        self.logger.debug("No game connected")
        return

      if game_id in ADDRESSES.keys():
        self.addresses = ADDRESSES[game_id]
        # PCSX2 reports the game id from the moment a boot starts, before
        # the game's code is in RAM; connecting then would write into
        # memory the loader is still filling and break the boot. The tick
        # cache can hold the probe from before a disconnect, so drop it.
        self.clear_cache()
        if self.game_loaded():
          self.current_game = game_id
        else:
          self.logger.debug("Game is still booting")
      elif (
        self.game_id_error != game_id and
        game_id != b'\x00\x00\x00\x00\x00\x00'
      ):
        self.logger.warning(
          f"Connected to the wrong game ({game_id})")
        self.game_id_error = game_id
    except RuntimeError:
      self.logger.debug(traceback.format_exc())
    except ConnectionError:
      self.logger.debug(traceback.format_exc())

  def disconnect_from_game(self) -> None:
    self.pcsx2_interface.disconnect()
    self.current_game = None
    self.logger.info("Disconnected from PCSX2 Emulator")

  def get_connection_state(self) -> bool:
    try:
      connected = self.pcsx2_interface.is_connected()
      return connected and self.current_game is not None
    except (RuntimeError, ConnectionError):
      return False

  def game_loaded(self) -> bool:
    """Whether the game's code has finished loading into RAM"""
    return True

class Sly2Interface(GameInterface):
  def __init__(self, logger: Logger) -> None:
    super().__init__(logger)
    self.last_skip = time()
    self.loot_installer = LootInstaller(self, logger)
    self.menu_icon_installer = MenuIconInstaller(self, logger)
    self._dag_key: Optional[tuple[int, int]] = None
    self._dag_nodes: list[int] = []
    self._dag_parents: dict[int, list[int]] = {}
    self._string_pairs_key: Optional[tuple[int, int]] = None
    self._string_pairs: dict[int, int] = {}

  # =====================================================
  # Private Helper Methods - Job/Task Management
  # =====================================================

  def invalidate_dag(self) -> None:
    self._dag_key = None
    self._dag_nodes = []
    self._dag_parents = {}

  def _get_job_address(self, task: int) -> int:
    # The DAG is a linked list walked from the root, one read per node, so
    # the node addresses are cached until the root moves or the map changes.
    root = self._read32(self.addresses["DAG root"])
    key = (root, self.get_current_map())
    if key != self._dag_key:
      self.invalidate_dag()
      self._dag_key = key
      self._dag_nodes = [root]
    while len(self._dag_nodes) <= task:
      self._dag_nodes.append(self._read32(self._dag_nodes[-1]+0x20))

    return self._dag_nodes[task]

  def _episode_nodes(self, episode: int) -> list[int]:
    """DAG indices of every job and task of an episode"""
    jobs = [
      index
      for chapter in self.addresses["jobs"][episode-1]
      for job in chapter
      for index in (job if isinstance(job, tuple) else (job,))
    ]
    episode_name = list(EPISODES.keys())[episode-1]
    tasks = [
      index
      for job_tasks in TASKS.get(episode_name, {}).values()
      for index, _ in job_tasks
    ]
    return jobs + tasks

  def prefetch_tick_state(self) -> None:
    """Fetch everything a tick reads in two batches: the fixed addresses,
    then the values behind pointers found in the first batch"""
    a = self.addresses
    words = [
      "world id", "map id", "job id", "loading", "active character",
      "active character pointer", "camera focus", "infobox",
      "infobox string", "coins", "items received", "bottle count",
      "savefile last world", "unload mega jump", "DAG root",
      "clock-la defeated", "hackpack", "sly pointer", "clock speed",
      "friction", "string table", "skip cutscene", "cave hook",
      "coin pops"
    ]
    reads = [(4, a[name]) for name in words]
    reads += [(4, CAVE_HOOK_ORIG)]
    reads += [(2, a["frame counter"]), (1, a["input"])]
    reads += [(1, a["episode unlocks"]), (6, a["gadgets"])]
    reads += [(4, a["sly bindings"] + 4*i) for i in range(3)]
    reads += [
      (4, address)
      for table in ("bottle flags", "vaults", "loot", "operation completion")
      for address in a[table]
    ]
    reads += [(4, address) for ep in a["treasures"] for address in ep]
    reads += [(4, address) for address in a["health"].values()]
    self.prefetch(reads)

    episode = self._read32(a["world id"])
    reads = [(4, self._read32(a["infobox"]) + 0x64)]
    if 1 <= episode <= 8:
      reads += [(4, address) for address in a["loot chance"][episode-1]]
      reads += [
        (4, address)
        for table in ("loot table odds", "loot table")
        for guard in a[table][episode-1]
        for address in guard
      ]
      if not self.is_loading():
        reads += [
          (4, self._get_job_address(index) + 0x54)
          for index in self._episode_nodes(episode)
        ]
    self.prefetch(reads)

  def _read_job_status(self, address: int) -> int:
    return self._read32(self._get_job_address(address)+0x54)

  def _write_job_status(self, address: int, status: int) -> None:
    self._write32(self._get_job_address(address)+0x54, status)

  def _read_task_mission(self, address: int, status: int) -> None:
    self._write32(self._get_job_address(address)+0x54, status)

  def _get_task_parents(self, task: int) -> List[int]:
    address = self._get_job_address(task)
    if task not in self._dag_parents:
      parents_n = self._read32(address+0x94)
      parents_list = self._read32(address+0x98)
      self._dag_parents[task] = [
        self._read32(parents_list+4*i) for i in range(parents_n)
      ]
    return self._dag_parents[task]

  def _task_parents_finished(self, task: int) -> bool:
    parents = self._get_task_parents(task)
    return all([
      self._read32(p+0x54) == 3
      for p in parents
    ])

  def _reload(self, reload_data: bytes) -> None:
    self._write_bytes(
      self.addresses["reload values"],
      reload_data
    )
    self._write32(self.addresses["reload"], 1)

  # =====================================================
  # State Checking
  # =====================================================

  def game_loaded(self) -> bool:
    return self._read32(CAVE_HOOK_ORIG) == CAVE_HOOK_ORIG_WORD

  def alive(self) -> bool:
    # Batch read all needed addresses at once
    addresses_to_read = [
      self.addresses["active character"],
      self.addresses["world id"],
      self.addresses["map id"]
    ]

    results = self._batch_read32(addresses_to_read)
    active_character = results[0]
    episode = Sly2Episode(results[1])
    current_map = results[2]

    # Collect health addresses to check based on character/episode/map
    health_checks = []

    iron_horse = Sly2Episode.He_Who_Tames_the_Iron_Horse
    if active_character == 7:
      health_checks.append(self.addresses["health"]["Sly"])
      if episode == iron_horse and current_map == 30:
        health_checks.append(self.addresses["health"]["ChopperCanada2"])
      elif episode == Sly2Episode.Anatomy_for_Disaster and current_map == 38:
        health_checks.append(self.addresses["health"]["ChopperCarmelita"])
    elif active_character == 8:
      health_checks.append(self.addresses["health"]["Bentley"])
      if episode == Sly2Episode.Jailbreak and current_map == 14:
        health_checks.append(self.addresses["health"]["ChopperPrague"])
      elif episode == Sly2Episode.A_Tangled_Web and current_map == 17:
        health_checks.append(self.addresses["health"]["Blimp"])
      elif episode == iron_horse and current_map == 29:
        health_checks.append(self.addresses["health"]["ChopperCanada1"])
      elif episode == Sly2Episode.A_Starry_Eyed_Encounter and current_map == 8:
        health_checks.append(self.addresses["health"]["ChopperIndia"])
        health_checks.append(self.addresses["health"]["Murray"])
      elif episode == Sly2Episode.The_Predator_Awakens and current_map == 12:
        health_checks.append(self.addresses["health"]["TurretIndia2"])
    elif active_character == 9:
      health_checks.append(self.addresses["health"]["Murray"])
      if episode == Sly2Episode.A_Starry_Eyed_Encounter and current_map == 8:
        health_checks.append(self.addresses["health"]["TurretIndia"])
      elif episode == Sly2Episode.A_Tangled_Web and current_map == 17:
        health_checks.append(self.addresses["health"]["Tank"])
      elif (
        episode == Sly2Episode.Menace_from_the_North_Eh and
        current_map == 33
      ):
        health_checks.append(self.addresses["health"]["RCTank"])

    # Check if hackpack health needs to be checked
    needs_hackpack = (
      (episode == Sly2Episode.Jailbreak and current_map in [14,15]) or
      (episode == Sly2Episode.A_Tangled_Web and current_map == 22) or
      (episode == Sly2Episode.Menace_from_the_North_Eh and current_map == 32) or
      (episode == Sly2Episode.Anatomy_for_Disaster and current_map == 38)
    )

    if needs_hackpack:
      health_checks.append(self.addresses["hackpack"])

    # Batch read all health values
    if not health_checks:
      return True

    health_values = self._batch_read32(health_checks)

    # If hackpack needed, the last value is hackpack pointer, need to read
    # its health
    if needs_hackpack:
      hackpack_pointer = health_values[-1]
      hackpack_health = self._read32(hackpack_pointer + 0x184)
      if hackpack_health == 0:
        return False
      health_values = health_values[:-1]

    # All health values must be non-zero
    return all(health > 0 for health in health_values)

  def is_loading(self) -> bool:
    return self._read32(self.addresses["loading"]) == 2

  def in_safehouse(self) -> bool:
    # Some of these checks are not necessary, but I absolutely can't be
    # bothered to figure out which ones are
    return (
      self.get_current_episode() != 0 and
      self.in_hub() and
      self.get_current_job() == 0xffffffff and
      self._read32(self.addresses["active character pointer"]) == 0 and
      self._read32(self.addresses["camera focus"]) == 0 and
      # self._read32(self.addresses["fade type"]) == 777
      self._read32(self.addresses["infobox string"]) in [305,306,307,308]
    )

  def in_cutscene(self) -> bool:
    frame_counter = self._read16(self.addresses["frame counter"])
    return frame_counter > 10

  def in_hub(self) -> bool:
    return self.get_current_map() in HUB_MAPS

  def in_thiefnet(self) -> bool:
    return self._read32(self.addresses["thiefnet control"]) == 0x2DFC00

  def is_infobox(self) -> bool:
    infobox_pointer = self._read32(self.addresses["infobox"])
    return self._read32(infobox_pointer+0x64) == 2

  def stuck_in_cairo(self) -> bool:
    return (
      self.get_current_map() == 0 and
      self._read32(self.addresses["savefile last world"]) != 0
    )

  # =====================================================
  # Getters & Setters
  # =====================================================

  def get_current_episode(self) -> Sly2Episode:
    episode_num = self._read32(self.addresses["world id"])
    return Sly2Episode(episode_num)

  def get_current_map(self) -> int:
    return self._read32(self.addresses["map id"])

  def get_current_job(self) -> int:
    return self._read32(self.addresses["job id"])

  def set_current_job(self, job: int) -> None:
    self._write32(self.addresses["job id"], job)

  # =====================================================
  # Job/Task Management
  # =====================================================

  def fix_jobs(self) -> None:
    current_job = self.get_current_job()
    if current_job != 0xffffffff:
      return

    all_jobs = [
      job
      for chapter in self.addresses["jobs"][self.get_current_episode()-1]
      for job in chapter
    ]

    for job in all_jobs:
      if isinstance(job, tuple):
        job = job[0]

      if self._read_job_status(job) == 2:
        self.logger.info(f"Fixing job {job}")
        self._write_job_status(job,1)
        address = self._get_job_address(job)
        mission = self._read32(address+0x7c)

        for i in range(1,50):
          address = self._read32(address+0x20)
          task_mission = self._read32(address+0x7c)
          if task_mission != mission:
            break

          self._write_job_status(job+i,0)

  def disarm_stale_triggers(self) -> None:
    """Marks leftover job checkpoints done once their job is. Touching one
    of them (e.g. the Jean Bison radio spot in the Laser Redirection
    building) restarts the finished job, and quitting that rolls the episode
    back to it. The DAG is rebuilt from the save on every map load, so this
    has to run per map."""
    episode = self.get_current_episode()
    for job, trigger in STALE_JOB_TRIGGERS.get(episode, []):
      if (
        self._read_job_status(job) == 3 and
        self._read_job_status(trigger) == 1
      ):
        self._write_job_status(trigger, 3)

  def _walk_interactables(self) -> Iterator[int]:
    """Yields the interactable objects currently near the player"""
    seen = set()
    pointer = self._read32(self.addresses["interactables"])
    while (
      in_ee_ram(pointer, INTERACTABLE_NEXT + 4) and
      pointer not in seen and
      len(seen) < MAX_INTERACTABLES
    ):
      seen.add(pointer)
      yield pointer
      pointer = self._read32(pointer + INTERACTABLE_NEXT)

  def allow_sly_treasure_pickup(self) -> None:
    """Lets Sly use treasure pedestals the level script has closed to him.
    The list is rebuilt as objects come into range, so this runs per tick."""
    for entity in self._walk_interactables():
      if self._read32(entity + 0xC) != PEDESTAL_VTABLE:
        continue
      users = self._read32(entity + PEDESTAL_USERS)
      if not users & SLY_USER_BIT:
        self._write32(entity + PEDESTAL_USERS, users | SLY_USER_BIT)

  def _walk_entity_descendants(
    self, entity: int, skip_vtable: Optional[int] = None
  ) -> Iterator[int]:
    if self._read32(entity + ENTITY_CHILD_LINK) != ENTITY_NEXT:
      return
    child = self._read32(entity + ENTITY_FIRST_CHILD)
    last = self._read32(entity + ENTITY_LAST_CHILD)
    seen = set()
    while in_ee_ram(child, ENTITY_CHILD_LINK + 4) and child not in seen:
      seen.add(child)
      if skip_vtable is None or self._read32(child + 0xC) != skip_vtable:
        yield child
        yield from self._walk_entity_descendants(child, skip_vtable)
      if child == last or len(seen) >= MAX_ENTITY_CHILDREN:
        return
      child = self._read32(child + ENTITY_NEXT)

  def _unlink_child(self, parent: int, child: int) -> None:
    previous = self._read32(child + ENTITY_PREV)
    following = self._read32(child + ENTITY_NEXT)
    operations = [(child + ENTITY_PREV, 0), (child + ENTITY_NEXT, 0)]
    if previous:
      operations.append((previous + ENTITY_NEXT, following))
    else:
      operations.append((parent + ENTITY_FIRST_CHILD, following))
    if following:
      operations.append((following + ENTITY_PREV, previous))
    else:
      operations.append((parent + ENTITY_LAST_CHILD, previous))
    self._batch_write32(operations)

  def hide_mega_jump_pack(self) -> None:
    """Unregisters the jump pack entities hanging under Sly's back node the
    same way the game does when a treasure is put back, so they stop being
    drawn, and unlinks them from the node so picking a treasure up does not
    register them again. A picked-up treasure hangs under the same node
    from the start of the grab animation, so treasures are told apart by
    class."""
    sly = self._read32(self.addresses["sly pointer"])
    if not in_ee_ram(sly, SLY_BACK_NODE + 4):
      return
    node = self._read32(sly + SLY_BACK_NODE)
    if not in_ee_ram(node, ENTITY_CHILD_LINK + 4):
      return
    free_count = self.addresses["entity manager"] + ENTITY_MANAGER_FREE
    for entity in self._walk_entity_descendants(node, TREASURE_VTABLE):
      slot = self._read32(entity + ENTITY_SLOT)
      if not in_ee_ram(slot, 8) or self._read32(slot + 4) != entity:
        continue
      self._batch_write32([
        (entity + ENTITY_SLOT, self._read32(slot)),
        (slot, 0),
        (slot + 4, 0),
        (free_count, self._read32(free_count) + 1)
      ])
    children = list(self._walk_entity_descendants(node, TREASURE_VTABLE))
    for child in children:
      if self._read32(child + 0x10) == node:
        self._unlink_child(node, child)

  def activate_job(self, task: int) -> None:
    status = self._read_job_status(task)
    if status != 0:
      return
    if self._task_parents_finished(task):
      self.logger.debug(f"Activating job {task}")
      self._write_job_status(task,1)
    else:
      parents = self._get_task_parents(task)
      statuses = [self._read32(p+0x54) for p in parents]
      self.logger.debug(
        f"Not activating job {task}: parent statuses {statuses}"
      )

  def deactivate_job(self, task: int) -> None:
    status = self._read_job_status(task)
    if status == 1:
      self.logger.debug(f"Deactivating job {task}")
      self._write_job_status(task,0)

  def job_completed(self, task: int) -> bool:
    return self._read_job_status(task) == 3

  def job_statuses(self, tasks: list[int]) -> list[int]:
    return self._batch_read32([self._get_job_address(t) + 0x54 for t in tasks])

  def jobs_completed(self, tasks: list[int]) -> list[bool]:
    # Get job addresses
    job_status_addresses = []
    for job_id in tasks:
      job_address = self._get_job_address(job_id)
      job_status_addresses.append(job_address + 0x54)

    # Batch read all statuses
    return [i == 3 for i in self._batch_read32(job_status_addresses)]

  def tasks_completed(self, tasks: list[int]) -> list[bool]:
    # Unlike whole jobs, a task node is done at state 2 (job still in
    # progress); it only reaches 3 once the whole job finalizes.
    addresses = [self._get_job_address(t) + 0x54 for t in tasks]
    return [status >= 2 for status in self._batch_read32(addresses)]

  # =====================================================
  # Vault Stuff
  # =====================================================

  def vault_opened(self, vault: int) -> bool:
    return self._read32(self.addresses["vaults"][vault-1]) == 1

  def all_vault_statuses(self) -> list[bool]:
    vault_addresses = self.addresses["vaults"]
    vault_values = self._batch_read32(vault_addresses)
    return [value == 1 for value in vault_values]

  def all_vaults_opened(self) -> bool:
    return all(self.all_vault_statuses())

  # =====================================================
  # Operations/Goal
  # =====================================================

  def get_operation_completion(self) -> list[bool]:
    statuses = self._batch_read32(self.addresses["operation completion"])
    return [s == 1 for s in statuses]

  def is_goaled(self, condition: int) -> bool:
    statuses = self.get_operation_completion()
    if condition == 0:
      return statuses[0]
    elif condition == 1:
      return statuses[2]
    elif condition == 2:
      return statuses[4]
    elif condition == 3:
      return statuses[6]
    elif condition == 4:
      return statuses[7]
    elif condition == 5:
      return all(statuses[i] for i in [0,2,4,6,7])
    else:
      return False

  # =====================================================
  # Bottle Methods
  # =====================================================

  def set_bottles(self, amount: int) -> None:
    self._write32(self.addresses["bottle count"], amount)

  def get_bottle_flags(self) -> list[int]:
    return self._batch_read32(self.addresses["bottle flags"])

  def get_bottles(self, episode: Sly2Episode) -> int:
    address = self.addresses["bottle flags"][episode.value-1]
    flags = self._read32(address)
    return bin(flags).count("1")

  def get_bottle_list(self, episode: Sly2Episode) -> list[bool]:
    address = self.addresses["bottle flags"][episode.value-1]
    flags = self._read32(address)
    return [s == "1" for s in format(flags,"032b")[2:]]

  # =====================================================
  # Loot & Treasure
  # =====================================================

  def set_loot_chance(
    self, episode: Sly2Episode, loot_chances: tuple[float, float]
  ) -> None:
    addresses = self.addresses["loot chance"][episode.value-1]
    # Batch write both loot chances
    self._batch_write_float([
      (addresses[0], loot_chances[0]),
      (addresses[1], loot_chances[1])
    ])

  def set_loot_table_odds(
    self, episode: Sly2Episode, loot_table: tuple[tuple[int, ...], ...]
  ) -> None:
    addresses = self.addresses["loot table odds"][episode.value-1]
    # Batch write all loot table odds at once
    write_operations = []
    for i, table in enumerate(loot_table):
      for j, chance in enumerate(table):
        write_operations.append((addresses[i][j], chance))
    self._batch_write32(write_operations)

  def set_loot_table(
    self, episode: Sly2Episode, loot_table: dict[str, list[tuple[int,bool,int]]]
  ) -> None:
    addresses = self.addresses["loot table"][episode.value-1]

    # Batch write all loot table values
    write_operations = []
    for loot, locations in loot_table.items():
      for ep, large, slot in locations:
        if ep != episode.value:
          continue
        address = addresses[int(large)][slot-1]
        loot_id = LOOT_IDS[loot]
        write_operations.append((address, loot_id))

    if write_operations:
      self._batch_write32(write_operations)

  def set_prices(
    self, loot_prices: dict[str,int], treasure_prices: dict[str,int]
  ) -> None:
    write_operations = [
      (self.addresses["loot prices"][loot], price)
      for loot, price in loot_prices.items()
    ]
    write_operations += [
      (self.addresses["treasure prices"][treasure], price)
      for treasure, price in treasure_prices.items()
    ]
    self._batch_write32(write_operations)

  def all_loot_stolen(self) -> list[bool]:
    """Batch read all loot statuses"""
    loot_addresses = self.addresses["loot"]
    values = self._batch_read32(loot_addresses)
    return [value > 0 for value in values]

  def all_treasures_stolen(self) -> list[list[bool]]:
    """Batch read all treasure statuses across all episodes"""
    all_addresses = []
    for episode_treasures in self.addresses["treasures"]:
      all_addresses += episode_treasures

    values = self._batch_read32(all_addresses)

    result = [[v > 0 for v in values[i*3:i*3+3]] for i in range(8)]

    return result

  # =====================================================
  # Powerup/ThiefNet
  # =====================================================

  def load_powerups(self, powerups: PowerUps) -> None:
    booleans = list(powerups)
    byte_list = [
      [False]*7+[booleans[0]],
      booleans[1:9],
      booleans[9:17],
      booleans[17:25],
      booleans[25:33],
      booleans[33:36]+[False]*5
    ]
    data = b''.join(
      int(''.join(str(int(i)) for i in byte[::-1]),2).to_bytes(1,"big")
      for byte in byte_list
    )

    self._write_bytes(self.addresses["gadgets"], data)

  def read_powerups(self) -> PowerUps:
    data = self._read_bytes(self.addresses["gadgets"], 6)
    bits = [
      bool(int(b))
      for byte in data
      for b in f"{byte:08b}"[::-1]
    ]

    relevant_bits = bits[7:43]
    return PowerUps(*relevant_bits)

  def _string_pair(self, string_id: int) -> Optional[int]:
    """Returns the address of the pointer to a string with the given ID."""
    base = self._read32(self.addresses["string table"])
    count = self._read32(self.addresses["string pair count"])
    key = (base, count)
    # Dict is rebuilt when it moves (on map change).
    if key != self._string_pairs_key:
      self._string_pairs_key = key
      data = self._read_bytes(base, count * 8)
      self._string_pairs = {
        int.from_bytes(data[i*8:i*8+4], "little"): base + i*8 + 4
        for i in range(count)
      }
    return self._string_pairs.get(string_id)

  def _repoint_string(self, string_id: int, char_pointer: int) -> None:
    pair = self._string_pair(string_id)
    if pair is not None:
      self._write32(pair, char_pointer)

  def _thiefnet_string_ids(self, powerup: int) -> Tuple[int, int]:
    """The (name, description) text ids of a ThiefNet gadget entry"""
    entry = self.addresses["thiefnet costs"][powerup] - 8
    return self._read32(entry + 0x14), self._read32(entry + 0x18)

  def set_thiefnet(
    self, powerup: int, table_name: str, description: str
  ) -> None:
    name_buffer = (
      self.addresses["thiefnet name buffer"] + powerup * THIEFNET_NAME_STRIDE
    )
    description_buffer = (
      self.addresses["thiefnet description buffer"]
      + powerup * THIEFNET_DESCRIPTION_STRIDE
    )
    self._write_bytes(name_buffer, self._encode_text(table_name))
    self._write_bytes(description_buffer, self._encode_text(description))
    name_id, description_id = self._thiefnet_string_ids(powerup)
    self._repoint_string(name_id, name_buffer)
    self._repoint_string(description_id, description_buffer)

  def set_thiefnet_format(self) -> None:
    self._write_bytes(
      self.addresses["thiefnet description format"],
      self._encode_text(THIEFNET_DESCRIPTION_FORMAT)
    )

  def set_thiefnet_cost(self, powerup: int, cost: int) -> None:
    address = self.addresses["thiefnet costs"][powerup]
    self._write32(address, cost)

  def set_thiefnet_unlock(self) -> None:
    # Batch write all thiefnet unlocks at once
    write_operations = [
      (self.addresses["thiefnet unlock"][i], 1)
      for i in range(24)
    ]
    self._batch_write32(write_operations)

  def reset_thiefnet(self) -> None:
    self._write_bytes(
      self.addresses["thiefnet description format"],
      self._encode_text(THIEFNET_DESCRIPTION_FORMAT_VANILLA)
    )
    powerups = self.addresses["text"]["powerups"][self.get_current_episode()-1]
    for powerup, (name, description) in enumerate(powerups.values()):
      name_id, description_id = self._thiefnet_string_ids(powerup)
      self._repoint_string(name_id, name)
      self._repoint_string(description_id, description)

  # =====================================================
  # Text & Infobox
  # =====================================================

  @staticmethod
  def _encode_text(text: str) -> bytes:
    return text.replace("&","&&").encode()+bytes([0])

  def set_text(self, text: str|int, replacement: str) -> None:
    if isinstance(text,str):
      text_offset = self.addresses["text"][text][self.get_current_episode()-1]

      if not isinstance(text_offset,int):
        return

      string_table = self._read32(self.addresses["string table"])
      text_pointer = self._read32(string_table+text_offset)
    else:
      text_pointer = text

    self._write_bytes(text_pointer, self._encode_text(replacement))

  def set_texts(self, texts: list[tuple[int, str]]) -> None:
    """Write several strings in one read and as few writes as needed, so
    re-asserting them every tick only costs a round trip when one has been
    reloaded by the game"""
    encoded = [(address, self._encode_text(text)) for address, text in texts]
    self.prefetch([(len(data), address) for address, data in encoded])
    for address, data in encoded:
      self._write_bytes(address, data)

  def current_infobox(self) -> int:
    return self._read32(self.addresses["infobox string"])

  def set_infobox(self, text: str) -> bool:
    """Shows text in the infobox; returns False when the game can't show
    it right now so the caller can keep it queued"""
    ep = self.get_current_episode()
    if ep == 0 or self.in_safehouse():
      return False

    infobox_pointer = self._read32(self.addresses["infobox"])
    pair = self._string_pair(INFOBOX_CLIENT_STRING)
    if infobox_pointer == 0 or pair is None:
      return False

    buffer = self.addresses["infobox buffer"]
    encoded = self._encode_text(" "*10+text)[:INFOBOX_BUFFER_SIZE-1]+b"\0"
    self._write32(self.addresses["infobox scrolling"],2)
    self._write_bytes(buffer, encoded)
    self._write32(pair, buffer)
    self._write32(self.addresses["infobox string"],INFOBOX_CLIENT_STRING)
    self._write32(infobox_pointer+0x64,2)
    # Seconds; the game closes the bar itself when they run out, so a bar
    # survives even if the client never gets to hide it.
    self._write_float(self.addresses["infobox duration"],INFOBOX_SECONDS)

    # For some reason this has to be done sometimes?
    self._write32(self.addresses["infobox scrolling"],1)
    return True

  def disable_infobox(self) -> None:
    # Scrolling 3 is the game's own scroll-out; it resets the string id
    # and scrolling when it finishes, which a bare state write never did.
    infobox_pointer = self._read32(self.addresses["infobox"])
    if infobox_pointer == 0:
      return
    if self._read32(infobox_pointer+0x64) != 1:
      self._write32(infobox_pointer+0x64,1)
      self._write32(self.addresses["infobox scrolling"],3)

  # =====================================================
  # Coins/Items Methods
  # =====================================================

  def add_coins(self, to_add: int) -> None:
    current_amount = self._read32(self.addresses["coins"])
    new_amount = max(current_amount + to_add,0)
    self._write32(self.addresses["coins"],new_amount)

  def coins_paying_out(self) -> bool:
    """Whether the cave is still in the middle of a coin payout"""
    return self._read32(self.addresses["coin pops"]) != 0

  def queue_coins(self, amount: int, pops: int) -> bool:
    """Have the cave pay out `amount` coins in `pops` pops with the pickup
    sound. Returns False when the cave isn't live or is still busy, so the
    caller keeps the coins pending."""
    if not self.cave_live() or self.coins_paying_out():
      return False
    self._write32(self.addresses["coin amount"], amount)
    self._write32(self.addresses["coin pops"], pops)
    return True

  def get_coins(self) -> int:
    return self._read32(self.addresses["coins"])

  def play_sound(self, sound_id: int, interval: int = 0) -> bool:
    if not self.cave_live():
      return False
    self._write32(self.addresses["sound timer"], 0)
    self._write32(self.addresses["sound interval"], interval)
    self._write32(self.addresses["sound id"], sound_id)
    return True

  def call_function(self, function: int, arguments: list[int]) -> bool:
    """Has the cave call `function(*arguments)` next frame; `call_count`
    advances once it has"""
    if not self.cave_live():
      return False
    slot = self.addresses["cave call"]
    padded = (arguments + [0] * 4)[:4]
    self._batch_write32([(slot + 4 + 4*i, a) for i, a in enumerate(padded)])
    # The cave clears the request once it runs, which the tick cache can't
    # see; a second call in the same tick would otherwise be skipped.
    self.invalidate(slot, 4)
    self._write32(slot, function)
    return True

  def call_count(self) -> int:
    return self._read32(self.addresses["cave call"] + 0x18)

  def install_loot_models(self, loot_ids: list[int]) -> list[int]:
    return self.loot_installer.install(loot_ids)

  def poll_loot_textures(self) -> bool:
    return self.loot_installer.poll()

  def install_menu_icons(self) -> None:
    # Needs the cave for the chooser patch, and ThiefNet open for the glyph
    # set (reshaping it otherwise crashes the game). The build writes only
    # free RAM, so it runs during the open animation; the cave wires it in at
    # settle (build/cave.s).
    installer = self.menu_icon_installer
    if not self.cave_live():
      return
    if not installer.structure_ready():
      return
    installer.save_vanilla_chars()
    installer.build_structure()
    installer.install_chooser()

  def arm_menu_icons(self) -> None:
    self.menu_icon_installer.arm()

  def apply_thiefnet_theme(self, theme: int) -> None:
    self.menu_icon_installer.apply_theme(theme)

  def set_thiefnet_row_chars(self, classes: Optional[list[str]]) -> None:
    self.menu_icon_installer.set_row_chars(classes)

  def stop_sound(self) -> None:
    self._write32(self.addresses["sound id"], 0)
    self._write32(self.addresses["sound interval"], 0)

  def sound_playing(self) -> bool:
    return self._read32(self.addresses["sound id"]) != 0

  def set_items_received(self, n:int) -> None:
    self._write32(self.addresses["items received"], n)

  def read_items_received(self) -> int:
    return self._read32(self.addresses["items received"])

  def read_thiefnet_prefs(self) -> tuple[Optional[int], Optional[bool]]:
    """Return the preferences for the ThiefNet theme: (icon theme, text
    color). None when not set."""
    word = self._read32(self.addresses["thiefnet prefs"])
    theme_byte = word & 0xFF
    text_byte = (word >> 8) & 0xFF
    theme = (theme_byte & 0x7F) if theme_byte & 0x80 else None
    text = bool(text_byte & 0x01) if text_byte & 0x80 else None
    return theme, text

  def save_thiefnet_theme(self, theme: int) -> None:
    self._write8(self.addresses["thiefnet prefs"], 0x80 | (theme & 0x7F))

  def save_thiefnet_text(self, on: bool) -> None:
    self._write8(self.addresses["thiefnet prefs"] + 1, 0x80 | int(on))

  # =====================================================
  # Deathlink
  # =====================================================

  def get_damage_type(self) -> int:
    active_character = self.get_active_character()
    if active_character == 0:
      return 0

    return self._read32(active_character + 0xe2c)

  def _write_patches(
    self, operations: list[tuple[int, int, int]]
  ) -> list[tuple[int, int, int]]:
    """Instruction patches go through the cave once it is hooked: PCSX2
    write-protects pages holding recompiled code, and a PINE-thread write
    there can abort the emulator (see CAVE_BLOB). Data patches, and code
    patches before the cave is up, are written directly. Code patches that
    find no free slot are returned for a retry next tick."""
    text_end = self.addresses["text end"]
    code = [op for op in operations if op[0] < text_end]
    direct = [op for op in operations if op[0] >= text_end]
    if direct:
      self._batch_write32([(a, v) for a, v, _ in direct])
    if not code:
      return []
    if not self.cave_live():
      # Logged so a crash report can be matched to it (see CAVE_BLOB).
      self.logger.info(
        "Writing code patches directly (cave not live): "
        + ", ".join(f"{a:#010x}" for a, _, _ in code)
      )
      self._batch_write32([(a, v) for a, v, _ in code])
      return []
    slots = self.addresses["cave patches"]
    pending = self._batch_read32(
      [slots + 8*i for i in range(CAVE_PATCH_SLOTS)]
    )
    free = [slots + 8*i for i, a in enumerate(pending) if a == 0]
    requests = []
    while code and free:
      address, value, _ = code.pop(0)
      slot = free.pop(0)
      requests += [(slot + 4, value), (slot, address)]
    if requests:
      self._batch_write32(requests)
    return code

  def install_cave(self) -> None:
    """Install the code cave and hook it in as the per-frame update method
    of a singleton object (see cave.s), so the client can have the game call
    its own functions."""
    cave = self.addresses["cave"]
    blob = bytes.fromhex(CAVE_BLOB)
    # Once the cave runs, its page holds recompiled code and a PINE write
    # there races the recompiler (see CAVE_BLOB), so only write it when it
    # is actually missing.
    current = self._read_bytes(cave, len(blob))
    if current != blob:
      if any(current):
        self.logger.debug("Replacing an old code cave left in memory")
      self._write_bytes(cave, blob)
    for name in ("death flag", "coin pops", "coin amount", "coin timer",
                 "sound id", "sound interval", "sound timer", "cave call"):
      self._write32(self.addresses[name], 0)
    self.loot_installer.reset()
    self._write32(self.addresses["coin interval"], COIN_POP_INTERVAL)
    self._write_bytes(
      self.addresses["cave patches"], bytes(8 * CAVE_PATCH_SLOTS)
    )
    self._write_bytes(
      self.addresses["vault marker table"],
      b"".join(a.to_bytes(4, "little") for a in self.addresses["vaults"])
    )
    self._write_bytes(self.addresses["thiefnet color table"], bytes(0x80))
    # A map change with ThiefNet open skips the cave's teardown; restore the
    # glyph-table global here, before its vanilla base is zeroed below and
    # the teardown can never restore it (other menus read it and crash on
    # the relocated table).
    if self._read32(GLYPH_TABLE_ALT) == MENU_ICON_TABLE + 0x24:
      base = self.menu_icon_installer.vanilla_table_base
      if base:
        self._write32(GLYPH_TABLE_ALT, base)
    self._write_bytes(MENU_ICON_CAVE, bytes(16))
    self.menu_icon_installer.reset()
    self.safe_patch(
      self.addresses["cave hook"], CAVE_HOOK_ENTRY, CAVE_HOOK_ORIG
    )

  def cave_live(self) -> bool:
    return self._read32(self.addresses["cave hook"]) == CAVE_HOOK_ENTRY

  def set_vault_marker(self) -> None:
    """Redirect the vault marker's "gadget ownership" check to the function in
    the code cave instead."""
    self.safe_patch(
      VAULT_MARKER_PATCH_SITE,
      0x0C000000 | (CAVE_VAULT_MARKER >> 2),
      VAULT_MARKER_ORIG,
    )

  def set_thiefnet_colors(
    self, colors: list[int], visible: list[int]
  ) -> None:
    """Color the ThiefNet rows' name text. `colors` is one ABGR word per
    item; `visible` is the six displayed rows' colors (the shop hides
    purchased items, so the displayed order skips them). The cave keeps the
    visible slots synced per frame from the table; the initial rows are set
    here since the rows build from the slots before the cave sees them."""
    if not self.cave_live():
      return
    padded = colors[:32] + [THIEFNET_TEXT_VANILLA] * (32 - len(colors))
    table = self.addresses["thiefnet color table"]
    self._batch_write32([(table + i*4, padded[i]) for i in range(32)])
    self._write32(THIEFNET_COLORS_FLAG, 1)
    self.safe_patch(
      THIEFNET_COLORS_SITE,
      0x0C000000 | (CAVE_THIEFNET_COLORS >> 2),
      THIEFNET_COLORS_ORIG,
    )
    shown = visible[:6] + [THIEFNET_TEXT_VANILLA] * (6 - len(visible))
    self._batch_write32(
      [(slots + i*0x80, shown[i]) for i in range(6)
       for slots in (THIEFNET_NAME_COLOR, THIEFNET_NAME_COLOR_RELOC)]
    )

  def clear_thiefnet_colors(self) -> None:
    """Undo set_thiefnet_colors: restore the scroll handler's own call and put
    the visible rows' name text back to the vanilla blue."""
    self._write32(THIEFNET_COLORS_FLAG, 0)
    self.safe_patch(
      THIEFNET_COLORS_SITE,
      THIEFNET_COLORS_ORIG,
      0x0C000000 | (CAVE_THIEFNET_COLORS >> 2),
    )
    self._batch_write32(
      [(slots + i*0x80, THIEFNET_TEXT_VANILLA) for i in range(6)
       for slots in (THIEFNET_NAME_COLOR, THIEFNET_NAME_COLOR_RELOC)]
    )

  def kill_player(self, damage_type: int = 0x200) -> None:
    if self.in_safehouse() or self.get_current_episode() == 0:
      return

    active_character = self.get_active_character()
    if active_character == 0:
      return

    # Without the cave hooked in, fall back to the blunt kill so the death is
    # not lost, just unanimated.
    if not self.cave_live():
      self._write32(active_character+0xdf4, 8)
      return

    skeleton = self._read32(active_character + 0x9f0)
    info = bytearray.fromhex(DEATH_INFO_TEMPLATE)
    struct.pack_into(
      "<IIII", info, 0, skeleton, skeleton, active_character, damage_type
    )
    self._write_bytes(self.addresses["death struct"], bytes(info))
    self._write32(self.addresses["death flag"], 1)

  # =====================================================
  # Guard Management
  # =====================================================

  def get_active_character(self) -> int:
    """The character the player is controlling, or 0 if there is none"""
    pointer = self._read32(self.addresses["active character pointer"])
    return pointer if in_ee_ram(pointer) else 0

  def _walk_guards(self) -> Iterator[int]:
    """
    Yields every currently spawned guard.

    The lists are linked through each guard's 0x20 field. After a map
    unload the heads still hold pointers into freed memory, so the walk
    validates every node, and stops on a repeat or an implausible length
    rather than following garbage forever.
    """
    for guard in self.addresses["guard structs"]:
      seen = set()
      pointer = self._read32(guard)
      while (
        in_ee_ram(pointer, 0x24) and
        pointer not in seen and
        len(seen) < MAX_GUARDS
      ):
        seen.add(pointer)
        yield pointer
        pointer = self._read32(pointer + 0x20)

  def despawn_guards(self) -> None:
    # Guards already spawned when the client connected rolled their pockets
    # (loot chance and table) from the pre-connect config. Disabling them
    # makes map streaming re-spawn fresh guards that re-roll from the config
    # we now hold. Deliberately never re-enabled: re-enabling revives the
    # same stale objects instead of letting streaming replace them.
    for guard in self._walk_guards():
      transform = self._read32(guard + 0x54)
      if transform != 0:
        self._write32(transform + 0xA0, 1)

  # =====================================================
  # Traps
  # =====================================================

  def set_current_health(self, value: int) -> None:
    self.logger.debug(f"Setting health to {value}")
    active_character = self.get_active_character()
    if active_character == 0:
      return

    health_pointer = self._read32(active_character + 0xe00)
    if health_pointer != 0:
      self._write32(health_pointer, value)
      self.logger.debug(f"New health value: {self._read32(health_pointer)}")

  def patch_mega_jump_unload(self) -> None:
    self.safe_patch(
      self.addresses["unload mega jump"], 0, MEGA_JUMP_UNLOAD_CALL
    )

  def get_sly_bindings(self) -> list[int]:
    """Sly's three button bindings as gadget ids (0 or -1 = empty)"""
    base = self.addresses["sly bindings"]
    values = self._batch_read32([base + 4*i for i in range(3)])
    return [v - 0x1_0000_0000 if v >= 0x8000_0000 else v for v in values]

  def set_sly_binding(
    self, slot: int, gadget: int = MEGA_JUMP_GADGET_ID
  ) -> None:
    operations = [(self.addresses["sly bindings"] + 4*slot, gadget)]
    sly = self._read32(self.addresses["sly pointer"])
    if in_ee_ram(sly):
      operations.append((sly + 0x1180 + 0xC*slot, gadget))
    self._batch_write32(operations)

  def set_current_gadget_power(self, value: int) -> None:
    self.logger.debug(f"Setting gadget power to {value}")
    active_character = self.get_active_character()
    if active_character == 0:
      return

    gadget_power = self._read32(active_character + 0x12fc)
    if gadget_power != 0:
      self._write32(gadget_power, value)
      self.logger.debug(f"New gadget power value: {self._read32(gadget_power)}")

  def set_clock_speed(self, speed: float) -> None:
    # The game zeroes the clock while it scripts a sequence (a pickpocket
    # grab holds 0.0 for its whole duration) and restores 1.0 itself.
    # Writing over the zero resumes time mid-script, which dereferences a
    # NULL message provider and hard-crashes the game.
    if self._read_float(self.addresses["clock speed"]) == 0.0:
      return
    self._write_float(self.addresses["clock speed"], speed)

  def set_friction(self, friction: float) -> None:
    self._write_float(self.addresses["friction"], friction)

  def alert_guards(self, infinite_reach: bool = True) -> None:
    active = self.get_active_character()
    if active == 0:
      return

    for guard in self._walk_guards():
      # Swarmers use a different struct layout; only touch guards
      # already targeting the active character.
      if self._read32(guard + 0x1110) == active:
        if infinite_reach:
          self._write32(guard + 0x1100, 1)
        self._write32(guard + 0x1114, 1)

  def release_guards(self) -> None:
    active = self.get_active_character()
    if active == 0:
      return

    for guard in self._walk_guards():
      if self._read32(guard + 0x1110) == active:
        self._write32(guard + 0x1100, 0)

  # =====================================================
  # Other utils
  # =====================================================

  def skip_cutscene(self) -> None:
    pressing_x = self._read8(self.addresses["input"]) == 64

    if self.in_cutscene() and pressing_x:
      self._write32(self.addresses["skip cutscene"],0)

  def to_episode_menu(self) -> None:
    self.logger.info("Skipping to episode menu")
    if (
      self.get_current_map() == 0 and
      self.get_current_job() == 1583
    ):
      self.set_current_job(0xffffffff)
      self.set_items_received(0)

    self._reload(bytes.fromhex(MENU_RETURN_DATA))

  def unlock_episodes(self) -> None:
    self._write8(self.addresses["episode unlocks"], 8)

  def set_title_start_enabled(self, enabled: bool) -> None:
    # The title screen asks the pad for pressed buttons & 0x800 (Start)
    # via `addiu $a1, $zero, 0x800`; zeroing the mask makes Start a no-op
    # there while Select (menu) keeps working.
    enabled_mask, disabled_mask = 0x24050800, 0x24050000
    address = self.addresses["title start mask"]
    if enabled:
      self.safe_patch(address, enabled_mask, disabled_mask)
    else:
      self.safe_patch(address, disabled_mask, enabled_mask)
