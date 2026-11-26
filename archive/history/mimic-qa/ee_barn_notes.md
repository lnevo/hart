## ee00_baseline
Live retain before tickle
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee01_110_thrown
110 THROWN = ladder diverge into East Lead. OS 110 should leave Stop.
turnouts: Switch 110=THROWN, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee02_110_closed
110 CLOSED. OS 110 should be Stop/red.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee03_111_thrown
111 THROWN = crossover. North 111 east/west should change.
turnouts: Switch 110=CLOSED, Switch 111=THROWN, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Stop          
East End East OS 111a                      Stop           Stop          
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Approach      
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee04_111_closed
111 CLOSED = Main West through WME. 111a Clear / West Main West Approach on CATS.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee05_112_closed
112 CLOSED = through OS110 / East Lead. OS 112 should Stop; East Lead dest OS 110.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=CLOSED, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Approach        MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Slow Clear      MISMATCH
East End East Lead                         Approach       Stop            MISMATCH
East End South OS 110                      Restricting    Stop            MISMATCH
East End South OS 112                      Stop           Stop          
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee06_112_thrown
112 THROWN = Barn / Main East. East Lead dest 117b; OS 112 dest 113a.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee07_117_thrown
117 THROWN = Barn crossover. Lower west Barn D should change.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=THROWN
mast                                       SML            CATS
West Yard West East Main Ext               Approach       Approach      
West Yard East OS 117b                     Approach       Stop            MISMATCH
West Yard West OS 117                      Stop           Stop          
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Approach       Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Approach        MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Stop           Clear           MISMATCH
Brick East Main West                       Stop           Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee08_117_closed
117 CLOSED = EME through Main East. Barn D Clear on CATS.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee09_main_east_occ
Main East occupied — 117b / OS 112 should Stop.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Stop          
West Yard East OS 117b                     Stop           Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Stop          
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Approach      
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee10_east_lead_occ
East Lead occupied — East Lead / OS 112 should Stop.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Approach        MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Stop           Stop          
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Stop          
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee11_main_west_occ
Main West occupied — 111a should Stop.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Approach      
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Stop          
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Stop            MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee12_wme_occ
West Main Ext occupied — West Main West / 115 should Stop.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Stop          
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Approach      
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee13_eme_occ
East Main Ext occupied — Plane EME / Barn D should Stop.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Stop            MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Approach       Approach      
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Approach        MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Stop           Clear           MISMATCH
Brick East Main West                       Stop           Stop          
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee14_os110_occ
OS 110 occupied.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee15_rest_clear
Occupancy restored; points at field rest.
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH

## ee99_restored
Restored MQTT retain
turnouts: Switch 110=CLOSED, Switch 111=CLOSED, Switch 112=THROWN, Switch 117=CLOSED
mast                                       SML            CATS
West Yard West East Main Ext               Stop           Clear           MISMATCH
West Yard East OS 117b                     Approach       Clear           MISMATCH
West Yard West OS 117                      Approach       Approach      
East End West Main West                    Stop           Approach        MISMATCH
East End East OS 111a                      Stop           Clear           MISMATCH
East End West Yard Track 1                 Restricting    Stop            MISMATCH
East End East Lead                         Stop           Clear           MISMATCH
East End South OS 110                      Stop           Stop          
East End South OS 112                      Stop           Clear           MISMATCH
Plane East East Main Ext                   Approach       Clear           MISMATCH
Brick East Main West                       Approach       Clear           MISMATCH
Princess West OS 113a                      Approach       Approach      
Princess West OS 113b                      Approach       Stop            MISMATCH
