"""Job DAG writes against the ep1_hub savestate, and the client's
job-completed -> location check flow. Episode 1 opens with Satellite
Sabotage (node 4 -> tasks 5, 6, 7 -> job end 8) gating node 9, which gates
Breaking and Entering (node 10)."""

import asyncio
import time
from typing import Callable

from ..data.Locations import location_dict
from ..data.Names import EpisodeName, job_location
from ..Sly2Client import _handle_game_ready
from .harness import LOADING_ACTIVE, POLL_INTERVAL, E2ETestBase
from .tick_base import TickTestBase

FIRST_JOB = 4
FIRST_JOB_TASKS = [5, 6, 7]
FIRST_JOB_CLOSURE = range(4, 10)
SECOND_JOB = 10
SECOND_CHAPTER_JOB = 36
LOCKED, AVAILABLE, IN_PROGRESS, DONE = range(4)
SETTLED = 3


def wait_for(condition: Callable[[], bool], timeout: float) -> bool:
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    if condition():
      return True
    time.sleep(POLL_INTERVAL)
  return False


class TestJobs(E2ETestBase):
  state = "ep1_hub"
  episode = 1
  map_id = 2

  def tearDown(self) -> None:
    self.reload()

  def status(self, node: int) -> int:
    self.interface.clear_cache()
    return self.interface._read_job_status(node)

  def complete_first_job(self) -> None:
    for node in FIRST_JOB_CLOSURE:
      self.interface._write_job_status(node, DONE)

  def test_activate_needs_parents(self) -> None:
    self.interface.activate_job(SECOND_JOB)
    self.assertEqual(self.status(SECOND_JOB), LOCKED)

  def test_activate_after_parents(self) -> None:
    self.complete_first_job()
    self.assertTrue(self.interface.job_completed(FIRST_JOB))
    self.assertEqual(
      self.interface.jobs_completed([FIRST_JOB, SECOND_JOB]), [True, False]
    )
    self.assertEqual(
      self.interface.tasks_completed(FIRST_JOB_TASKS), [True] * 3
    )
    self.interface.activate_job(SECOND_JOB)
    self.assertEqual(self.status(SECOND_JOB), AVAILABLE)
    self.interface.deactivate_job(SECOND_JOB)
    self.assertEqual(self.status(SECOND_JOB), LOCKED)

  def test_deactivate_and_reactivate(self) -> None:
    self.interface.deactivate_job(FIRST_JOB)
    self.assertEqual(self.status(FIRST_JOB), LOCKED)
    self.interface.activate_job(FIRST_JOB)
    self.assertEqual(self.status(FIRST_JOB), AVAILABLE)

  def test_fix_jobs_leaves_episode_without_job(self) -> None:
    self.assertFalse(self.interface.fix_jobs())
    self.assertEqual(self.pine.read_int32(self.addr["reload"]), 0)


class TestJobAbort(E2ETestBase):
  """Rolling back Satellite Sabotage, started in-game"""
  state = "ep1_job"
  episode = 1
  map_id = 2

  def tearDown(self) -> None:
    self.reload()

  def transitioned(self, episode: int, map_id: int) -> bool:
    """Waits for a reload to start and settle on episode/map_id"""
    def loading() -> int:
      return self.pine.read_int32(self.addr["loading"])

    def settled() -> bool:
      return (
        loading() == SETTLED and
        self.pine.read_int32(self.addr["world id"]) == episode and
        self.pine.read_int32(self.addr["map id"]) == map_id
      )

    return (
      wait_for(lambda: loading() == LOADING_ACTIVE, 10.0) and
      wait_for(settled, 30.0)
    )

  def status(self, node: int) -> int:
    self.interface.clear_cache()
    self.interface.invalidate_dag()
    return self.interface._read_job_status(node)

  def test_fix_jobs_rolls_back_through_reload(self) -> None:
    self.assertEqual(self.status(FIRST_JOB), IN_PROGRESS)
    self.assertTrue(self.interface.fix_jobs())
    self.assertTrue(self.transitioned(self.episode, self.map_id))
    self.assertEqual(self.pine.read_int32(self.addr["abort mission"]), 0)
    self.assertEqual(self.status(FIRST_JOB), AVAILABLE)
    self.assertEqual(
      [self.status(t) for t in FIRST_JOB_TASKS], [LOCKED] * 3
    )

  def test_menu_reload_consumes_abort(self) -> None:
    self.interface.to_episode_menu()
    self.assertNotEqual(
      self.pine.read_int32(self.addr["abort mission"]), 0
    )
    self.assertTrue(self.transitioned(0, 1))
    self.assertEqual(self.pine.read_int32(self.addr["abort mission"]), 0)


class TestJobTick(TickTestBase):
  """Completing a job in memory makes the client send its location and
  open the next job"""

  async def test_ticks(self) -> None:
    for node in FIRST_JOB_CLOSURE:
      self.interface._write_job_status(node, DONE)
    await self.run_ticks()
    self.assertTrue(self.ctx.jobs_completed[0][0][0])
    sent = {
      code
      for message in self.ctx.sent_cmds("LocationChecks")
      for code in message["locations"]
    }
    self.assertIn(
      location_dict[job_location(
        EpisodeName.THE_BLACK_CHATEAU, "Satellite Sabotage"
      )].code,
      sent
    )
    self.assertEqual(
      self.interface.job_statuses([SECOND_JOB, SECOND_CHAPTER_JOB]),
      [AVAILABLE, LOCKED]
    )
    self.interface._write_job_status(SECOND_JOB, DONE)
    await asyncio.wait_for(_handle_game_ready(self.ctx), 15.0)
    await asyncio.wait_for(_handle_game_ready(self.ctx), 15.0)
    sent = {
      code
      for message in self.ctx.sent_cmds("LocationChecks")
      for code in message["locations"]
    }
    self.assertIn(
      location_dict[job_location(
        EpisodeName.THE_BLACK_CHATEAU, "Breaking and Entering"
      )].code,
      sent
    )
