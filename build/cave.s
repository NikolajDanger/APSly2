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
#     latter is what starts the payout.
#   sound: while a sound id is set, plays it through the game's own sound
#     functions. With interval 0 the sound plays once and the id is cleared;
#     with interval N it replays every N frames until the client clears the id,
#     so a rhythmic effect keeps frame-accurate timing without the client
#     driving each hit.
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
	divu  $zero, $a1, $k1
	mflo  $a2                   # pop = amount / pops
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
	ori   $a0, $a0, 0xeb30
	jal   0x1617e0             # SetCoins(0x2DEB30, coins + pop)
	addu  $a1, $a1, $v0
	jal   0x1fbb90             # new sound instance, id 41 (coin pickup)
	addiu $a0, $zero, 41
	move  $a0, $v0
	jal   0x1fb2f8             # play it
	move  $a1, $zero
call:
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
	move  $a0, $v0
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
