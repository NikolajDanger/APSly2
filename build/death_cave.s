# Deathlink death-animation code cave (SCUS-97316). Source for DEATH_CAVE_BLOB
# in data/Constants.py. PINE cannot call game functions, so this cave is
# written into free EE RAM and the per-frame world-update loop (0x226550) is
# trampoline-hooked at 0x226674 to run it. On the client-set flag it calls the
# game's damage function (0x1A19A0) with a fabricated damage_info struct, which
# makes the game play a real, animated death.
#
# Assemble + emit the hex blob:
#   llvm-mc --assemble --triple=mipsel --mcpu=mips64r2 --filetype=obj \
#     -o death_cave.o death_cave.s
#   llvm-objcopy -O binary --only-section=.text death_cave.o death_cave.bin
#   python3 -c "print(open('death_cave.bin','rb').read().hex())"
#
# Layout in the cave's free block: FLAG=0x0042BF00, RA_SAVE=0x0042BF04,
# heartbeat=0x0042BF08; the damage_info struct lives at 0x0042BE00.
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
	ori   $k0, $k0, 0xbf00      # k0 = 0x0042BF00 (FLAG)
	lw    $k1, 0($k0)
	beq   $k1, $zero, done
	nop
	sw    $zero, 0($k0)         # clear FLAG
	lui   $k0, 0x002d
	ori   $k0, $k0, 0xe2f0      # k0 = 0x002DE2F0 (active char ptr)
	lw    $a0, 0($k0)
	beq   $a0, $zero, done      # no active character -> skip
	nop
	addiu $a0, $a0, 0x0df0      # a0 = entity+0xDF0 (damage block)
	lui   $a1, 0x0042
	ori   $a1, $a1, 0xbe00      # a1 = &damage_info @0x0042BE00
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xbf04      # k0 = 0x0042BF04 (RA_SAVE)
	sw    $ra, 0($k0)
	jal   0x1a19a0             # game damage function
	nop
	lui   $k0, 0x0042
	ori   $k0, $k0, 0xbf04
	lw    $ra, 0($k0)
done:
	lw    $2, -11524($19)       # relocated original at 0x226674
	lw    $4, 8($20)            # relocated original at 0x226678
	j     0x22667c             # return to hook+8
	nop
