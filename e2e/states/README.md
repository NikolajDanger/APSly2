# E2E savestates

PCSX2 savestates loaded by the end-to-end suite (`e2e/`). Captured with `python -m worlds.Sly2.e2e.capture_state <name>` from the Archipelago checkout; recapture with `--force` when the game setup or the PCSX2 version changes, since savestates are not portable across PCSX2 versions.

- PCSX2 `2.6.3`, game `SCUS-97316 (07652DD9)`.
- The sentinel word `0x466FF0` is zeroed before capture.

| State | Episode / map | Contents |
|---|---|---|
| `ep1_hub` | 1 / 2 (Paris hub) | Fresh game. Sly on the safehouse roof, no job active, no infobox showing, the intro cutscene done, a few guards pickpocketed (18 coins), 0 bottles, no gadgets, no ThiefNet purchases, client never connected (no code cave). |
| `title` | 0 / 0 (title screen) | Fresh boot to "Press START", no save loaded, episode unlocks 0, Start enabled. |
| `ep8_hub` | 8 / 38 (Anatomy for Disaster hub) | Fresh entry, just outside the safehouse, no job active, 18 coins, no gadgets, no jump pack yet (the level script attaches it after several jobs). |
| `episode_menu` | 0 / 1 (episode select) | Reached from `title` with `unlock_episodes` + `to_episode_menu`. The menu init resets the unlock byte to 1; the `Episode N` labels hold their vanilla strings. |
| `ep1_safehouse` | 1 / 2 (inside the Paris safehouse) | Same game as `ep1_hub`, just walked into the safehouse. |
| `ep1_thiefnet` | 1 / 2 (ThiefNet open) | As above with the ThiefNet shop list open. |
| `ep8_pack` | 8 / 38 (Anatomy for Disaster hub) | The Mega-Jump job (DAG node 80) available, next to a treasure pedestal, every gadget but Mega Jump owned, bindings full, 99 coins. Reached by poking the DAG rather than playing the jobs, so the DAG in this state is inconsistent (statuses do not follow the real job chain); use it for the pack and pedestal checks, not for job logic. |
