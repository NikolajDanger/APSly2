from typing import Any

from Options import OptionError

from . import Sly2TestBase


class OptionTestBase(Sly2TestBase):
  def assert_option_error(self, options: dict[str, Any]) -> None:
    """Assert that generating with `options` is rejected by
    validate_options."""
    class Strict(OptionTestBase):
      auto_construct = False

    Strict.options = options
    case = Strict("world_setup")
    with self.assertRaises(OptionError):
      case.world_setup()


class TestAllVaultsCoercion(OptionTestBase):
  options = {
    "permissive_yaml": True,
    "goal": "All_Vaults",
    "include_vaults": False,
  }

  def test_include_vaults_forced_on(self) -> None:
    self.assertTrue(self.world.options.include_vaults)

  def test_strict_raises(self) -> None:
    self.assert_option_error({**self.options, "permissive_yaml": False})


class TestPickAndMixCoercion(OptionTestBase):
  options = {
    "permissive_yaml": True,
    "goal": "Pick_and_Mix",
    "pick_and_mix": {},
  }

  def test_default_condition_enabled(self) -> None:
    self.assertEqual(
      self.world.options.pick_and_mix.value["anatomy_for_disaster"], 1
    )

  def test_strict_raises(self) -> None:
    self.assert_option_error({**self.options, "permissive_yaml": False})


class TestPickAndMixVaultsCoercion(OptionTestBase):
  options = {
    "permissive_yaml": True,
    "goal": "Pick_and_Mix",
    "pick_and_mix": {"all_vaults": 1},
    "include_vaults": False,
  }

  def test_include_vaults_forced_on(self) -> None:
    self.assertTrue(self.world.options.include_vaults)

  def test_strict_raises(self) -> None:
    self.assert_option_error({**self.options, "permissive_yaml": False})


class TestClockwerkHuntKeysCoercion(OptionTestBase):
  options = {
    "permissive_yaml": True,
    "goal": "Clockwerk_Hunt",
    "keys_in_pool": 10,
    "required_keys_goal": 20,
  }

  def test_requirement_lowered(self) -> None:
    self.assertEqual(self.world.options.required_keys_goal.value, 10)

  def test_strict_raises(self) -> None:
    self.assert_option_error({**self.options, "permissive_yaml": False})


class TestStartingEpisode8Coercion(OptionTestBase):
  options = {
    "permissive_yaml": True,
    "starting_episode": "Anatomy_for_Disaster",
    "episode_8_keys": "First_section",
  }

  def test_keys_mode_changed(self) -> None:
    self.assertEqual(self.world.options.episode_8_keys.value, 1)

  def test_strict_raises(self) -> None:
    self.assert_option_error({**self.options, "permissive_yaml": False})


class TestBottleBundleCoercion(OptionTestBase):
  options = {
    "permissive_yaml": True,
    "bottle_item_bundle_size": 3,
    "bottle_location_bundle_size": 0,
  }

  def test_both_sizes_zeroed(self) -> None:
    self.assertEqual(self.world.options.bottle_item_bundle_size.value, 0)
    self.assertEqual(self.world.options.bottle_location_bundle_size.value, 0)

  def test_strict_raises(self) -> None:
    self.assert_option_error({**self.options, "permissive_yaml": False})


class TestMinMaxSwapCoercion(OptionTestBase):
  options = {
    "permissive_yaml": True,
    "coins_minimum": 300,
    "coins_maximum": 100,
    "thiefnet_minimum": 3000,
    "thiefnet_maximum": 1000,
    "loot_value_minimum": 200,
    "loot_value_maximum": 20,
    "treasure_value_minimum": 900,
    "treasure_value_maximum": 300,
  }

  def test_values_swapped(self) -> None:
    opt = self.world.options
    self.assertEqual((opt.coins_minimum.value, opt.coins_maximum.value),
                     (100, 300))
    self.assertEqual(
      (opt.thiefnet_minimum.value, opt.thiefnet_maximum.value), (1000, 3000)
    )
    self.assertEqual(
      (opt.loot_value_minimum.value, opt.loot_value_maximum.value), (20, 200)
    )
    self.assertEqual(
      (opt.treasure_value_minimum.value, opt.treasure_value_maximum.value),
      (300, 900)
    )

  def test_strict_raises(self) -> None:
    for low, high in [
      ("coins_minimum", "coins_maximum"),
      ("thiefnet_minimum", "thiefnet_maximum"),
      ("loot_value_minimum", "loot_value_maximum"),
      ("treasure_value_minimum", "treasure_value_maximum"),
    ]:
      self.assert_option_error({low: 10, high: 5})


class TestTooManyItemsCoercion(OptionTestBase):
  options = {
    "permissive_yaml": True,
    "goal": "Clockwerk_Hunt",
    "keys_in_pool": 500,
    "required_keys_goal": 500,
    "required_keys_episode_8": 500,
  }

  def test_pool_shrunk_and_requirements_clamped(self) -> None:
    opt = self.world.options
    self.assertLess(opt.keys_in_pool.value, 500)
    self.assertLessEqual(opt.required_keys_goal.value, opt.keys_in_pool.value)
    self.assertLessEqual(
      opt.required_keys_episode_8.value, opt.keys_in_pool.value
    )

  def test_strict_raises(self) -> None:
    self.assert_option_error({**self.options, "permissive_yaml": False})


class TestEpisode8KeysWarnOnly(OptionTestBase):
  options = {
    "permissive_yaml": False,
    "episode_8_keys": "Last_section",
    "keys_in_pool": 10,
    "required_keys_episode_8": 50,
  }

  def test_left_as_written(self) -> None:
    self.assertEqual(self.world.options.required_keys_episode_8.value, 50)

  @property
  def run_default_tests(self) -> bool:
    return False


class TestEpisode8KeysLoweredWhenPermissive(OptionTestBase):
  options = {
    "permissive_yaml": True,
    "episode_8_keys": "Last_section",
    "keys_in_pool": 10,
    "required_keys_episode_8": 50,
  }

  def test_requirement_lowered(self) -> None:
    self.assertLessEqual(self.world.options.required_keys_episode_8.value, 10)
