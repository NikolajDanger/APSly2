import os
import unittest
from inspect import cleandoc

from Options import Range

from ..Sly2Options import Sly2Options

YAML_PATH = os.path.join(
  os.path.dirname(os.path.dirname(__file__)), "Sly 2.yaml"
)


def comment_blocks() -> dict[str, list[str]]:
  """Map each top-level option key in the template to the comment lines
  immediately above it, with the '#' stripped."""
  with open(YAML_PATH, encoding="utf-8-sig") as f:
    lines = f.read().splitlines()

  blocks = {}
  for i, line in enumerate(lines):
    if not line.startswith("  ") or line.startswith("   ") or ":" not in line:
      continue
    key = line[2:].split(":")[0]
    if " " in key or key.startswith("#"):
      continue
    block = []
    j = i - 1
    while j >= 0:
      prev = lines[j].strip()
      if prev.startswith("##"):
        break
      if prev.startswith("#"):
        block.append(prev.lstrip("#").strip())
      elif prev == "" and j > 0 and lines[j-1].strip().startswith("#"):
        block.append("")
      else:
        break
      j -= 1
    while block and block[0] == "":
      block.pop(0)
    while block and block[-1] == "":
      block.pop()
    blocks[key] = list(reversed(block))
  return blocks


def expected_lines(option: type) -> list[str]:
  doc = cleandoc(option.__doc__ or "").strip()
  lines = [line.strip() for line in doc.splitlines()]
  if issubclass(option, Range):
    lines += [
      "",
      "You can define additional values between the minimum and maximum "
      "values.",
      f"Minimum value is {option.range_start}",
      f"Maximum value is {option.range_end}",
    ]
  return lines


class TestYamlTemplate(unittest.TestCase):
  def test_docstrings_match_template(self) -> None:
    blocks = comment_blocks()
    own_options = {
      name: option for name, option in Sly2Options.type_hints.items()
      if option.__module__ == Sly2Options.__module__
    }
    self.assertTrue(own_options)
    for name, option in own_options.items():
      with self.subTest(option=name):
        self.assertIn(name, blocks)
        self.assertEqual(blocks[name], expected_lines(option))
