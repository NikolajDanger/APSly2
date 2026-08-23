"""The title screen: the one place the client rewrites menu text, unlocks
episodes and toggles the Start button."""

from ..Sly2Interface import Sly2Episode
from .harness import E2ETestBase

START_ENABLED = 0x24050800
START_DISABLED = 0x24050000


class TestTitle(E2ETestBase):
  state = "title"
  episode = 0
  map_id = 0

  def setUp(self) -> None:
    super().setUp()
    self.mutated = True

  def tearDown(self) -> None:
    if self.mutated:
      self.reload()

  def raw32(self, address: int) -> int:
    return self.pine.read_int32(address)

  def test_state(self) -> None:
    self.mutated = False
    self.assertEqual(
      self.interface.get_current_episode(), Sly2Episode.Title_Screen
    )
    self.assertEqual(self.interface.get_current_map(), 0)
    self.assertFalse(self.interface.in_hub())
    self.assertFalse(self.interface.is_loading())
    self.assertFalse(self.interface.stuck_in_cairo())
    self.assertEqual(self.raw32(self.addr["title start mask"]), START_ENABLED)
    self.assertEqual(self.pine.read_int8(self.addr["episode unlocks"]), 0)

  def test_title_strings(self) -> None:
    self.mutated = False
    texts = self.addr["text"]
    self.assertEqual(
      self.pine.read_string(texts["Press START (new)"], 64),
      "Press START button for New Game"
    )
    self.assertEqual(
      self.pine.read_string(texts["Press START (resume)"], 64),
      "Press START button to Resume Game"
    )

  def test_start_toggle(self) -> None:
    address = self.addr["title start mask"]
    self.interface.set_title_start_enabled(False)
    self.assertEqual(self.raw32(address), START_DISABLED)
    self.interface.clear_cache()
    self.interface.set_title_start_enabled(True)
    self.assertEqual(self.raw32(address), START_ENABLED)
    self.assertEqual(self.interface.refused_patches, set())

  def test_replace_title_text(self) -> None:
    texts = self.addr["text"]
    self.interface.set_texts([
      (texts["Press START (new)"], "Connected to Archipelago server"),
      (texts["Press START (resume)"], "Connected to Archipelago server")
    ])
    for key in ("Press START (new)", "Press START (resume)"):
      self.assertEqual(
        self.pine.read_string(texts[key], 64),
        "Connected to Archipelago server"
      )

  def test_unlock_episodes(self) -> None:
    self.interface.unlock_episodes()
    self.assertEqual(self.pine.read_int8(self.addr["episode unlocks"]), 8)


class TestEpisodeMenu(E2ETestBase):
  """The episode select menu, where the client rewrites the episode labels"""

  state = "episode_menu"
  episode = 0
  map_id = 1

  def test_state(self) -> None:
    self.assertEqual(
      self.interface.get_current_episode(), Sly2Episode.Title_Screen
    )
    self.assertEqual(self.interface.get_current_map(), 1)
    self.assertFalse(self.interface.is_loading())

  def test_episode_strings(self) -> None:
    for n in range(1, 9):
      with self.subTest(n):
        self.assertEqual(
          self.pine.read_string(self.addr["text"][f"Episode {n}"], 32),
          f"Episode {n}"
        )

  def test_replace_episode_text(self) -> None:
    address = self.addr["text"]["Episode 3"]
    self.interface.set_texts([(address, "Locked")])
    self.assertEqual(self.pine.read_string(address, 32), "Locked")
    self.reload()
