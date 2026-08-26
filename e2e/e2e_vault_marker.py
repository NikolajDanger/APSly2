"""Vault-location marker (ep1 hub): the client redirects the marker's
gadget-ownership check to the cave function so the marker tracks the episode's
vault instead of the gadget. The marker only renders after the vault-reveal
job, so these test the mechanism (pointer table, redirected call site, cave
function returning the current vault flag), not the visuals."""

import time
from typing import Callable

from ..data.Constants import (
  CAVE_VAULT_MARKER, VAULT_MARKER_ORIG, VAULT_MARKER_PATCH_SITE
)
from .harness import E2ETestBase

REDIRECT = 0x0C000000 | (CAVE_VAULT_MARKER >> 2)


class TestVaultMarker(E2ETestBase):
  state = "ep1_hub"
  episode = 1
  map_id = 2

  def setUp(self) -> None:
    super().setUp()
    with self.interface.batched_patches():
      self.interface.install_cave()
      self.interface.set_vault_marker()
    self._wait(lambda: self.interface.cave_live() and self._site() == REDIRECT)

  def tearDown(self) -> None:
    self.reload()

  def _wait(self, cond: Callable[[], bool], timeout: float = 6.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      self.interface.clear_cache()
      if cond():
        return True
      time.sleep(0.05)
    return False

  def _site(self) -> int:
    return self.pine.read_int32(VAULT_MARKER_PATCH_SITE)

  def _call_marker_fn(self) -> int:
    slot = self.addr["cave call"]
    self.interface.clear_cache()
    before = self.pine.read_int32(slot + 0x18)
    self.interface.call_function(CAVE_VAULT_MARKER, [0, 0, 0, 0])
    self._wait(lambda: self.pine.read_int32(slot + 0x18) != before)
    return self.pine.read_int32(slot + 0x14)

  def test_table_holds_vault_addresses(self) -> None:
    table = self.addr["vault marker table"]
    got = [self.pine.read_int32(table + 4*i) for i in range(8)]
    self.assertEqual(got, list(self.addr["vaults"]))

  def test_call_site_redirected(self) -> None:
    self.assertTrue(self.interface.cave_live())
    self.assertEqual(self._site(), REDIRECT)
    self.assertNotEqual(REDIRECT, VAULT_MARKER_ORIG)

  def test_returns_current_vault_flag(self) -> None:
    world = self.pine.read_int32(self.addr["world id"])
    flag_address = self.addr["vaults"][world - 1]
    original = self.pine.read_int32(flag_address)
    try:
      for want in (0, 1):
        self.pine.write_int32(flag_address, want)
        self.assertEqual(self._call_marker_fn(), want)
    finally:
      self.pine.write_int32(flag_address, original)
