"""Start PCSX2 (if none answers on PINE) and load a checked-in savestate,
then leave it running for interactive poking.

From the Archipelago checkout:
  SLY2_E2E=1 SLY2_E2E_ISO=<iso> python -m worlds.Sly2.e2e.launch [state]
State names are the files in e2e/states (default ep1_hub).
"""

import atexit
import sys

from .harness import (
  LOADING, MAP_ID, WORLD_ID, connect, emulator, load_state, scratch
)

STATES = {
  "ep1_hub": (1, 2), "ep1_safehouse": (1, 2), "ep1_thiefnet": (1, 2),
  "ep8_hub": (8, 38), "ep8_pack": (8, 38), "title": (0, 0),
  "episode_menu": (0, 1)
}


def main(argv: list[str]) -> int:
  name = argv[0] if argv else "ep1_hub"
  if name not in STATES:
    print(f"unknown state {name!r}; one of {', '.join(STATES)}")
    return 1
  pine = connect()
  atexit.unregister(emulator.shutdown)
  load_state(pine, name, *STATES[name])
  scratch.release()
  world, map_id, loading = pine.batch_read_int32([WORLD_ID, MAP_ID, LOADING])
  print(
    f"{name}: world {world} map {map_id} loading {loading}; "
    "PCSX2 left running"
  )
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
