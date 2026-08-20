import io

from . import Sly2TestBase


class TestOptionAdjustmentsSpoiler(Sly2TestBase):
  options = {
    "permissive_yaml": True,
    "goal": "All_Vaults",
    "include_vaults": False,
  }

  def test_adjustment_recorded(self) -> None:
    self.assertNotEqual(self.world.option_adjustments, [])

  def test_adjustment_in_spoiler(self) -> None:
    handle = io.StringIO()
    self.world.write_spoiler(handle)
    spoiler = handle.getvalue()
    self.assertIn("Sly 2 (Tester) Option Adjustments", spoiler)
    self.assertIn("Turning on include_vaults.", spoiler)


class TestNoOptionAdjustmentsSpoiler(Sly2TestBase):
  options = {}

  def test_no_adjustments_recorded(self) -> None:
    self.assertEqual(self.world.option_adjustments, [])

  def test_no_section_in_spoiler(self) -> None:
    handle = io.StringIO()
    self.world.write_spoiler(handle)
    self.assertNotIn("Option Adjustments", handle.getvalue())
