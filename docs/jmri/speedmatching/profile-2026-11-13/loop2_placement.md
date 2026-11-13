# Loop 2 placement (2026-11-13)

Two passes (steps 24 and 48), then the one-lap survey. Neither is applied to `block_lengths.csv` yet.

## Passes

```
pass 1: CSX 2121 reverse step 24 (pass_CSX_2121_reverse_step24_20261113_154325.log, ended passed): 252.2 mm/s between the pins
  OS Switch 7 centre 4260 mm from Switch 5's points, 1649 mm before OS Switch 15's centre
  OS Switch 13 centre 5444 mm from Switch 5's points, 465 mm before OS Switch 15's centre
pass 2: CSX 2121 reverse step 48 (pass_CSX_2121_reverse_step48_20261113_154720.log, ended passed): 433.3 mm/s between the pins
  OS Switch 7 centre 4239 mm from Switch 5's points, 1670 mm before OS Switch 15's centre
  OS Switch 13 centre 5470 mm from Switch 5's points, 439 mm before OS Switch 15's centre
locate: OS Switch 7 centre 4249 mm from Switch 5's points, 1660 mm before OS Switch 15's centre (mean of 2 passes)
  passes differ by 21 mm (last minus first -21 mm)
locate: OS Switch 13 centre 5457 mm from Switch 5's points, 452 mm before OS Switch 15's centre (mean of 2 passes)
  passes differ by 27 mm (last minus first +27 mm)
```

## Survey (one usable lap only)

```
loop2: sensor                               mm   +-mm      in  laps
Switch 5                                  768      0    30.3     1
Scale                                    3527      0   138.9     1
Switch 7                                  406      0    16.0     1
Barn                                      777      0    30.6     1
Switch 13                                 411      0    16.2     1
Switch 15                                 497      0    19.5     1
S-R                                      5383      0   211.9     1
Switch 23b                                772      0    30.4     1
Switch 31                                 241      0     9.5     1
Switch 33                                 389      0    15.3     1
East Lead                                2602      0   102.4     1
Switch 35a                                364      0    14.3     1
Switch 37 / BS McKeesport                 441      0    17.4     1
K-2                                      2904      0   114.3     1
K-1                                      3036      0   119.5     1
Switch 39 / BS McKees Rocks               353      0    13.9     1
Switch 35b                                451      0    17.7     1
West Main Ext                            3958      0   155.8     1
Switch 23a                                676      0    26.6     1
Main West                                5485      0   215.9     1
Switch 1                                  545      0    21.4     1
Brick-Plane                              1443      0    56.8     1
total                                   35429   (plan loop 35429)
rows on both routes (loop 1 value from block_lengths.csv, this run beside it):
  Switch 5                           loop1     625 mm   loop2     768 mm     +144
  Switch 33                          loop1     315 mm   loop2     389 mm      +74
  East Lead                          loop1    2233 mm   loop2    2602 mm     +370
  Switch 35a                         loop1     381 mm   loop2     364 mm      -17
  Switch 37 / BS McKeesport          loop1     419 mm   loop2     441 mm      +22
  K-2                                loop1    2885 mm   loop2    2904 mm      +19
  K-1                                loop1    2743 mm   loop2    3036 mm     +293
  Switch 39 / BS McKees Rocks        loop1     244 mm   loop2     353 mm     +109
  Switch 35b                         loop1     521 mm   loop2     451 mm      -70
  West Main Ext                      loop1    3965 mm   loop2    3958 mm       -7
  Switch 23a                         loop1     597 mm   loop2     676 mm      +80
  Main West                          loop1    5519 mm   loop2    5485 mm      -35
  Switch 1                           loop1     574 mm   loop2     545 mm      -29
  Brick-Plane                        loop1    1476 mm   loop2    1443 mm      -32
locate: OS Switch 7 centre 4254 mm from Switch 5's points, 1639 mm before OS Switch 15's centre
locate: OS Switch 13 centre 5439 mm from Switch 5's points, 454 mm before OS Switch 15's centre
```
