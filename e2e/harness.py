"""Fixtures for the end-to-end suite, which talks to a PCSX2 that is already
running Sly 2 over PINE. Nothing here launches an emulator: when none is
answering, every test skips. The suite is further gated on SLY2_E2E=1 so it
can never run as part of a blanket Archipelago test run."""

import atexit
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..pcsx2_interface.pine import DEFAULT_SLOT, Pine, PineConnectionError
from ..Sly2Interface import Sly2Interface

GAME_ID = "SCUS-97316"
E2E_ROOT = Path(__file__).parent
STATES_DIR = E2E_ROOT / "states"

ENABLED = os.environ.get("SLY2_E2E", "") not in ("", "0")
SCRATCH_SLOT = int(os.environ.get("SLY2_E2E_SLOT", "99"))
SSTATES_DIR = Path(
  os.environ.get("SLY2_E2E_SSTATES", "~/.config/PCSX2/sstates")
).expanduser()
STATE_PREFIX = os.environ.get("SLY2_E2E_GAME", "SCUS-97316 (07652DD9)")
PINE_SLOT = int(os.environ.get("SLY2_E2E_PINE_SLOT", str(DEFAULT_SLOT)))
ISO = os.environ.get("SLY2_E2E_ISO", "")
PCSX2 = os.environ.get("SLY2_E2E_PCSX2", "pcsx2-qt")
LAUNCH_TIMEOUT = 90.0
RESERVED_SLOTS = range(0, 11)

SENTINEL_ADDRESS = 0x466FF0
SENTINEL = 0xDEADBEEF
POLL_INTERVAL = 0.1
SETTLE_POLLS = 5

WORLD_ID = 0x3D4A60
MAP_ID = 0x3E1110
LOADING = 0x3D3980
LOADING_ACTIVE = 2

BACKUP_SUFFIX = ".sly2-e2e-backup"


def slot_path(slot: int) -> Path:
  return SSTATES_DIR / f"{STATE_PREFIX}.{slot:02d}.p2s"


def state_path(name: str) -> Path:
  return STATES_DIR / f"{name}.p2s"


class ScratchSlot:
  """Owns the PCSX2 savestate slot the suite loads through. Whatever the user
  had in that slot is moved aside on first use and moved back at exit."""

  def __init__(self, slot: int) -> None:
    if slot in RESERVED_SLOTS:
      raise ValueError(
        f"Slot {slot} is reachable from the PCSX2 UI; "
        "set SLY2_E2E_SLOT above 10"
      )
    self.slot = slot
    self.path = slot_path(slot)
    self.backup = self.path.with_name(self.path.name + ".backup")
    self.claimed = False

  def claim(self) -> None:
    if self.claimed:
      return
    for path in (self.path, self.backup):
      if path.exists():
        path.rename(path.with_name(path.name + BACKUP_SUFFIX))
    self.claimed = True
    atexit.register(self.release)

  def release(self) -> None:
    if not self.claimed:
      return
    for path in (self.path, self.backup):
      path.unlink(missing_ok=True)
      saved = path.with_name(path.name + BACKUP_SUFFIX)
      if saved.exists():
        saved.rename(path)
    self.claimed = False

  def install(self, name: str) -> None:
    source = state_path(name)
    if not source.exists():
      raise unittest.SkipTest(f"Savestate {source.name} is not checked in")
    self.claim()
    shutil.copyfile(source, self.path)

  def wait_for_written(self, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last = -1
    stable = 0
    while time.monotonic() < deadline:
      size = self.path.stat().st_size if self.path.exists() else -1
      stable = stable + 1 if size > 0 and size == last else 0
      if stable >= SETTLE_POLLS:
        return
      last = size
      time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"PCSX2 did not finish writing {self.path}")


scratch = ScratchSlot(SCRATCH_SLOT)


class Emulator:
  """A PCSX2 the suite started itself, shut down again at exit. Only used
  when SLY2_E2E_ISO is set and nothing answers on PINE."""

  def __init__(self) -> None:
    self.process: Optional[subprocess.Popen] = None
    self.log: Optional[str] = None

  @staticmethod
  def already_running() -> bool:
    return subprocess.run(
      ["pgrep", "-x", os.path.basename(PCSX2)], capture_output=True
    ).returncode == 0

  def launch(self) -> Pine:
    if not os.path.exists(ISO):
      raise unittest.SkipTest(f"SLY2_E2E_ISO does not exist: {ISO}")
    if self.process is not None:
      # Our own instance stopped answering: it is crashing, and writing
      # the core dump takes a while. Wait for it so pgrep sees it gone.
      try:
        self.process.wait(120.0)
      except subprocess.TimeoutExpired:
        self.process.kill()
        self.process.wait()
      print(f"PCSX2 died (exit {self.process.returncode}), relaunching")
    if self.already_running():
      raise unittest.SkipTest(
        "A PCSX2 is running but not answering on PINE; enable PINE there "
        "or close it so the suite can start its own"
      )
    log = tempfile.NamedTemporaryFile(
      prefix="sly2-e2e-pcsx2-", suffix=".log", delete=False
    )
    self.log = log.name
    self.process = subprocess.Popen(
      [PCSX2, "-batch", "-earlyconsolelog", "-fastboot", ISO],
      stdout=log, stderr=subprocess.STDOUT
    )
    print(f"PCSX2 log: {self.log}")
    atexit.register(self.shutdown)
    deadline = time.monotonic() + LAUNCH_TIMEOUT
    while time.monotonic() < deadline:
      if self.process.poll() is not None:
        raise unittest.SkipTest("PCSX2 exited before PINE came up")
      pine = Pine(PINE_SLOT)
      try:
        pine.connect()
        if pine.get_game_id() == GAME_ID:
          return pine
        pine.disconnect()
      except (PineConnectionError, TimeoutError, ConnectionError):
        pass
      time.sleep(0.5)
    raise unittest.SkipTest("PCSX2 did not bring up PINE in time")

  def shutdown(self) -> None:
    if self.process is None or self.process.poll() is not None:
      return
    self.process.terminate()
    try:
      self.process.wait(15.0)
    except subprocess.TimeoutExpired:
      self.process.kill()
      self.process.wait()


emulator = Emulator()


def connect() -> Pine:
  pine = Pine(PINE_SLOT)
  try:
    pine.connect()
    pine.get_emu_status()
  except (ConnectionError, TimeoutError) as error:
    pine.disconnect()
    if not ISO:
      raise unittest.SkipTest(f"PCSX2 is not answering on PINE: {error}")
    pine = emulator.launch()
  if pine.get_emu_status() != Pine.EmuStatus.RUNNING:
    raise unittest.SkipTest("PCSX2 is not running a game")
  game_id = pine.get_game_id()
  if game_id != GAME_ID:
    raise unittest.SkipTest(f"PCSX2 is running {game_id!r}, not {GAME_ID}")
  return pine


def reconnect(pine: Pine) -> None:
  pine.disconnect()
  deadline = time.monotonic() + 10.0
  while True:
    try:
      pine.connect()
      return
    except (PineConnectionError, TimeoutError):
      if time.monotonic() > deadline:
        raise
      time.sleep(POLL_INTERVAL)


def wait_for_idle(pine: Pine, timeout: float = 30.0) -> None:
  deadline = time.monotonic() + timeout
  while pine.read_int32(LOADING) == LOADING_ACTIVE:
    if time.monotonic() > deadline:
      raise TimeoutError("The game is stuck in a level transition")
    time.sleep(POLL_INTERVAL)


def load_state(
  pine: Pine, name: str, episode: int, map_id: int, timeout: float = 30.0
) -> None:
  scratch.install(name)
  wait_for_idle(pine, timeout)
  pine.write_int32(SENTINEL_ADDRESS, SENTINEL)
  pine.load_state(scratch.slot)
  deadline = time.monotonic() + timeout
  settled = 0
  while time.monotonic() < deadline:
    time.sleep(POLL_INTERVAL)
    try:
      values = pine.batch_read_int32(
        [SENTINEL_ADDRESS, WORLD_ID, MAP_ID, LOADING]
      )
    except ConnectionError:
      reconnect(pine)
      continue
    sentinel, world, current_map, loading = values
    ok = (
      sentinel != SENTINEL and world == episode and current_map == map_id and
      loading != LOADING_ACTIVE
    )
    settled = settled + 1 if ok else 0
    if settled >= SETTLE_POLLS:
      time.sleep(0.5)
      return
  raise TimeoutError(
    f"Savestate {name} did not settle on episode {episode} map {map_id}"
  )


def raw(pine: Pine, address: int) -> int:
  return pine.read_int32(address)


@unittest.skipUnless(ENABLED, "set SLY2_E2E=1 to run against PCSX2")
class E2ETestBase(unittest.TestCase):
  state: Optional[str] = None
  episode: int = 0
  map_id: int = 0
  pine: Pine
  interface: Sly2Interface

  @classmethod
  def setUpClass(cls) -> None:
    cls.pine = connect()
    cls.interface = Sly2Interface(getLogger("Sly2E2E"))
    cls.interface.pcsx2_interface = cls.pine
    cls.interface.connect_to_game()
    if cls.interface.current_game != GAME_ID:
      raise unittest.SkipTest("Sly2Interface did not recognise the game")
    cls.reload()

  @classmethod
  def tearDownClass(cls) -> None:
    cls.pine.disconnect()

  @classmethod
  def reload(cls) -> None:
    if cls.state is not None:
      load_state(cls.pine, cls.state, cls.episode, cls.map_id)
    cls.interface.clear_cache()
    cls.interface.invalidate_dag()

  def setUp(self) -> None:
    self.interface.clear_cache()
    self.addr = self.interface.addresses


if TYPE_CHECKING:
  HubTestMixin = E2ETestBase
else:
  class HubTestMixin:
    """Base for test mixins that are only collected through a state-specific
    E2ETestBase subclass"""
