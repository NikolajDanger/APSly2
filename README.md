# Sly 2: Band of Thieves Archipelago
An archipelago implementation of Sly 2.

## What does randomization do in this game?
Each gadget and chapter of each episode is shuffled into the item pool, and optionally the bottles as well. The checks are completing jobs, collecting treasures, opening the vaults, purchasing items from ThiefNet, and optionally collecting bottles and pickpocketing loot from guards.

**Additional features include:**
- The ability to skip video cutscenes by pressing the X button.

## Setup

### Requirements
In order to play the Sly 2 Archipelago randomizer, you need:

- [Archipelago Multiworld Randomizer](https://github.com/ArchipelagoMW/Archipelago/releases).
- [The Sly 2 apworld](https://github.com/NikolajDanger/APSly2/releases/latest).
- [PCSX2](https://pcsx2.net/downloads/). Must be v1.7 or higher.
- A Sly 2 US ISO (`SCUS-97316`).

### PCSX2 Settings
Enable PINE in PCSX2
- In PCSX2, under `Tools`, check `Show Advanced Settings`.
- In PCSX2, `System -> Settings -> Advanced -> PINE Settings`, check `Enable` and ensure `Slot` is set to `28011`.

It is also recommended to check `Tools -> Enable File Logging` in PCSX2. If the emulator ever crashes while the client is connected, its log (in PCSX2's `logs` folder) then records why.

### Generating and hosting a multiworld
Refer to [the official guide](https://archipelago.gg/tutorial/Archipelago/setup_en) on how to set up your game. Be aware that Sly 2 is not in core, so you cannot generate a game on the website.

### Playing a game
1. Start the game in PCSX2.
2. Start the Sly 2 client from the Archipelago launcher, and connect to the multiworld.
3. Ensure that the "Press START ..." message has changed before playing.
4. Start a new game.

## Skipping the intro
You can skip the intro with the `/menu` command in the client. This might disable saving, so refer to "There's no "save and quit" option in the pause menu" in the Troubleshooting section.

## Skipping Cutscenes
If you want to skip every in-engine cutscene, you can do so with [this patch](https://github.com/zzamizz/weed-sheet/blob/main/mods/advantage/sly2/put_down_the_popcorn/07652DD9.put_down_the_popcorn.pnach).

Save the patch to your PCSX2 `patches` directory, and then enable it in `Settings -> Game Properties -> Patches` in PCSX2. The patch also adds several other improvements which can be toggled here.

## Tracker
The randomizer has full support for [Universal Tracker](https://github.com/FarisTheAncient/Archipelago/blob/tracker/worlds/tracker/docs/setup.md), based on lastingParadox's [tracker pack](https://github.com/lastingParadox/Sly2-Poptracker) for poptracker.

## Troubleshooting
### I completed some jobs but can't start the next one
Each episode is split into chunks by its chalk-talk cutscenes, and each chunk is unlocked by a separate `Progressive <Episode>` item. If you've finished the jobs you have access to and the next job marker is missing, you need another of that episode's items. The episode menu shows how many chunks you've unlocked (e.g. `Unlocked 2/4`). When using `Gradual sections`, episode 8's label instead shows your progress towards the next section (`Parts required for section 2: 3/5`).

### The client won't connect to my PCSX2 instance
Before asking for help in the Discord channel:
- Make sure you have PINE enabled. Also check that you've not turned it off in the game-specific settings.
- Make sure that you're playing the US version of the game (`SCUS-97316`).
- If you've enabled discord's rich presence for PCSX2, try disabling it.
- Make sure nothing else (like another Archipelago client) is connected to PCSX2's PINE slot; PCSX2 only answers one client at a time.

If all these fail, please ask for help in the [Discord channel](https://discord.com/channels/731205301247803413/1359447263981600788).

### PCSX2 crashed while the client was connected
Please report it in the Discord channel with the client log (`logs/Sly 2 Client_<date>.txt` in your Archipelago folder), which lists the last memory writes before the emulator stopped answering, and PCSX2's own log if you have file logging enabled (see [PCSX2 Settings](#pcsx2-settings)).

### There's no "save and quit" option in the pause menu
You can save the game manually in Options.

## Nerd zone
Want to have a bit of a poke at the code? See [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up a development checkout, run the tests and build the apworld.

## Acknowledgment
This project was heavily inspired by and built upon the structure and PINE code from [Evilwb's Archipelago Ratchet and Clank 2 implementation](https://github.com/evilwb/APRac2).
