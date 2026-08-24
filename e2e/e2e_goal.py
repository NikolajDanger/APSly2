"""Vault and operation flags against the ep1_hub savestate, and the
client's vault location check and goal completion ticks."""

from NetUtils import ClientStatus

from ..data.Locations import location_dict
from ..data.Names import EpisodeName, vault_location
from .harness import E2ETestBase
from .tick_base import TickTestBase

GOAL_OPERATIONS = {0: 0, 1: 2, 2: 4, 3: 6, 4: 7}
GOAL_ALL_BOSSES = 5
GOAL_ALL_VAULTS = 7


class TestVaultsAndOperations(E2ETestBase):
  state = "ep1_hub"
  episode = 1
  map_id = 2

  def tearDown(self) -> None:
    self.reload()

  def test_vaults(self) -> None:
    self.assertEqual(self.interface.all_vault_statuses(), [False] * 8)
    self.pine.write_int32(self.addr["vaults"][0], 1)
    self.interface.clear_cache()
    self.assertTrue(self.interface.vault_opened(1))
    self.assertFalse(self.interface.vault_opened(2))
    self.assertEqual(
      self.interface.all_vault_statuses(), [True] + [False] * 7
    )
    self.assertFalse(self.interface.all_vaults_opened())
    self.pine.batch_write_int32([(a, 1) for a in self.addr["vaults"]])
    self.interface.clear_cache()
    self.assertTrue(self.interface.all_vaults_opened())

  def test_operations(self) -> None:
    operations = self.addr["operation completion"]
    self.assertEqual(self.interface.get_operation_completion(), [False] * 8)
    for goal, index in GOAL_OPERATIONS.items():
      with self.subTest(goal=goal):
        self.assertFalse(self.interface.is_goaled(goal))
        self.pine.write_int32(operations[index], 1)
        self.interface.clear_cache()
        self.assertTrue(self.interface.is_goaled(goal))
    self.assertTrue(self.interface.is_goaled(GOAL_ALL_BOSSES))
    self.assertEqual(
      self.interface.get_operation_completion(),
      [i in GOAL_OPERATIONS.values() for i in range(8)]
    )


class TestVaultTick(TickTestBase):
  options = {"include_vaults": True}

  async def test_ticks(self) -> None:
    self.pine.write_int32(self.interface.addresses["vaults"][0], 1)
    await self.run_ticks()
    self.assertEqual(self.ctx.vaults, [True] + [False] * 7)
    sent = {
      code
      for message in self.ctx.sent_cmds("LocationChecks")
      for code in message["locations"]
    }
    self.assertIn(
      location_dict[vault_location(EpisodeName.THE_BLACK_CHATEAU)].code, sent
    )
    self.assertFalse(self.ctx.goal_sent)


class GoalTicks(TickTestBase):
  def goal_messages(self) -> list[dict]:
    return [
      m for m in self.ctx.sent_cmds("StatusUpdate")
      if m["status"] == ClientStatus.CLIENT_GOAL
    ]

  async def assert_goal_after(self, address: int) -> None:
    await self.run_ticks()
    self.assertFalse(self.ctx.goal_sent)
    self.assertEqual(self.goal_messages(), [])
    self.pine.write_int32(address, 1)
    await self.run_ticks()
    self.assertTrue(self.ctx.goal_sent)
    self.assertEqual(len(self.goal_messages()), 1)


class TestClockLaGoalTick(GoalTicks):
  options = {"goal": 4}

  async def test_ticks(self) -> None:
    operations = self.interface.addresses["operation completion"]
    await self.assert_goal_after(operations[GOAL_OPERATIONS[4]])


class TestAllVaultsGoalTick(GoalTicks):
  options = {"goal": GOAL_ALL_VAULTS, "include_vaults": True}

  async def test_ticks(self) -> None:
    vaults = self.interface.addresses["vaults"]
    self.pine.batch_write_int32([(a, 1) for a in vaults[1:]])
    await self.assert_goal_after(vaults[0])
