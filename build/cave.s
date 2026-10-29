# Shared code cave for SCUS-97316: the client's way of making the game run its
# own code. PINE can only read and write memory, never call a function, so the
# client writes this small routine into a stretch of RAM the game never uses and
# then arranges for the game to run it once every frame.
#
# *How it gets called*: Every frame the game walks a list of objects and calls
# each one's update function, which it finds by looking the function up in a
# table of pointers attached to the object's class (a C++ vtable). One class in
# that list has exactly one live object in every map, title screen and menu
# included. The client overwrites that class's "update" pointer so it points at
# this routine; the routine does its work and then jumps to the real update
# function, so the object keeps working as before. The hook is therefore just
# one pointer changed in a data table, and putting the original pointer back
# unhooks it again.
#
# *Why a pointer and not a patched instruction*: PCSX2 does not interpret the
# game's code instruction by instruction: it translates each stretch to native
# code the first time it runs and keeps the translation. To notice when the game
# modifies its own code, it marks every memory page holding translated code as
# read-only; a write to such a page trips that guard, and the guard throws the
# page's translations away so they get redone. A PINE write arrives on PINE's
# own thread, so the guard throws translations away while the game thread may
# be right in the middle of running them. A table of pointers is data, never
# translated, so its page is never guarded and writing it is harmless.
#
# What the routine does each frame:
#   patches: up to four (address, value) pairs. The routine stores each value at
#     its address and clears the request. This lets the client's remaining
#     instruction patches be written by the game thread, for the same reason as
#     above.
#   death: when the death flag is set, calls the game's damage function with a
#     fabricated "lethal hit" record, so the player dies with the real animation
#     instead of the map just reloading.
#   coins: while a payout is pending, every few frames adds one installment to
#     the wallet through the game's own coin functions and plays the coin pickup
#     sound, so a received Coins item clinks in like a real coin grab. The
#     client writes the amount before the number of installments, since the
#     latter is what starts the payout. A negative amount takes the coins
#     away in the same installments (the Debt trap), never below zero.
#   sound: while a sound id is set, plays it through the game's own sound
#     functions. With interval 0 the sound plays once and the id is cleared;
#     with interval N it replays every N frames until the client clears the id,
#     so a rhythmic effect keeps frame-accurate timing without the client
#     driving each hit. While a pitch range is set, each play gets a random
#     pitch in [min, min + range) from the cave's own generator (xorshift),
#     so a fast repeat doesn't need the client to rewrite it every hit.
#   guards: when the remove-guards flag is set, despawns every guard in the
#     world through the game's own removal (remove_guards below) and clears
#     the flag.
#   costs: while ThiefNet is open and the client has set the cost layouts,
#     lays out each visible cost cell for the cost it shows, so five-digit
#     costs fit (tn_costs below).
#   call: when a function pointer is set, calls it with the four argument words
#     that follow it, stores the return value, clears the pointer and bumps a
#     completion counter, so the client can run any game function.
#
# The routine's code and its data area are deliberately on different 4K pages:
# once the routine has run, its own page is a translated-code page with the
# guard described above, and every request the client wrote into it would trip
# that guard from PINE's thread.
#
# Assemble + emit the hex blob (CAVE_BLOB in data/Constants.py):
#   llvm-mc --assemble --triple=mipsel --mcpu=mips64r2 --filetype=obj \
#     -o cave.o cave.s
#   llvm-objcopy -O binary --only-section=.text cave.o cave.bin
#   python3 -c "print(open('cave.bin','rb').read().hex())"
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcf08      # k0 = 0x0042CF08 (heartbeat counter)
	lw    $k1, 0($k0)
	addiu $k1, $k1, 1
	sw    $k1, 0($k0)           # bump every frame -> proves hook fires
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcf04      # k0 = 0x0042CF04 (RA_SAVE)
	sw    $ra, 0($k0)
	sw    $a0, 0x20($k0)        # A0_SAVE: the update method's object
	sw    $a1, 0x24($k0)        # A1_SAVE
# menu icons: finish the ThiefNet icon install in the frame the shop
# settles, and undo its one global once the shop closes. The client builds
# everything into free RAM during the open animation and arms this through
# the params at 0x0042CFB0 (+0 armed, +4 vanilla glyph-table base, +8 text
# colors on, +c animation observed). The group array is only laid out at
# settle, so the cave copies
# the finalized groups over the client's copy, re-appends the row group's
# two elements and wires the glyph set. On close it restores GLYPH_TABLE_ALT,
# which other menus read. 0x3DA160 is zero once ThiefNet closes, unlike the
# glyph set and settle marker, which stay stale; every glyph-set dereference
# is guarded. A reopen can find the glyph set still wired (the game reuses
# it without reinitializing, e.g. after a same-episode map reload); the wire
# itself must not rerun then (its +2 appends aren't idempotent), but the
# blanked chars and the visible text colors are restored every settled
# frame either way.
menu_icons:
	lui   $k1, 0x003d
	ori   $k1, $k1, 0xa160      # ThiefNet UI control block
	lw    $t9, 0($k1)
	b     tn_costs              # closed: mi_teardown; open: widen the cost
	nop                         # column, then come back
tc_return:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcfb0      # menu-icon params
	lw    $k1, 0($k0)
	beq   $k1, $zero, patches   # not armed
	nop
	lui   $k1, 0x003d
	ori   $k1, $k1, 0xa174      # GLYPH_SET_PTR
	lw    $a0, 0($k1)           # a0 = live glyph set
	lui   $t0, 0x0010
	sltu  $t1, $a0, $t0
	bne   $t1, $zero, patches   # a0 < 0x00100000: not a real pointer
	nop
	lui   $t0, 0x0200
	sltu  $t1, $a0, $t0
	beq   $t1, $zero, patches   # a0 >= 0x02000000: not a real pointer
	nop
	lui   $k1, 0x003d
	ori   $k1, $k1, 0xa1a0      # THIEFNET_SETTLED
	lw    $k1, 0($k1)
	addiu $t0, $zero, -1
	beq   $k1, $t0, mi_blank     # still animating: blank rows so no vanilla
	nop                        # portraits flash before the themed wire
	lw    $k1, 0x54($a0)        # live glyph-table base
	beq   $k1, $zero, patches   # not ready
	nop
	lui   $t0, 0x0043
	ori   $t0, $t0, 0x6024      # MENU_ICON_TABLE + 0x24
	beq   $k1, $t0, mi_restore  # already wired: skip the non-idempotent
	nop                         # wire, still restore chars and colors
	lw    $t0, 0xc($k0)         # only wire a menu whose open animation the
	beq   $t0, $zero, mi_colors # cave saw (mi_blank sets this): a client
	nop                         # connecting mid-open leaves the row pool
	                            # built from the vanilla table, and wiring
	                            # under it freezes the next reopen. Colors
	                            # still apply (the slots don't need the wire).
	lw    $t1, 0x84($a0)        # src = live group array
	lw    $t2, 0x80($a0)        # group count
	sltiu $t0, $t2, 0x100
	beq   $t0, $zero, patches   # implausible count: bail
	nop
	sll   $t3, $t2, 5
	sll   $t4, $t2, 4
	addu  $t3, $t3, $t4         # size = count * 0x30
	lui   $t4, 0x0043
	ori   $t4, $t4, 0xa000      # dest = MENU_ICON_GROUPS
	addu  $t5, $zero, $zero
mi_copy:
	addu  $t6, $t1, $t5
	lw    $t7, 0($t6)
	addu  $t8, $t4, $t5
	sw    $t7, 0($t8)
	addiu $t5, $t5, 4
	bne   $t5, $t3, mi_copy
	nop
	lui   $t4, 0x0043
	ori   $t4, $t4, 0xa570      # row group in the copy (0x43a000 + 29*0x30)
	lhu   $t5, 0($t4)
	addiu $t5, $t5, 2
	sh    $t5, 0($t4)
	lui   $t5, 0x0043
	ori   $t5, $t5, 0xf800      # MENU_ICON_FIFTH_ELEMS
	sw    $t5, 4($t4)
	addiu $t5, $zero, 0x6c
	sw    $t5, 0x50($a0)        # max glyph id
	lui   $t5, 0x0043
	ori   $t5, $t5, 0x6024
	sw    $t5, 0x54($a0)        # live glyph-table base
	lw    $t5, 0x80($a0)
	addiu $t5, $t5, 2
	sw    $t5, 0x80($a0)        # group count + 2
	lui   $t5, 0x0043
	ori   $t5, $t5, 0xa000
	sw    $t5, 0x84($a0)        # group-array base
	lui   $t4, 0x003e
	ori   $t4, $t4, 0x1c78      # GLYPH_TABLE_ALT
	lui   $t5, 0x0043
	ori   $t5, $t5, 0x6024
	sw    $t5, 0($t4)           # GLYPH_TABLE_ALT = relocated
mi_restore:
	lui   $t0, 0x002b
	ori   $t0, $t0, 0xcde4      # ThiefNet row 0 char word (0x2BCDE4, stride 0x20)
	lui   $t1, 0x0043
	ori   $t1, $t1, 0x5000      # MENU_ICON_CHAR_TABLE (client-staged real chars)
	addiu $t2, $zero, 24
mi_chars:
	lw    $t3, 0($t1)
	sw    $t3, 0($t0)           # restore the real char word at the wire
	addiu $t0, $t0, 0x20
	addiu $t1, $t1, 4
	addiu $t2, $t2, -1
	bne   $t2, $zero, mi_chars
	nop
# The row pool the game built at settle reads its name colors from whichever
# table it was built against, so keep the six visible slots fresh in both the
# vanilla pool and the relocated copy. The scroll hook only fires on a
# scroll, never at the open itself. Each visible row's item comes from the
# menu's own row array (a purchase removes the item's row, so the displayed
# list is not contiguous in item index); rows past the end hold -1 and fall
# back to the vanilla blue.
mi_colors:
	lw    $t0, 8($k0)           # text colors on (client toggle)
	beq   $t0, $zero, patches
	nop
	lui   $t0, 0x003d
	ori   $t0, $t0, 0xa3a0      # scroll offset = first visible row
	lw    $t0, 0($t0)
	sltiu $t1, $t0, 27          # 24-row list, 6 visible rows
	beq   $t1, $zero, patches   # implausible scroll: bail
	nop
	lui   $t1, 0x003d
	ori   $t1, $t1, 0xa19c      # menu row array {item entry, element id}
	sll   $t2, $t0, 3
	addu  $t1, $t1, $t2         # &rows[scroll]
	lui   $t2, 0x003e
	ori   $t2, $t2, 0x307c      # row 0's name-color slot, vanilla pool
	lui   $t3, 0x0043
	ori   $t3, $t3, 0x6f00      # the same slot in the relocated copy
	addiu $t4, $zero, 6
mi_colors_loop:
	lw    $t5, 0($t1)           # the row's item entry index
	addiu $t5, $t5, -7          # entry 7+i = client item i
	sltiu $t6, $t5, 24
	beq   $t6, $zero, mi_colors_vanilla
	sll   $t5, $t5, 2
	lui   $t6, 0x0042
	ori   $t6, $t6, 0xce80      # color table (client-populated)
	addu  $t6, $t6, $t5
	b     mi_colors_store
	lw    $t5, 0($t6)
mi_colors_vanilla:
	lui   $t5, 0x7f66
	ori   $t5, $t5, 0x4c33
mi_colors_store:
	sw    $t5, 0($t2)
	sw    $t5, 0($t3)
	addiu $t1, $t1, 8
	addiu $t2, $t2, 0x80
	addiu $t4, $t4, -1
	bne   $t4, $zero, mi_colors_loop
	addiu $t3, $t3, 0x80
	b     patches
	nop
mi_blank:
	lw    $t0, 0x54($a0)        # already wired: the rebuild reads the real
	lui   $t1, 0x0043           # chars, so no vanilla portrait can flash, and
	ori   $t1, $t1, 0x6024      # a blanked char would draw the appended
	beq   $t0, $t1, patches     # filler glyph mid-animation, whose packet
	nop                         # theme 0 never stages
	addiu $t1, $zero, 1
	sw    $t1, 0xc($k0)         # animation observed: the settle wire may run
	lui   $t0, 0x002b
	ori   $t0, $t0, 0xcde4      # ThiefNet row 0 char word
	addiu $t1, $zero, 15        # filler char: its glyph's group isn't built yet,
	addiu $t2, $zero, 24        # so the row draws blank instead of a portrait
mi_blank_loop:
	sw    $t1, 0($t0)
	addiu $t0, $t0, 0x20
	addiu $t2, $t2, -1
	bne   $t2, $zero, mi_blank_loop
	nop
	b     patches
	nop
mi_teardown:
	lui   $t7, 0x003d
	ori   $t7, $t7, 0xa1a0      # THIEFNET_SETTLED stays settled on close;
	addiu $t8, $zero, -1        # reset it so a reopen waits for its own settle
	sw    $t8, 0($t7)           # instead of wiring before the row pool exists
	                            # and dropping the selection box
	lui   $t4, 0x003e
	ori   $t4, $t4, 0x1c78      # GLYPH_TABLE_ALT
	lw    $t5, 0($t4)
	lui   $t6, 0x0043
	ori   $t6, $t6, 0x6024
	bne   $t5, $t6, patches     # not our relocated base: nothing to restore
	nop
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcfb0      # menu-icon params
	lw    $t5, 4($k0)           # vanilla glyph-table base
	beq   $t5, $zero, patches
	nop
	sw    $t5, 0($t4)           # GLYPH_TABLE_ALT = vanilla
patches:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcf40      # k0 = 0x0042CF40 (PATCH slot 0)
	lw    $k1, 0($k0)
	beq   $k1, $zero, patch1
	lw    $a1, 4($k0)
	sw    $a1, 0($k1)
	sw    $zero, 0($k0)
patch1:
	lw    $k1, 8($k0)
	beq   $k1, $zero, patch2
	lw    $a1, 12($k0)
	sw    $a1, 0($k1)
	sw    $zero, 8($k0)
patch2:
	lw    $k1, 16($k0)
	beq   $k1, $zero, patch3
	lw    $a1, 20($k0)
	sw    $a1, 0($k1)
	sw    $zero, 16($k0)
patch3:
	lw    $k1, 24($k0)
	beq   $k1, $zero, death
	lw    $a1, 28($k0)
	sw    $a1, 0($k1)
	sw    $zero, 24($k0)
death:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcf00      # k0 = 0x0042CF00 (DEATH_FLAG)
	lw    $k1, 0($k0)
	beq   $k1, $zero, coins
	nop
	sw    $zero, 0($k0)         # clear DEATH_FLAG
	lui   $k0, 0x002d
	ori   $k0, $k0, 0xe2f0      # k0 = 0x002DE2F0 (active char ptr)
	lw    $a0, 0($k0)
	beq   $a0, $zero, coins     # no active character -> skip
	nop
	addiu $a0, $a0, 0x0df0      # a0 = entity+0xDF0 (damage block)
	lui   $a1, 0x0042
	jal   0x1a19a0             # game damage function
	ori   $a1, $a1, 0xce00      # a1 = &damage_info @0x0042CE00
coins:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcf10      # k0 = 0x0042CF10 (COIN_POPS)
	lw    $k1, 0($k0)
	beq   $k1, $zero, call
	nop
	lw    $k1, 8($k0)           # COIN_TIMER
	beq   $k1, $zero, pop
	addiu $k1, $k1, -1
	b     call
	sw    $k1, 8($k0)
pop:
	lw    $k1, 12($k0)          # COIN_INTERVAL
	lw    $a1, 4($k0)           # COIN_AMOUNT
	sw    $k1, 8($k0)
	lw    $k1, 0($k0)           # COIN_POPS
	div   $zero, $a1, $k1
	mflo  $a2                   # pop = amount / pops (signed)
	subu  $a1, $a1, $a2
	sw    $a1, 4($k0)
	addiu $k1, $k1, -1
	sw    $k1, 0($k0)
	sw    $a2, 16($k0)          # COIN_POP
	lui   $a0, 0x002d
	jal   0x161798             # GetCoins(0x2DEB30)
	ori   $a0, $a0, 0xeb30
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcf20
	lw    $a1, 0($k0)
	lui   $a0, 0x002d
	addu  $a1, $a1, $v0         # coins + pop
	slt   $k1, $a1, $zero
	movn  $a1, $zero, $k1       # floor at 0
	jal   0x1617e0             # SetCoins(0x2DEB30, max(coins + pop, 0))
	ori   $a0, $a0, 0xeb30
	jal   0x1fbb90             # new sound instance, id 41 (coin pickup)
	addiu $a0, $zero, 41
	move  $a0, $v0
	jal   0x1fb2f8             # play it
	move  $a1, $zero
call:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcfc0      # k0 = 0x0042CFC0 (REMOVE_GUARDS request)
	lw    $k1, 0($k0)
	beq   $k1, $zero, call_fn
	nop
	bal   remove_guards
	nop
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcfc0
	sw    $zero, 0($k0)
call_fn:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcf80      # k0 = 0x0042CF80 (CALL_FN request)
	lw    $k1, 0($k0)
	beq   $k1, $zero, sound     # no call armed
	lw    $a0, 4($k0)           # CALL_A0..A3
	lw    $a1, 8($k0)
	lw    $a2, 12($k0)
	jalr  $k1
	lw    $a3, 16($k0)
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcf80
	sw    $v0, 0x14($k0)        # CALL_RESULT
	sw    $zero, 0($k0)         # clear the request
	lw    $k1, 0x18($k0)        # CALL_COUNT: bumped once per completed call
	addiu $k1, $k1, 1
	sw    $k1, 0x18($k0)
sound:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcf0c      # k0 = 0x0042CF0C (SOUND_ID request)
	lw    $k1, 0($k0)
	beq   $k1, $zero, done      # no sound armed
	nop
	lw    $a2, 0x20($k0)        # SOUND_INTERVAL (0x0042CF2C), frames; 0=once
	beq   $a2, $zero, splay
	nop
	lw    $a1, 0x24($k0)        # SOUND_TIMER (0x0042CF30)
	beq   $a1, $zero, sreset
	addiu $a1, $a1, -1
	b     done
	sw    $a1, 0x24($k0)        # count down to the next repeat
sreset:
	b     sfire
	sw    $a2, 0x24($k0)        # timer = interval, then play (stay armed)
splay:
	sw    $zero, 0($k0)         # one-shot: clear the request after playing
sfire:
	jal   0x1fbb90             # new sound instance, id = k1
	move  $a0, $k1
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcf0c
	lw    $a1, 0x28($k0)        # SOUND_PITCH_RANGE (0x0042CF34), float
	beq   $a1, $zero, sstart    # no range: keep the default pitch
	move  $a0, $v0
	lw    $a2, 0x30($k0)        # SOUND_SEED (0x0042CF3C)
	sll   $a3, $a2, 13
	xor   $a2, $a2, $a3
	srl   $a3, $a2, 17
	xor   $a2, $a2, $a3
	sll   $a3, $a2, 5
	xor   $a2, $a2, $a3
	sw    $a2, 0x30($k0)
	srl   $a3, $a2, 9
	lui   $a2, 0x3f80           # 1.0
	or    $a3, $a3, $a2         # random float in [1, 2)
	mtc1  $a3, $f0
	mtc1  $a2, $f1
	sub.s $f0, $f0, $f1
	mtc1  $a1, $f1
	mul.s $f0, $f0, $f1
	lw    $a3, 0x2c($k0)        # SOUND_PITCH_MIN (0x0042CF38), float
	mtc1  $a3, $f1
	add.s $f0, $f0, $f1
	swc1  $f0, 0x18($v0)        # the instance's pitch
sstart:
	jal   0x1fb2f8             # play it
	move  $a1, $zero
done:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcf04
	lw    $ra, 0($k0)
	lw    $a0, 0x20($k0)
	lw    $a1, 0x24($k0)
	j     0x212c50             # the original update method
	nop

# Extra function, not part of the per-frame routine. Sets v0 to 0 or 1
# depending on whether the current episode's vault is open. This is to replace
# the function that decides whether to display the vault marker, which normally
# just checks if the vault gadget is owned.
vault_marker_opened:
	lui   $v0, 0x003d
	lw    $v1, 0x4a60($v0)      # world id (1..8)
	addiu $v1, $v1, -1          # -> table index 0..7
	sll   $v1, $v1, 2
	lui   $v0, 0x0042
	ori   $v0, $v0, 0xcf60      # &vault_table (client-populated)
	addu  $v0, $v0, $v1
	lw    $v0, 0($v0)           # this episode's vault-flag address
	lw    $v0, 0($v0)           # v0 = flag (1 = opened)
	jr    $ra
	nop

# Extra function, not part of the per-frame routine. Replaces the ThiefNet
# scroll handler's tail call `jal 0x1da9e8` (a0 = the menu object): it runs the
# original function, then recolors the six visible rows' name text. The color
# slots are per screen position, not per item, so on every scroll the client's
# per-item color table is re-read and the visible slots rewritten, keeping the
# names colored by item class as the list scrolls. Each row's item comes from
# the menu's row array (a purchase removes the item's row, so the displayed
# list is not contiguous in item index). Writes are gated on the
# client's toggle flag, so a freshly zeroed color table (every map init) is
# never copied into the slots as invisible alpha-0 words, and both slot
# regions are written since a stale-wired reopen's row pool reads the
# relocated copy.
thiefnet_colors:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcfa0      # save area
	sw    $ra, 0($k0)
	sw    $a0, 4($k0)           # a0 = the menu object
	jal   0x1da9e8             # the original tail call
	nop
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcfa0
	lw    $a0, 4($k0)
	lui   $t0, 0x0042
	ori   $t0, $t0, 0xcfb8      # text colors on (client toggle)
	lw    $t0, 0($t0)
	beq   $t0, $zero, tncolors_done
	nop
	lw    $t0, 0x250($a0)       # t0 = scroll offset (first visible row)
	sll   $t1, $t0, 3
	addu  $t1, $t1, $a0
	addiu $t1, $t1, 0x4c        # t1 = &rows[scroll] {item entry, element id}
	lui   $t2, 0x003e
	ori   $t2, $t2, 0x307c      # t2 = row 0's name-color slot (stride 0x80),
	                            # THIEFNET_NAME_COLOR (the vanilla row pool)
	lui   $t5, 0x0043
	ori   $t5, $t5, 0x6f00      # the same slot in the relocated copy
	addiu $t3, $zero, 6         # six visible rows
tncolors_loop:
	lw    $t4, 0($t1)           # the row's item entry index
	addiu $t4, $t4, -7          # entry 7+i = client item i
	sltiu $t6, $t4, 24
	beq   $t6, $zero, tncolors_vanilla
	sll   $t4, $t4, 2
	lui   $t6, 0x0042
	ori   $t6, $t6, 0xce80      # color table (client-populated)
	addu  $t6, $t6, $t4
	b     tncolors_store
	lw    $t4, 0($t6)
tncolors_vanilla:
	lui   $t4, 0x7f66
	ori   $t4, $t4, 0x4c33
tncolors_store:
	sw    $t4, 0($t2)
	sw    $t4, 0($t5)
	addiu $t1, $t1, 8
	addiu $t5, $t5, 0x80
	addiu $t3, $t3, -1
	bne   $t3, $zero, tncolors_loop
	addiu $t2, $t2, 0x80
tncolors_done:
	bal   tc_layout             # the scroll changed which cost each cell
	nop                         # shows: lay them out before this frame draws
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xcfa0
	lw    $ra, 0($k0)
	jr    $ra
	nop

# Extra function, not part of the per-frame routine, run through the call
# slot: claims a0 bytes (16-aligned by the client) from the bottom of the
# level heap and returns the claimed address. The game allocates map-lifetime
# memory from the same pointer on its own thread, so a read-modify-write of
# it over PINE can hand out memory the game just claimed; here the bump runs
# between frames, where nothing else allocates.
heap_alloc:
	lui   $v1, 0x002f
	ori   $v1, $v1, 0x6384      # &heap bottom
	lw    $v0, 0($v1)
	addiu $v0, $v0, 15
	addiu $a1, $zero, -16
	and   $v0, $v0, $a1         # v0 = the claim: heap bottom, aligned up
	addu  $a1, $v0, $a0
	jr    $ra
	sw    $a1, 0($v1)           # bottom = claim + size

# Extra function, not part of the per-frame routine: despawns every guard in
# the world through its class's Remove (vtable +0x4c, the same removal the
# game runs once a knocked-out guard has faded out), so the spawner refills
# the pool with fresh guards that roll their pockets from the current loot
# config. Guard structs are a fixed pool, chained through +0x20 from three
# list heads; +0x2c bit 0x10000000 marks one that is in the world. Hiding a
# guard instead leaves it spawned, frozen and still able to see the player.
# The t registers don't survive Remove, so the walk state lives on the stack.
remove_guards:
	addiu $sp, $sp, -0x20
	sw    $ra, 0($sp)
	lui   $t0, 0x003e
	ori   $t1, $t0, 0x0774
	sw    $t1, 4($sp)           # swarmer list head
	ori   $t1, $t0, 0x0778
	sw    $t1, 8($sp)           # swarmer list head
	ori   $t1, $t0, 0x0780
	sw    $t1, 12($sp)          # flashlight guard list head
	addiu $t0, $zero, 4
	sw    $t0, 0x10($sp)        # stack offset of the current head
rg_list:
	lw    $t0, 0x10($sp)
	addu  $t0, $t0, $sp
	lw    $t0, 0($t0)
	lw    $t1, 0($t0)           # first guard
	addiu $t2, $zero, 512
	sw    $t2, 0x14($sp)        # walk limit, in case a list is garbage
rg_guard:
	lui   $t2, 0x0010
	sltu  $t3, $t1, $t2
	bne   $t3, $zero, rg_next   # below 0x00100000: end of list
	lui   $t2, 0x0200
	sltu  $t3, $t1, $t2
	beq   $t3, $zero, rg_next   # 0x02000000 and up: not a real pointer
	nop
	lw    $t2, 0x14($sp)
	beq   $t2, $zero, rg_next
	addiu $t2, $t2, -1
	sw    $t2, 0x14($sp)
	lw    $t2, 0x20($t1)
	sw    $t2, 0x18($sp)        # next guard, read before the removal
	lw    $t2, 0x2c($t1)
	lui   $t3, 0x1000
	and   $t2, $t2, $t3
	beq   $t2, $zero, rg_skip   # not in the world
	nop
	lw    $t2, 0xc($t1)         # vtable
	lh    $a0, 0x48($t2)
	lw    $t3, 0x4c($t2)        # Remove
	jalr  $t3
	addu  $a0, $t1, $a0
rg_skip:
	b     rg_guard
	lw    $t1, 0x18($sp)
rg_next:
	lw    $t0, 0x10($sp)
	addiu $t0, $t0, 4
	sltiu $t1, $t0, 0x10
	bne   $t1, $zero, rg_list
	sw    $t0, 0x10($sp)
	lw    $ra, 0($sp)
	jr    $ra
	addiu $sp, $sp, 0x20

# Per-frame part of menu_icons, kept at the end so the extra functions above
# stay at their addresses. The cost cells only fit four digits: the text is
# right-anchored in a box that grows from its left x, so a five-digit cost
# needs a wider box, moved left and squeezed. Each visible cell takes the
# client's wide layout (width, x scale, x at 0x0042CFD0; width 0 = off) when
# the row it shows costs over 9999, and the vanilla one (at +0xc) otherwise,
# so a scroll moves the layout with the cost. The rows come from the menu's
# row array, as in mi_colors. The scroll hook (thiefnet_colors) runs the
# same pass, since this per-frame one runs before the scroll in its frame
# and would leave one frame drawn with the previous rows' layouts. The box width lives in each cell's draw item
# (vanilla glyph table, and its relocated copy once the menu icons are
# wired); scale and x live in two template transforms the game copies into a
# live transform every frame. Draw items and templates are built together on
# the first open and kept across reopens, so the draw item's element id
# guards both. The live transforms are a shared pool, only written while
# they point at a cost cell.
tn_costs:
	beq   $t9, $zero, mi_teardown  # ThiefNet closed: restore the global
	nop
	bal   tc_layout
	nop
	b     tc_return
	nop
tc_layout:
	lui   $t0, 0x0042
	ori   $t0, $t0, 0xcfd0      # cost layouts: wide, then vanilla
	lw    $t1, 0($t0)
	beq   $t1, $zero, tc_done   # no layout set
	nop
	lui   $t1, 0x003d
	ori   $t1, $t1, 0xa3a0      # scroll offset = first visible row
	lw    $t1, 0($t1)
	sltiu $at, $t1, 27          # 24-row list, 6 visible rows
	beq   $at, $zero, tc_done   # implausible scroll: bail
	sll   $t1, $t1, 3
	lui   $t2, 0x003d
	ori   $t2, $t2, 0xa19c      # menu row array {item entry, element id}
	addu  $t1, $t1, $t2         # &rows[scroll]
	lui   $t4, 0x003e
	ori   $t4, $t4, 0x30a0      # cost cell 0's draw item (stride 0x80)
	lui   $t5, 0x0043
	ori   $t5, $t5, 0x6f24      # the same in the relocated glyph table
	lui   $t6, 0x003e
	ori   $t6, $t6, 0x7990      # live transform pool (stride 0xe0)
	lui   $t7, 0x003e
	ori   $t7, $t7, 0x8e60      # first template (stride 0x80), second +0x1830
	addiu $t8, $zero, 0x442     # cost cell 0's element id
tc_loop:
	lw    $at, 0x18($t4)
	bne   $at, $t8, tc_next     # not built yet
	nop
	lw    $t2, 0($t1)           # the row's item entry
	sltiu $at, $t2, 0x2b        # the item table's size; past the end: -1
	beq   $at, $zero, tc_narrow
	sll   $t2, $t2, 5
	lui   $t3, 0x002c
	addu  $t3, $t3, $t2
	lw    $t3, -0x32f8($t3)     # the item's cost (0x2BCD08 + entry * 0x20)
	sltiu $at, $t3, 10000
	bne   $at, $zero, tc_narrow
	nop
	b     tc_apply
	move  $t2, $t0              # wide layout
tc_narrow:
	addiu $t2, $t0, 12          # vanilla layout
tc_apply:
	lw    $t3, 0($t2)           # width
	sw    $t3, 0x24($t4)
	lw    $at, 0x18($t5)
	bne   $at, $t8, tc_templates
	nop
	sw    $t3, 0x24($t5)
tc_templates:
	lw    $t3, 4($t2)           # x scale
	lw    $t9, 8($t2)           # x
	sw    $t3, 0($t7)
	sw    $t9, 0x10($t7)
	sw    $t3, 0x1830($t7)
	sw    $t9, 0x1840($t7)
	lw    $at, 0x20($t6)        # the live transform's draw item
	beq   $at, $t4, tc_live
	nop
	bne   $at, $t5, tc_next
	nop
tc_live:
	sw    $t3, 0($t6)
	sw    $t9, 0x10($t6)
tc_next:
	addiu $t1, $t1, 8
	addiu $t4, $t4, 0x80
	addiu $t5, $t5, 0x80
	addiu $t6, $t6, 0xe0
	addiu $t7, $t7, 0x80
	addiu $t8, $t8, 1
	sltiu $at, $t8, 0x448
	bne   $at, $zero, tc_loop
	nop
tc_done:
	jr    $ra
	nop

# Extra function, not part of the per-frame routine: completes a job for the
# client's job skip, the way finishing its last task does. Takes the job's
# mission and runs SetNodeStatus(the mission's last DAG node, 3), which marks
# every node of the job done, makes the next ones available and plays the
# job's ending (job-complete screen, and the chalk talk that follows it). The
# game only plays that ending for a job local to the current map, so the
# node's and the mission's "lives in another map" flags (+0x50) are cleared
# around the call and restored after it.
skip_job:
	addiu $sp, $sp, -0x20
	sw    $ra, 0($sp)
	lw    $t0, 0x68($a0)        # the mission's last node
	sw    $a0, 4($sp)
	sw    $t0, 8($sp)
	lw    $t1, 0x50($a0)
	sw    $t1, 0xc($sp)
	lw    $t1, 0x50($t0)
	sw    $t1, 0x10($sp)
	sw    $zero, 0x50($a0)
	sw    $zero, 0x50($t0)
	move  $a0, $t0
	jal   0x164df0              # SetNodeStatus
	addiu $a1, $zero, 3
	lw    $a0, 4($sp)
	lw    $t0, 8($sp)
	lw    $t1, 0xc($sp)
	sw    $t1, 0x50($a0)
	lw    $t1, 0x10($sp)
	sw    $t1, 0x50($t0)
	lw    $ra, 0($sp)
	jr    $ra
	addiu $sp, $sp, 0x20

# Extra function, not part of the per-frame routine: the Hypnosis trap's
# hook, patched over the world loop's per-vjoy fill call (HYPNOSIS_SITE,
# `jal 0x1c4468`). It runs the original fill, with three effects around it
# that the client switches on and off through the state block at
# 0x0042CD00 (+0 pace magnitude, +4 stick dead zone, +8 pace on, +c button
# latch mask, +10 overlay object, +14/+18/+1c the overlay's start/loop/end
# clip lengths less a frame and a half):
#   overlay: the ported hypnosis overlay is a level-script state machine
#     whose start and end clips only advance by script, so a ported copy
#     loops them forever; when the object sits in its start (3) or end (4)
#     state past the clip's length, it is moved on to the loop (2) or idle
#     (1) state. The loop clip's last key draws nothing, so the loop (2)
#     is restarted just before it. The block outlives the map that owned
#     the object, so the object is only trusted while it still carries the
#     class and the trap's object id.
#   latch: the mask is OR'd into the pad latch before the fill, which
#     masks those buttons out of this frame's vjoy and blocks them as new
#     presses from the next, so the trap locks every action but walking.
#   pace: the player character's vjoy gets a fixed magnitude after the
#     fill, and with the stick released keeps the character's heading, so
#     the hypnotized walk can only be steered, like the game's own.
# The EE's float compare is funct 0x34, not the 0x3c the assembler emits,
# hence the .word.
hypno_vjoy:
	addiu $sp, $sp, -0x30
	sd    $ra, 0x20($sp)
	sw    $a0, 0x10($sp)
	lui   $t1, 0x0042
	ori   $t1, $t1, 0xcd00      # the state block
	lw    $t6, 0x10($t1)        # overlay object
	beq   $t6, $zero, hv_latch
	nop
	lw    $t7, 0xc($t6)
	lui   $t8, 0x002d
	ori   $t8, $t8, 0xaf30      # its class vtable
	bne   $t7, $t8, hv_latch
	nop
	lw    $t7, 0x18($t6)
	ori   $t8, $zero, 0xfee0    # the trap's object id
	bne   $t7, $t8, hv_latch
	nop
	lw    $t7, 0x58($t6)        # state
	addiu $t8, $zero, 3
	beq   $t7, $t8, hv_start
	addiu $t8, $zero, 2
	beq   $t7, $t8, hv_loop
	addiu $t8, $zero, 4
	bne   $t7, $t8, hv_latch
	nop
	lwc1  $f4, 0x1c($t1)        # end clip length
	b     hv_clip
	addiu $a1, $zero, 1         # -> idle
hv_loop:
	lwc1  $f4, 0x18($t1)        # loop clip length
	lw    $t9, 0x84($t6)
	lw    $t9, 8($t9)
	lwc1  $f0, 0xc($t9)         # clip time
	.word 0x46040034            # c.lt.s $f0, $f4
	bc1t  hv_latch              # clip still running
	nop
	move  $a0, $t6
	jal   0x213830              # play the loop clip again (the set-state
	lw    $a1, 0x70($t6)        # function ignores the state it is in)
	b     hv_latch
	nop
hv_start:
	lwc1  $f4, 0x14($t1)        # start clip length
	addiu $a1, $zero, 2         # -> loop
hv_clip:
	lw    $t9, 0x84($t6)
	lw    $t9, 8($t9)
	lwc1  $f0, 0xc($t9)         # clip time
	.word 0x46040034            # c.lt.s $f0, $f4
	bc1t  hv_latch              # clip still running
	nop
	move  $a0, $t6
	jal   0x212a70              # set state + play its clip
	nop
hv_latch:
	lui   $t1, 0x0042
	ori   $t1, $t1, 0xcd00
	lw    $t3, 0xc($t1)         # latch mask
	lui   $t4, 0x002e
	lw    $t5, 0x0cbc($t4)      # pad latch
	or    $t5, $t5, $t3
	sw    $t5, 0x0cbc($t4)
	lw    $a0, 0x10($sp)
	jal   0x1c4468              # the original vjoy fill
	nop
	lui   $t1, 0x0042
	ori   $t1, $t1, 0xcd00
	lw    $t2, 8($t1)           # pace on
	beq   $t2, $zero, hv_done
	lw    $a0, 0x10($sp)
	lui   $t3, 0x002e
	lw    $t3, -0x1d10($t3)     # active character
	lw    $t5, 0x7c($a0)        # the vjoy's owner
	bne   $t5, $t3, hv_done
	nop
	lw    $t6, 0x80($a0)        # vjoy mode: 1 = player pad
	addiu $t7, $zero, 1
	bne   $t6, $t7, hv_done
	nop
	lwc1  $f0, 0x1c($a0)        # stick magnitude
	lwc1  $f4, 4($t1)           # dead zone
	.word 0x46040034            # c.lt.s $f0, $f4
	bc1f  hv_pace               # stick pushed: keep its angle
	nop
	lwc1  $f1, 0x1a8($t3)       # the character's heading
	swc1  $f1, 0x18($a0)
hv_pace:
	lwc1  $f5, 0($t1)
	swc1  $f5, 0x1c($a0)        # fixed magnitude
hv_done:
	ld    $ra, 0x20($sp)
	jr    $ra
	addiu $sp, $sp, 0x30

# Extra function, not part of the per-frame routine, run through the call
# slot: loads a sound bank from EE memory (a0) into the IOP sound driver
# through the game's loader RPC and returns its handle, -1 if the driver
# refused it, or -2 when the RPC client is busy (retry). The EE side of
# the driver's library was stripped from the game, so the bank-from-EE
# command is issued straight through the SIF RPC with the loader's client
# and command number. The send and reply buffers are the block at
# 0x0042CD50; the RPC blocks until the IOP replies.
hypno_bank_load:
	addiu $sp, $sp, -0x40
	sd    $ra, 0x30($sp)
	sd    $s0, 0x20($sp)
	lui   $s0, 0x0042
	ori   $s0, $s0, 0xcd50      # send buffer; reply at +0x10
	sw    $a0, 0($s0)
	addiu $v0, $zero, -1
	sw    $v0, 0x10($s0)
	lui   $a0, 0x0044
	jal   0x237488              # sceSifCheckStatRpc
	ori   $a0, $a0, 0x8440      # the loader's RPC client
	bne   $v0, $zero, hb_busy
	nop
	lui   $a0, 0x0044
	ori   $a0, $a0, 0x8440
	addiu $a1, $zero, 0x57      # bank from EE memory
	move  $a2, $zero            # blocking
	move  $a3, $s0
	addiu $t0, $zero, 4
	addiu $t1, $s0, 0x10
	addiu $t2, $zero, 4
	move  $t3, $zero
	sw    $zero, 0($sp)
	jal   0x237288              # sceSifCallRpc
	nop
	b     hb_out
	lw    $v0, 0x10($s0)
hb_busy:
	addiu $v0, $zero, -2
hb_out:
	ld    $ra, 0x30($sp)
	ld    $s0, 0x20($sp)
	jr    $ra
	addiu $sp, $sp, 0x40

# Extra function, not part of the per-frame routine: the callback the
# sound driver's looping play takes, which stores the new voice handle
# (a0) where the play call's argument (a1) points, so the client can stop
# the voice later.
hypno_voice_cb:
	jr    $ra
	sw    $a0, 0($a1)

# Extra function, not part of the per-frame routine: patched over the
# level sound-bank load's call between dropping the old level bank and
# loading the new one (HYPNOSIS_BANK_SITE, `jal 0x117d50`, reached on every
# level load). A trap bank still loaded there leaves the sound driver no
# room for the next level's bank, which then fails to load and silences
# every sound in it, so the trap's bank (+74 of the state block) is unloaded
# first and its handle and voice words cleared, then the original call runs.
hypno_level_unload:
	addiu $sp, $sp, -0x20
	sd    $ra, 0x10($sp)
	sw    $a0, 0($sp)
	lui   $t0, 0x0042
	ori   $t0, $t0, 0xcd00      # the state block
	lw    $a0, 0x74($t0)        # the trap's bank
	beq   $a0, $zero, hl_out
	nop
	sw    $zero, 0x70($t0)
	jal   0x2321b8              # unload it
	sw    $zero, 0x74($t0)
hl_wait:
	jal   0x231c48              # until the driver has taken it
	nop
	nop
	nop
	bne   $v0, $zero, hl_wait
	nop
hl_out:
	lw    $a0, 0($sp)
	ld    $ra, 0x10($sp)
	j     0x117d50              # the original call
	addiu $sp, $sp, 0x20
