from typing import Optional
from unittest.mock import patch

from .. import Sly2Callbacks, Sly2Client
from ..Sly2Callbacks import (
  SKIP_SETTLE,
  SKIP_STALL,
  JobSkip,
  handle_job_skips,
  pending_skip_steps,
)
from ..data.Constants import (
  CAVE_HOOK_ENTRY,
  CAVE_SKIP_JOB,
  ENDING_TRIGGER_VTABLE,
  FIRE_ENDING_TRIGGER,
  GO_TO_JOB,
)
from ..Sly2Interface import Sly2Episode
from .client_base import (
  ClientTestBase,
  build_dag,
  dag_node,
  set_job_status,
)

MISSIONS = 0x0180_0000
SCREEN = 0x0190_0000

SATELLITE = "The Black Chateau - Satellite Sabotage"
THUNDER_BEAK = "The Black Chateau - Operation: Thunder Beak"
FINALE = "Anatomy for Disaster - Carmelita's Gunner/Defeat Clock-la"


class JobSkipTestBase(ClientTestBase):
  options = {"goal": "Clockwerk_Hunt", "skip_jobs": [SATELLITE]}

  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    build_dag(self.pine, self.addr)
    self.pine.poke32(self.addr["cave hook"], CAVE_HOOK_ENTRY)
    self.now = 1000.0
    self.enter(1, 2)
    self.ctx.available_episodes[Sly2Episode(1)] = 4
    self.add_mission(4, 8)

  def add_mission(self, first: int, last: int, screen: bool = True) -> int:
    mission = MISSIONS + first*0x100
    for node in range(first, last+1):
      self.pine.poke32(dag_node(node) + 0x7C, mission)
    self.pine.poke32(mission + 0x68, dag_node(last))
    self.pine.poke32(mission + 0xAC, 0x6D6 if screen else 0xFFFFFFFF)
    self.pine.poke32(mission + 0xB8, SCREEN if screen else 0)
    return mission

  def tick(self, seconds: float = 0.0) -> None:
    self.now += seconds
    self.interface.clear_cache()
    with patch.object(Sly2Callbacks, "time", return_value=self.now):
      handle_job_skips(self.ctx)

  def called(self) -> Optional[tuple[int, int]]:
    """The armed cave call (function, first argument), and clears it the
    way the cave does"""
    slot = self.addr["cave call"]
    function = self.pine.peek32(slot)
    if not function:
      return None
    self.pine.poke32(slot, 0)
    return function, self.pine.peek32(slot + 4)


class TestYamlSkip(JobSkipTestBase):
  async def test_skips_available_job(self) -> None:
    set_job_status(self.pine, 4, 1)
    self.tick()
    self.assertEqual(self.called(), (CAVE_SKIP_JOB, MISSIONS + 4*0x100))
    self.assertEqual(
      list(self.ctx.notification_queue), ["Skipping Satellite Sabotage"]
    )

  async def test_waits_while_a_job_runs(self) -> None:
    set_job_status(self.pine, 4, 1)
    self.pine.poke32(self.addr["current mission"], MISSIONS)
    self.tick()
    self.assertIsNone(self.called())
    self.pine.poke32(self.addr["current mission"], 0)
    self.tick()
    self.assertIsNotNone(self.called())

  async def test_waits_for_the_chapter(self) -> None:
    set_job_status(self.pine, 4, 1)
    self.ctx.available_episodes[Sly2Episode(1)] = 0
    self.tick()
    self.assertIsNone(self.called())

  async def test_waits_outside_the_hub(self) -> None:
    set_job_status(self.pine, 4, 1)
    self.enter(1, 3)
    self.tick()
    self.assertIsNone(self.called())

  async def test_waits_for_the_screen(self) -> None:
    set_job_status(self.pine, 4, 1)
    self.pine.poke32(SCREEN + 0x58, 2)
    self.tick()
    self.pine.poke32(SCREEN + 0x58, 1)
    self.tick(SKIP_SETTLE - 1)
    self.assertIsNone(self.called())
    self.tick(2)
    self.assertIsNotNone(self.called())

  async def test_done_job_is_left_alone(self) -> None:
    set_job_status(self.pine, 4, 3)
    self.ctx.jobs_completed[0][0][0] = True
    self.pine.clear_counts()
    self.tick()
    self.assertIsNone(self.ctx.job_skip)
    self.assertEqual((self.pine.reads, self.pine.batches), (0, 0))

  async def test_finishes_after_the_ending(self) -> None:
    set_job_status(self.pine, 4, 1)
    self.tick()
    self.called()
    set_job_status(self.pine, 4, 3)
    self.tick(SKIP_SETTLE + 1)
    self.assertIsNone(self.ctx.job_skip)


class TestOperationSkip(JobSkipTestBase):
  options = {"goal": "Clockwerk_Hunt", "skip_jobs": [THUNDER_BEAK]}

  async def test_steps_through_the_parts(self) -> None:
    self.ctx.jobs_completed[0] = [
      [True]*len(chapter) for chapter in self.ctx.jobs_completed[0][:3]
    ] + [[False]]
    part_1 = self.add_mission(83, 93, screen=False)
    part_2 = self.add_mission(94, 97)
    set_job_status(self.pine, 83, 1)
    self.tick()
    self.assertEqual(self.called(), (CAVE_SKIP_JOB, part_1))

    set_job_status(self.pine, 83, 3)
    set_job_status(self.pine, 94, 1)
    self.tick(1)
    self.assertIsNone(self.called())
    self.tick(SKIP_SETTLE)
    self.assertEqual(self.called(), (CAVE_SKIP_JOB, part_2))
    self.assertEqual(self.ctx.job_skip.steps, [])  # type: ignore[union-attr]

  async def test_running_later_part_is_skipped(self) -> None:
    part_2 = self.add_mission(94, 97)
    set_job_status(self.pine, 94, 2)
    self.ctx.job_skip = JobSkip(THUNDER_BEAK, 1, [("skip", 94)])
    self.tick()
    self.assertEqual(self.called(), (CAVE_SKIP_JOB, part_2))

  async def test_leaving_the_episode_drops_the_skip(self) -> None:
    self.ctx.job_skip = JobSkip(THUNDER_BEAK, 1, [("skip", 94)])
    self.enter(0, 1)
    self.tick()
    self.assertIsNone(self.ctx.job_skip)

  async def test_gives_up_on_a_node_that_never_opens(self) -> None:
    self.ctx.job_skip = JobSkip(THUNDER_BEAK, 1, [("skip", 94)])
    self.tick()
    self.tick(SKIP_STALL + 1)
    self.assertIsNone(self.ctx.job_skip)
    self.assertIsNone(self.called())


class TestEpisode8Steps(JobSkipTestBase):
  options = {"goal": "Clockwerk_Hunt", "skip_jobs": [FINALE]}

  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.enter(8, 38)

  async def test_go_to_job_after_recon(self) -> None:
    set_job_status(self.pine, 23, 1)
    self.ctx.job_skip = JobSkip(
      "Anatomy for Disaster - Blimp HQ Recon", 8, [("go", 23)]
    )
    self.tick()
    self.assertEqual(self.called(), (GO_TO_JOB, dag_node(23)))

  async def test_fires_the_ending_trigger(self) -> None:
    trigger = dag_node(97) + 0xC0
    self.pine.poke32(trigger + 0xC, ENDING_TRIGGER_VTABLE)
    self.pine.poke32(trigger + 0x24, dag_node(98))
    set_job_status(self.pine, 98, 1)
    self.ctx.job_skip = JobSkip(FINALE, 8, [("end", 98)])
    self.tick()
    self.assertEqual(self.called(), (FIRE_ENDING_TRIGGER, trigger))

  async def test_finished_finale_is_not_replayed(self) -> None:
    for node in (86, 89):
      set_job_status(self.pine, node, 3)
    set_job_status(self.pine, 98, 1)
    self.assertEqual(pending_skip_steps(self.ctx, FINALE), [])

  async def test_finale_resumes_at_its_second_part(self) -> None:
    set_job_status(self.pine, 86, 3)
    set_job_status(self.pine, 89, 1)
    self.assertEqual(
      pending_skip_steps(self.ctx, FINALE), [("skip", 89), ("end", 98)]
    )


class TestSkipCommand(JobSkipTestBase):
  options = {"goal": "Dimitri", "skip_jobs": []}

  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.cmd = Sly2Client.Sly2CommandProcessor(self.ctx)

  async def test_skips_named_job(self) -> None:
    set_job_status(self.pine, 4, 1)
    self.cmd("/skip_job satellite sabotage")
    self.tick()
    self.assertEqual(self.called(), (CAVE_SKIP_JOB, MISSIONS + 4*0x100))

  async def test_refuses_the_goal_job(self) -> None:
    with self.assertLogs(Sly2Client.logger, "INFO") as logs:
      self.cmd("/skip_job Operation: Thunder Beak")
    self.assertIn("your goal needs it", logs.output[0])
    self.assertIsNone(self.ctx.job_skip_request)

  async def test_unknown_job(self) -> None:
    with self.assertLogs(Sly2Client.logger, "INFO") as logs:
      self.cmd("/skip_job Spice Room Recon")
    self.assertIn("has no job called", logs.output[0])

  async def test_reports_why_it_cannot_start(self) -> None:
    self.cmd("/skip_job Satellite Sabotage")
    with self.assertLogs(Sly2Client.logger, "INFO") as logs:
      self.tick()
    self.assertIn("isn't available yet", logs.output[0])
    self.assertIsNone(self.called())

  async def test_lists_skippable_jobs(self) -> None:
    set_job_status(self.pine, 4, 1)
    with self.assertLogs(Sly2Client.logger, "INFO") as logs:
      self.cmd._cmd_skip_job()
    self.assertIn("Jobs you can skip now: Satellite Sabotage", logs.output[0])
