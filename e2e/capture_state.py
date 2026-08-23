"""Save the game currently running in PCSX2 into the checked-in states.

Run from the Archipelago checkout:
  python -m worlds.Sly2.e2e.capture_state <name> [--force]
"""

import argparse
import shutil
import sys

from .harness import (
  LOADING, MAP_ID, SENTINEL_ADDRESS, WORLD_ID, connect, scratch, state_path
)

JOB_ID = 0x2DEB44


def main(argv: list[str]) -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("name")
  parser.add_argument("--force", action="store_true")
  args = parser.parse_args(argv)
  target = state_path(args.name)
  if target.exists() and not args.force:
    print(f"{target} exists; pass --force to overwrite")
    return 1

  pine = connect()
  world, map_id, job, loading = pine.batch_read_int32(
    [WORLD_ID, MAP_ID, JOB_ID, LOADING]
  )
  print(f"world {world}  map {map_id}  job {job:#x}  loading {loading}")
  if input(f"Save this as {target.name}? [y/N] ").strip().lower() != "y":
    return 1

  pine.write_int32(SENTINEL_ADDRESS, 0)
  scratch.claim()
  scratch.path.unlink(missing_ok=True)
  pine.save_state(scratch.slot)
  scratch.wait_for_written()
  shutil.copyfile(scratch.path, target)
  scratch.release()
  print(f"wrote {target} ({target.stat().st_size} bytes)")
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
