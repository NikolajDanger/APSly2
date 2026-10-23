"""Writes the essentials yaml template: the full template cut down to the
options in ESSENTIALS, which keep their comments, sections and defaults.

  python build/essentials_yaml.py FULL_TEMPLATE OUTPUT
"""

import re
import sys

ESSENTIALS = (
  "progression_balancing",
  "accessibility",
  "death_link",
  "ring_link",
  "starting_episode",
  "goal",
  "pick_and_mix",
  "keys_in_pool",
  "episode_8_keys",
  "required_keys_episode_8",
  "required_keys_goal",
  "include_tom",
  "include_mega_jump",
  "include_time_rush",
  "bottle_item_bundle_size",
  "trap_chance",
  "include_vaults",
  "include_pickpocketing",
  "tasksanity",
  "bottle_location_bundle_size",
  "bottlesanity",
  "randomize_loot",
  "local_items",
  "non_local_items",
  "start_inventory",
  "start_inventory_from_pool",
  "start_hints",
  "start_location_hints",
  "exclude_locations",
  "priority_locations",
  "item_links"
)
GAME_KEY = "'Sly 2: Band of Thieves':"
OPTION = re.compile(r"^  (\w+):")
SECTION_RULE = re.compile(r"^  ##+$")
SECTION_TITLE = re.compile(r"^  ## .+ ##$")
DESCRIPTION = re.compile(r"^description: '(.*)'$")
NOTE = (
  "# Options left out of this template take their default values. The full\n"
  "# template, sly2.yaml, lists every option.\n"
)


class Section:
  def __init__(self, header: list[str]) -> None:
    self.header = header
    self.options: list[tuple[str, list[str]]] = []


def split_template(
  lines: list[str]
) -> tuple[list[str], list[Section]]:
  """Split the template into its preamble and its sections' options."""
  start = lines.index(GAME_KEY + "\n") + 1
  sections: list[Section] = []
  pending: list[str] = []
  i = start
  while i < len(lines):
    line = lines[i]
    if SECTION_RULE.match(line) and SECTION_TITLE.match(lines[i + 1]):
      sections.append(Section(pending + lines[i:i + 3]))
      pending = []
      i += 3
      continue
    pending.append(line)
    i += 1
    match = OPTION.match(line)
    if not match:
      continue
    while i < len(lines) and lines[i].startswith("    "):
      pending.append(lines[i])
      i += 1
    sections[-1].options.append((match.group(1), pending))
    pending = []
  return lines[:start], sections


def essentials(lines: list[str]) -> list[str]:
  preamble, sections = split_template(lines)
  found = {name for section in sections for name, _ in section.options}
  missing = [name for name in ESSENTIALS if name not in found]
  if missing:
    raise SystemExit(f"Not in the full template: {', '.join(missing)}")

  out = []
  for line in preamble:
    match = DESCRIPTION.match(line)
    if match:
      title = match.group(1).replace("Default", "Essentials")
      line = f"description: '{title}'\n"
    if line == GAME_KEY + "\n":
      out.append(NOTE + "\n")
    out.append(line)
  for section in sections:
    kept = [block for name, block in section.options if name in ESSENTIALS]
    if not kept:
      continue
    out += section.header
    for block in kept:
      out += block
  return out


def main() -> None:
  source, destination = sys.argv[1:]
  with open(source, encoding="utf-8") as f:
    lines = f.readlines()
  with open(destination, "w", encoding="utf-8") as f:
    f.writelines(essentials(lines))


if __name__ == "__main__":
  main()
