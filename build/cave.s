# Shared code cave (SCUS-97316). Source for CAVE_BLOB in data/Constants.py.
# PINE cannot call game functions, so this cave is written into free EE RAM
# and the per-frame world-update loop (0x226550) is trampoline-hooked at
# 0x226674 to run it. Each call site is driven by client-written words that
# the cave consumes itself:
#   death (DEATH_FLAG): calls the damage function 0x1A19A0 with the
#     fabricated damage_info struct at 0x42BE00 -> a real animated death.
#   coins (COIN_POPS, COIN_AMOUNT): while COIN_POPS != 0, every COIN_INTERVAL
#     frames pay out COIN_AMOUNT/COIN_POPS (the last pop takes the remainder)
#     with SetCoins(GetCoins()+pop) (0x1617E0/0x161798, which tick the HUD
#     counter) followed by the coin pickup sound, id 41 via 0x1FBB90/0x1FB2F8
#     exactly as the coin entity plays it. Splitting into several pops gives
#     the clinking of a real coin grab. The client writes COIN_AMOUNT before
#     COIN_POPS, since COIN_POPS is the trigger.
#
# Assemble + emit the hex blob:
#   llvm-mc --assemble --triple=mipsel --mcpu=mips64r2 --filetype=obj \
#     -o cave.o cave.s
#   llvm-objcopy -O binary --only-section=.text cave.o cave.bin
#   python3 -c "print(open('cave.bin','rb').read().hex())"
#
# Layout in the cave's free block: DEATH_FLAG=0x0042BF00, RA_SAVE=0x0042BF04,
# heartbeat=0x0042BF08, COIN_POPS=0x0042BF10, COIN_AMOUNT=0x0042BF14,
# COIN_TIMER=0x0042BF18, COIN_INTERVAL=0x0042BF1C, COIN_POP=0x0042BF20; the
# damage_info struct lives at 0x0042BE00. k0/k1 are never kept live across a
# call (an interrupt may clobber them), so state round-trips through memory.
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xbf08      # k0 = 0x0042BF08 (heartbeat counter)
	lw    $k1, 0($k0)
	addiu $k1, $k1, 1
	sw    $k1, 0($k0)           # bump every frame -> proves hook fires
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xbf04      # k0 = 0x0042BF04 (RA_SAVE)
	sw    $ra, 0($k0)
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xbf00      # k0 = 0x0042BF00 (DEATH_FLAG)
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
	ori   $a1, $a1, 0xbe00      # a1 = &damage_info @0x0042BE00
coins:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xbf10      # k0 = 0x0042BF10 (COIN_POPS)
	lw    $k1, 0($k0)
	beq   $k1, $zero, done
	nop
	lw    $k1, 8($k0)           # COIN_TIMER
	beq   $k1, $zero, pop
	addiu $k1, $k1, -1
	b     done
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
	ori   $k0, $k0, 0xbf20
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
done:
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xbf04
	lw    $ra, 0($k0)
	lw    $2, -11524($19)       # relocated original at 0x226674
	lw    $4, 8($20)            # relocated original at 0x226678
	j     0x22667c             # return to hook+8
	nop
