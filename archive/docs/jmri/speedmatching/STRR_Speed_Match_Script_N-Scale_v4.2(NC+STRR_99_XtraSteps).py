# STRR_Speed_Match_Script_N-Scale_v4.2(NC+STRR_99_XtraSteps) (11-2025)  Compatible with JMRI 4.16 to at least 5.12 or possibly higher.  Works with JAVA 17.
#
#   First and foremost, this Speed matching script could not have been created without the help and previous work from the following people:
#   Authors: Phil Klein, Version 2.14 Copyright 2010
#           Eric W. Bradford Version UltimateSpeedMatch_v1.0 Copyright 2011
#           Thomas Stephens, Version SpeedTLSv5_B Copyright Jan 2013
#           Grit_City_Railroad Version Ultimate_Speed_Match_V2.0 Copyright 2019
#           jmriusers@groups.io Matthew Harris, Version Ultimate_Speed_Match_V2.0 Copyright 2019 (for updating the script for JMRI 4.16 compatibility)
#           Eric W. Bradford, Version UltimateSpeedMatch_V3.4 10-2025 (Modified for n-scale local club)
#
#   All of the gentlemen above have laid a great foundation for which I was able to build upon.  
#   This is not to take away from their work, only improve upon it by making modifications to make 1 great speed matching script for my local N-SCALE club (Short Track Rail Road in Vista,CA).
#   I have taken the liberty to remove items that are no longer being used or I feel is not necessary with regards to my local club.
#
#   This Script will automatically build a speed table for a decoder using OPS mode programming and create a text file on your desktop for future use.
#
#   Summary of how it works:
#   User enters info about locomotive and decoder such as Loco Number, DCC Address, Scale, Brand of decoder, CV3 and CV4 desired, direction to be tested, and top speed desired on the input panel.
#   A throttle is created in JMRI to run the locomotive.
#   The locomotive is warmed up for a few laps (in both directions if diesel is selected, forward direction for steam).
#   The top speed of the locomotive is measured (in both directions for diesels, forward direction from steam).
#   Using the block detectors to measure time, it adjusts the throttle until the appropriate speed is found for the speed step being measured.
#   9 Speed steps are measured; the rest are interpolated. The measured ones are 4, 8, 12, 16, 20, 24, and 28.
#   These are written to the decoder, a text file is created on your Windows PC desktop, and the locomotive is release from the throttle and the throttle is discarded.
#
#   If something goes wrong and you need to start over; "Steal" it in another throttle and stop the locomotive.
#   Close the input panel.
#   Under the "Panels" tab, select "Thread Monitor" and "Kill" the script.  Or just close JMRI and reopen JMRI software.
#
#   Notes:
#       BEMF    Any adjustments should be made before running the script
#
#           TCS - May need to turn off BEMF since it is not adjustable. A speed jump may be present
#               and maybe very noticeable after the speedtable is created
#
#           Digitax -
#               CV57 default value 6 may prevent the locomotive from going below about 5 mph
#               setting this to 33 improves this. Or turn it off by setting it to zero.  This Speed Matching script will set it to zero for you.
#
#           NCE - some older N scale decoders will revert to 28 step mode instead of 128 step mode (this may happen in HO as well)
#
#       The locomotives speed should be approximately equivlent to what is displayed on a throttle if the maximum speed was set to 100.
#           (running by itself without a train)
#
#   Hardware tested with this script:
#   Command Station - Digitrax DCS100, Digitrax Zypher, Pi-SPROG One, DCS200 with DT402 throttle
#   Train Detection - BDL168 (Board Address 1),Team Digital SIC24 with DBD22's 
#   Computer Interface - MS100, RR-Cirkits Locobuffer II, RR-Cirkits Locobuffer NG, PR3, PR4
#   
#   JMRI Software 4.16 OR GREATER IS REQUIRED for this script to work.  Confirmed to work up to 4.92 and expected to work up to 4.99.  Not verified to work with 5.0 thru 5.12 versions.

#   By opening up the JMRI Sysem Console screen ("Help Tab" then "System console"), one can see what is being done on the track.  Useful for problem solving.
#
#   Track - 12 pieces of Kato N scale 19" Radius Unitrak
#   I used one sensor for every 2 pieces of N scale track
#   The N tracks share sensors 1 - 12
#
#   Past changes and added functions from multiple authors are listed below.
#   Added step list for ESU decoders
#   Added redo time measurement when start time and stop time are the same when using the MS100
#   Fixed writing values higher than 255 to the decoder
#   Fixed writing values lower than 1
#   Added STEAM to input panel to see if that accomodates tender pickup issues
#       Steam locomotives should be placed on the track so that the wheels that pick up power
#       on the tenders front truck are on the rail that is detected to reduce errors.
#   Added the ability for the user to select the top speed
#   Added "Atlas" to user selectable decoders
#   05/28/08    Added CV25 = 0 If decoder was using a predefined table, can't get accurate measurements
#   08/18/08    Fixed Atlas...should have been Atlas/Lenz XF
#   08/25/08    Added waits after writing CV's 62, 25 and 29  possible issue with Zypher not sending write CV29 command
#   08/26/08    Changed speedtable setting for testing 128 support from 120 to 84
#   09/09/08    Seperated testing for 128 support for N scale.
#   09/11/08    Add displaying of throttle setting chosen for given speed step
#   09/22/08    Added "Done != True"  to fine measurement.  Was changing throttle setting even though we were done 
#   09/22/08    Increased wait times after writing CV's before warm up  QSI decoders weren't getting all of them  was 250msec, now 500
#   01/09/09    TCS decoders would not run after initial ops mode programming
#   01/09/09    TCS decoders stall when using values above 249 
#   06/15/09    Changed Soundtraxx to Soundtraxx DCD in preparation for adding Soundtraxx Tsunami 
#   06/26/09    Added Soundtraxx Tsunami
#   08/28/09    Increased wait time when writing table from 100ms to 150ms  DZ121 was getting zero written for every other entry 
#   09/11/09    Added cycling track power before starting.
#   09/15/09    Created new list for newer TCS decoders
#   09/15/09    Created test to determine which TCS list to use
#   09/15/09    Increased wait time when measuring max speed.  Tsunami was missing direction change
#   09/15/09    Added wait time when turning on speed table.  Tsunami was missing change to CV29
#   09/17/09    Removed "Unknown" from selection list.  Getting too hard to support 
#   09/17/09    Fixed throttlesetting from being set above 127 
#   09/17/09    Moved comparison of hithrottle & lowthrottle into coarse measurement
#   09/18/09    Added a second forward statment when measuring fwd max speed. Sometimes doesn't execute
#   05/21/10    Changed getOpsModeProgrammer to getAddressedeProgrammer something changed between 2.8 and 2.9.6
#   05/21/10    Warmup for steam now only goes forward
#   03/17/12    Added prompts for acel/decel values (CV3/4), Sets value when done
#   03/17/12    Added prompt for target direction. Replaces calculation based on max speed
#   03/17/12    Increased numbers of values in countsensor to compensate for odd values on specific track sections
#   02/18/13    Changed number of measurements from 1 to 4 for 100 mph by adding a "high speed array"..
#   02/18/13    Corrected decoder lists for speed measurements.  Wrong list being used due to python coding issues.
#   02/18/13    Set up that if user forgets to choose scale, default is N-SCALE.
#   02/18/13    Text File now being created on windows PC desktop (at least for Win XP) for future use.
#   02/18/13    Added comments by commands throughout the script to help others understand what is taking place.
#   03/20/13    Reverted change to let different brands run together.
#   03/24/13    Changed CV3&4 defaults to 4
#   03/24/13    Changed initial dialog position. Was showing mostly off screen.
#   11/17/19    Added Linux Text Output, Changed Some Defaults, Started correcting easy Errors to make compatile with JMRI 4.16
#   12/05/19    Matthew Harris corrected complicated Errors to make compatible with JMRI 4.16 - Update references to PowerManager - Update deprecated references to writeCv
#   8/1/2025    Eric W. Bradford modified script to be only for N-Scale.  Added Max Speed Array for determining max forward-reverse speeds.  Adjusted course and fine adjustments when determining each speed step.
#   8/18/2025   Eric W. Bradford confirmed latest script can run on JAVA 17 and JMRI 5.12 with no observed issues.
#   11/12/2025  Eric W. Bradford changed interpolation code and number of speed steps measured.  Set top speed default as 99 to align with Digitrax throttles.
#   11/12/2025  Python code improvements require python code to use 0-27 speed steps until time of writing to loco, then it changes to 1-28 speed steps.  Same with writing CV values.
#   11/12/2025  Eric W. Bradford change input window options and file output info.

# SCRIPT BEGINS HERE

import java
import javax.swing
import jmri
import datetime #added Date to printout 8/10/24 PhilA

class AutoSpeedTable(jmri.jmrit.automat.AbstractAutomaton) :
    

    # individual block section length (scale feet)
    blockN = float(132.6450)  # 132.6450 arc length feet Phil's test track

    long = False
    # +++ TLS 3/17/12 more test numbers. was 5. Compensate for odd values on specific track sections
    countsensor = 7 # Use 1 for testing and 6 for running

    # init() is called exactly once at the beginning to do
    # any necessary configuration.
    def init(self):

        self.sensor1 = sensors.provideSensor("LS1")
        self.sensor2 = sensors.provideSensor("LS2")
        self.sensor3 = sensors.provideSensor("LS3")
        self.sensor4 = sensors.provideSensor("LS4")
        self.sensor5 = sensors.provideSensor("LS5")
        self.sensor6 = sensors.provideSensor("LS6")
        self.sensor7 = sensors.provideSensor("LS7")
        self.sensor8 = sensors.provideSensor("LS8")
        self.sensor9 = sensors.provideSensor("LS9")
        self.sensor10 = sensors.provideSensor("LS10")
        self.sensor11 = sensors.provideSensor("LS11")
        self.sensor12 = sensors.provideSensor("LS12")

        self.memory1 = memories.provideMemory("1")
        self.memory2 = memories.provideMemory("2")
        self.memory3 = memories.provideMemory("3")
        self.memory4 = memories.provideMemory("4")
        self.memory5 = memories.provideMemory("5")
        self.memory6 = memories.provideMemory("6")
        self.memory7 = memories.provideMemory("7")
        self.memory8 = memories.provideMemory("8")
        self.memory9 = memories.provideMemory("9")
        self.memory10 = memories.provideMemory("10")
        self.memory11 = memories.provideMemory("11")
        self.memory12 = memories.provideMemory("12")
        self.memory20 = memories.provideMemory("20")        #Stores the selection of "Forward" or "Reverse" for speed matching direction
        self.memory21 = memories.provideMemory("21")        #Stores max reverse speed found.
        self.memory22 = memories.provideMemory("22")        #Stores max forward speed found.
        self.memory23 = memories.provideMemory("23")        #Stores DCC Decoder brand.
        self.memory24 = memories.provideMemory("24")        #Stores target speeds being determined on speed table.
        self.memory25 = memories.provideMemory("25")        #Stores messages to be displayed in script output window.
        self.memory26 = memories.provideMemory("26")        #Stores if Sound Decocder is present in locomotive
        

        
        #EWB -- Used for when top is set to 99 MPH (setting for Digitrax DT400 throttle)
        #EWB -- MaxSpeedArray created to utilize 4 blocks for each measurment. If 6 blocks are needed, you will use 2 sensors (1 and 7 only).
        self.MaxSpeedArray = (
                self.sensor1,
                self.sensor5,
                self.sensor9)
                
        #EWB--Wanted to take 3 measurements at higher speeds instead of just 1 measurement per lap. Uses 3 blocks for each measurement above 80 MPH.
        self.HighSpeedArray = (
                self.sensor1,
                self.sensor4,
                self.sensor7, 
                self.sensor10)

        #Used for speeds between 40 and 80 MPH
        #Uses 2 blocks for each measurement
        self.MediumSpeedArray = (
                self.sensor1,
                self.sensor3,
                self.sensor5,
                self.sensor7,
                self.sensor9,
                self.sensor11)

        # used below 50 MPH 
        #Uses single blocks for measurements
        self.LowSpeedArray = (
                self.sensor1,
                self.sensor2,
                self.sensor3,
                self.sensor4,
                self.sensor5,
                self.sensor6,
                self.sensor7,
                self.sensor8,
                self.sensor9,
                self.sensor10,
                self.sensor11,
                self.sensor12)


#       These speed steps are measured.  All others are calculated
#               CV  70  73  76  79  82  85  88  91  94
#       Speedsteps  4   7   10  13  16  19  22  25  28 
#     Python index  3   6   9   12  15  18  21  24  27

    # The step list below applies to all decoders and the values shown are percentages of full speed
        self.SpeedTargets = [11, 22, 33, 44, 55, 66, 77, 88, 99]        ##EWB This is the only StepList that is used by this script.  Numbers determined to align digitrax physical throttle setting to n-scale MPH.

# Getting throttle
        
        self.status.text = "Getting throttle"

        dccnumber = int(self.dccaddress.text)   #EWB -- Used for file naming confusion and text file information
        loconumber = int(self.locoaddress.text)  #EWB -- created to help with file naming confusion or duplicates
        if (dccnumber > 127) :
             self.long = True
        else :
             self.long = False
        self.throttle = self.getThrottle(dccnumber, self.long)
        if (self.throttle == None) :
             print "Couldn't assign throttle!"
        else :
            print
            print
            print
            print "Locomotive number",loconumber, "with DCC Address",dccnumber

    # Getting Programmer
        self.programmer = addressedProgrammers.getAddressedProgrammer(self.long, dccnumber)

        return
#----------------------------------------------------------------
    def measuretime(self,sensorlist,blocklength,starttime,stoptime) :

        """Measures the time between virtual blocks"""
        if starttime == 0 :
            self.waitChange(sensorlist)
            self.waitSensorActive(sensorlist)
            stoptime = java.lang.System.currentTimeMillis() 

        starttime = stoptime

        self.waitChange(sensorlist)
        self.waitChange(sensorlist)
        self.waitSensorActive(sensorlist)

        stoptime = java.lang.System.currentTimeMillis()
        runtime = stoptime - starttime
        return runtime, starttime, stoptime
    #---------------------------------------------------------------
    def getspeed(self,targetspeed,block) :      #"""converts time to speed, ft/sec - scale speed"""
        starttime = stoptime = 0    # Needed when using every block
        self.memory24.value = str(targetspeed)

        speedlist = []  # Clear Speedlist (speed list contains measured speeds for each run)

        self.waitSensorInactive(self.LowSpeedArray)     #Making sure locomotive is at the correct starting position

        for z in range(1,self.countsensor + 1) : # make <countsensor> speed measurements
            if int(targetspeed) >= 95 : #Used for determining max forward and reverse speeds
                if block == 132.6450 :
                    blocklength = block * 4    # Phil's N scale loop has 12 blocks
                else :
                    blocklength = block * 4    
                duration, starttime, stoptime = self.measuretime(self.MaxSpeedArray,blocklength,starttime,stoptime)
            
            elif int(targetspeed) >= 75 :  # EWB -- Used for final speed steps.
                blocklength = block * 3     #makes 3-block measurements
                duration, starttime, stoptime = self.measuretime(self.HighSpeedArray,blocklength,starttime,stoptime)  #makes 4-block measurements

            elif int(targetspeed) >= 40 :   # EWB -- Used for speed steps between 40 and 79 mph.
                blocklength = block * 2     # makes 2-block measurements
                duration, starttime, stoptime = self.measuretime(self.MediumSpeedArray,blocklength,starttime,stoptime)  # makes 2-block measurements
            else :
                blocklength = block * 1     #EWB -- Used for speed steps 1 and 40 mph.
                duration, starttime, stoptime = self.measuretime(self.LowSpeedArray,blocklength,starttime,stoptime) #makes 1-block measurements
            
            if duration == 0 :
                print "Measurement #",z," duration = ",duration
                z = z - 1
                print "got a zero for duration" # this has occured when using a MS100
                print "        Measurement #",z
            else :

                speed = (blocklength / (duration / 1000.0)) * (3600.0 / 5280)   
                speedlist.append(speed)

                print "Measured Speed MPH =",round(speed,1) , " Measurement #",z
                self.status.text = "Measured Speed = " + str(round(speed,1)) + " MPH"

                if self.sensor1.knownState==ACTIVE:                     #Memory values offset by # of blocks; delta of 6, 4, 3, and 2 blocks.
                    self.memory1.value = str(round(speed))
                    self.memory7.value = " "
                    self.memory9.value = " "
                    self.memory10.value = " "
                    self.memory11.value = " "
                    print "[Block 1]"

                elif self.sensor2.knownState==ACTIVE:
                    self.memory2.value = str(round(speed))
                    self.memory8.value = " "
                    self.memory10.value = " "
                    self.memory11.value = " "
                    self.memory12.value = " "
                    print "[Block 2]"
                
                elif self.sensor3.knownState==ACTIVE:
                    self.memory3.value = str(round(speed))
                    self.memory9.value = " "
                    self.memory11.value = " "
                    self.memory12.value = " "
                    self.memory1.value = " "
                    print "[Block 3]"

                elif self.sensor4.knownState==ACTIVE:
                    self.memory4.value = str(round(speed)) 
                    self.memory10.value = " "
                    self.memory12.value = " "
                    self.memory1.value = " "
                    self.memory2.value = " "
                    print "[Block 4]"
                
                elif self.sensor5.knownState==ACTIVE:
                    self.memory5.value = str(round(speed)) 
                    self.memory11.value = " "
                    self.memory1.value = " "
                    self.memory2.value = " "
                    self.memory3.value = " "
                    print "[Block 5]"
                
                elif self.sensor6.knownState==ACTIVE:
                    self.memory6.value = str(round(speed)) 
                    self.memory12.value = " "
                    self.memory2.value = " "
                    self.memory3.value = " "
                    self.memory4.value = " "
                    print "[Block 6]"
                
                elif self.sensor7.knownState==ACTIVE:
                    self.memory7.value = str(round(speed)) 
                    self.memory1.value = " "
                    self.memory3.value = " "
                    self.memory4.value = " "
                    self.memory5.value = " "
                    print "[Block 7]"
                
                elif self.sensor8.knownState==ACTIVE:
                    self.memory8.value = str(round(speed)) 
                    self.memory2.value = " "
                    self.memory4.value = " "
                    self.memory5.value = " "
                    self.memory6.value = " "
                    print "[Block 8]"
                
                elif self.sensor9.knownState==ACTIVE:
                    self.memory9.value = str(round(speed)) 
                    self.memory3.value = " "
                    self.memory5.value = " "
                    self.memory6.value = " "
                    self.memory7.value = " "
                    print "[Block 9]"
                
                elif self.sensor10.knownState==ACTIVE:
                    self.memory10.value = str(round(speed)) 
                    self.memory4.value = " "
                    self.memory6.value = " "
                    self.memory7.value = " "
                    self.memory8.value = " "
                    print "[Block 10]"
                
                elif self.sensor11.knownState==ACTIVE:
                    self.memory11.value = str(round(speed)) 
                    self.memory5.value = " "
                    self.memory7.value = " "
                    self.memory8.value = " "
                    self.memory9.value = " "
                    print "[Block 11]"
                
                elif self.sensor12.knownState==ACTIVE:
                    self.memory12.value = str(round(speed)) 
                    self.memory6.value = " "
                    self.memory8.value = " "
                    self.memory9.value = " "
                    self.memory10.value = " "
                    print "[Block 12]"


    # EWB-- select the median from the list and use it as the measured speed
        def calc_median(speedlist):
            n = len(speedlist)
            if n == 0:
                return 0.0
            s = sorted(speedlist)
            mid = n // 2
            return s[mid] if n % 2 == 1 else (s[mid - 1] + s[mid]) / 2.0
             
        speed = calc_median (speedlist) #EWB-- calculates median of values in list of measurements.

        return speed
#---------------------------------------------------------------

# handle() will only execute once here, to run a single test
#EWB -- Any "print" command starting from here will show up in the JMRI Sysem Console screen ("Help Tab" then "System console")
    
    def handle(self):
    
        print "STRR+NC+ExtraSteps_Ultimate_Speed_Match_v4.2 --- 11/15/2025"

        self.memory25.value = "Preparing Locomotive for speed measurments"

#09/11/09
        jmri.InstanceManager.getDefault(jmri.PowerManager).setPower(jmri.PowerManager.OFF)
        self.waitMsec(1000)
        jmri.InstanceManager.getDefault(jmri.PowerManager).setPower(jmri.PowerManager.ON)
        self.waitMsec(1000)
        self.throttle.speedSetting = 0.
        self.waitMsec(500)
        starttesttime = java.lang.System.currentTimeMillis()
        badlocomotive = False # will be true if locomotive will not go slow enough

        self.memory1.value = " "
        self.memory2.value = " "
        self.memory3.value = " "
        self.memory4.value = " "
        self.memory5.value = " "
        self.memory6.value = " "
        self.memory7.value = " "
        self.memory8.value = " "
        self.memory9.value = " "
        self.memory10.value = " "
        self.memory11.value = " "
        self.memory12.value = " "


    #First line is Default
        block = self.blockN  

        print self.Scale.getSelectedItem()
        
        print "Todays date is ", datetime.date.today()

        print "Type of Locomotive is", self.Locomotive.getSelectedItem()
                        
        print "Decoder Brand is", self.DecoderBrand.getSelectedItem()
        self.memory23.value = self.DecoderBrand.getSelectedItem()
        
        decodertype = self.DecoderBrand.getSelectedItem()
        print "Is this a Sound Decoder? ", self.DecoderSound.getSelectedItem()
        self.memory26.value = self.DecoderSound.getSelectedItem()
        decodersoundYN = self.DecoderSound.getSelectedItem()
        
        print "CV3 will be set to",self.cv3.text
        print "CV4 will be set to",self.cv4.text
        
        screendisplay = float(self.MaxSpeed.text)   #used for display purposes
        topspeed = float(self.MaxSpeed.text)/99.4    # Used for calculation purposes; aligns max speed of 99 to align to 99% Digigrax throttle reading 
        print "Desired Top N-Scale Speed is",screendisplay, "MPH"
        self.status.text = "Locomotive Setup"
                
        print "Speed Matching Direction is set to", self.SetDirection.getSelectedItem()     #This is based on the orientation of the locomotive and the direction you want it speedmatched.
        print "--------------------------------------------"
        print "============================================\n"
 
    # This will change FX Rate and Keep Alive on Digitrax Decoders
    # This will change Random Sound Max on ESU LokSound Decoders
    # 08/25/08
    # 09/22/08
        if decodertype == "QSI-BLI" :
            self.programmer.writeCV("62", 0, None) # Turn off verbal reporting on QSI decoders
            self.waitMsec(1000)

        if decodertype == "Digitrax" :
            self.programmer.writeCV("57", 0, None) # Turn OFF Back EMF as per note above.
            self.waitMsec(1000)
            
        self.programmer.writeCV("25", 0, None) # Turn off manufacture defined speed tables
        self.waitMsec(1000)

        if self.long == True :          #turn off speed tables
            self.programmer.writeCV("29", 34, None)
        else:
            self.programmer.writeCV("29", 18, None)     # originally was "2"; for turning on analog function of DCC chip; set for 2 digit - no analog - 128 steps

        self.waitMsec(1000)
        
        self.programmer.writeCV("3", 0, None)   #Acceleration off
        self.waitMsec(1000)
        self.programmer.writeCV("4", 0, None)   #Deceleration off
        self.waitMsec(1000)
        self.programmer.writeCV("19", 0, None)  #Clear consist
        self.waitMsec(1000)
        self.programmer.writeCV("66", 0, None) #Turn off Forward Trim
        self.waitMsec(1000)
        self.programmer.writeCV("95", 0, None) #Turn off reverse Trim
        self.waitMsec(1000)

# Run Locomotive for certain number of laps each direction to warm it up

        self.memory25.value = "Warming up Locomotive"
        self.status.text = "Warming up Locomotive"
        print
        print "Warming up Locomotive"
        print
        self.throttle.setIsForward(True)
        self.memory20.value = "Forward"

        self.throttle.setF0(True)
        self.throttle.setF8(True)

# Warm up locomotive for certain number of laps forward
#01/09/09   TCS decoder would not move when setting throttle to 1.0
        self.throttle.speedSetting = .99
        self.waitMsec(500)
        self.throttle.speedSetting = 1.0

        for x in range (1, 4) :     # Warm up locomotive for 2 laps forward
            self.waitChange([self.sensor1])
            self.waitSensorActive(self.sensor1)

        self.throttle.speedSetting = 0.0
        self.waitMsec(2000)

 # Warm up certain number of laps reverse

#05/21/10   Removed reverse warmup and max speed measurement for Steam

        if self.Locomotive.getSelectedItem() == "Diesel" :
            self.throttle.setIsForward(False)
            self.memory20.value = "Reverse"
            self.throttle.speedSetting = 1.0

            for x in range (1, 4) :
                self.waitChange([self.sensor1])
                self.waitSensorActive(self.sensor1)

    # Find maximum speed reverse

            self.memory25.value = "Finding Maximum N-Scale Speeds"
            print "Finding Maximum N-Scale Speeds"
            self.throttle.speedSetting = 1.0
            self.waitMsec(500)
            revmaxspeed = self.getspeed(95,block)      #Uses code that calls out 95 target speed and the use of 4 speed sensor blocks. Lines 266-283 above.
            print
            print "Reverse Max N-Scale Speed = ",round(revmaxspeed), "MPH"
            print
            self.throttle.speedSetting = 0.0
            self.status.text = "Max Reverse N-Scale Speed = " + str(int(revmaxspeed))
            
#09/15/09
            self.waitMsec(3000)

#05/21/10
        else :
            revmaxspeed = 0
        
        self.memory21.value = str(int(revmaxspeed))



#09/18/09       # Find maximum speed forward
        self.throttle.setIsForward(True)
        self.waitMsec(500)
        self.throttle.setIsForward(True)
        self.waitMsec(500)
        self.memory20.value = "Forward"
        self.throttle.speedSetting = 1.0
        self.waitMsec(1000)
        print "Finding Maximum Forward N-Scale Speeds"
        fwdmaxspeed = self.getspeed(95,block)          #Uses code that calls out 95 target speed and the use of 4 speed sensor blocks. Lines 266-283 above.
        print
        print "Forward Max N-Scale Speed = ",round(fwdmaxspeed), "MPH"
        print
        self.throttle.speedSetting = 0.0
        self.status.text = "Max Forward N-Scale Speed " + str(int(fwdmaxspeed))
        self.memory22.value = str(int(fwdmaxspeed))
        self.waitMsec(1000)
        
        self.memory23.value = decodertype
        print "Decoder Brand Installed is ",decodertype

# 3/24/2013 Removed decoder specific steplist. Was preventing different decoder types from running together
# Not needed anyway as speed determined from actual measurement of physical speed.

        steplist = self.SpeedTargets
        self.throttle.speedSetting = 0.0
        self.waitMsec(2000)


#we are now ready to build a speedtable
        if decodertype <> "Unknown" :

            self.memory25.value = "Measuring N-Scale Speeds"

#Turn off speed table for measurements
            if self.long == True :
                self.programmer.writeCV("29", 34, None)
            else:
                self.programmer.writeCV("29", 2, None)

#set direction based on user selection
# ++ TLS
            if self.SetDirection.getSelectedItem() == "Forward" :
                self.throttle.setIsForward(True)
                self.memory20.value = "Forward"
            else:
                self.throttle.setIsForward(False)
                self.memory20.value = "Reverse"

#Find throttle setting that gives desired speed

            stepvaluelist = [0]
            throttlesetting = 45    #EWB -- starting throttle setting increased by 5 units (determined by lots of testing)
            lowthrottle = 0 

# ------------------------------------------------------------
    # Force the throttle into a specific speed step mode
            try:
                self.throttle.setSpeedStepMode(jmri.Throttle.SpeedStepMode128)
                print "Throttle speed step mode set to 128-step."
            except:
                print "Could not set throttle mode directly; using JMRI default."
                print "Throttle is currently using:", self.throttle.speedStepMode
# ------------------------------------------------------------
            
            for speedvalue in steplist :
                targetspeed = round(speedvalue * topspeed)   

                print
                print
                print 
                print "TARGET SPEED BEING MEASURED IS: ",targetspeed, " MPH"

                stepvaluelist.extend([0,0]) #create spots in list for calculated speed steps

    #initializing all variables for next measured speed step
                Done = False
                speed = 1000
                minimumdifference = 20
                beenupone = False
                beendownone = False
                lowspeed = 0    
                hispeed = 1000
                hithrottle = 127

#05/21/10
                if ((self.Locomotive.getSelectedItem() == "Diesel") and (targetspeed > revmaxspeed)) or targetspeed > fwdmaxspeed :
                    print
                    print "Locomotive can not reach ",targetspeed, " MPH"
                    print
                    Done = True
                    throttlesetting = 127

                while Done == False:
#---------------------------------------------------------------------------------------------
    # Measure speed on test track
    # Measure speed
                    self.throttle.speedSetting = (.0079365 * throttlesetting)
                    self.waitMsec(250)
                    print
                    print "Throttle Setting ",throttlesetting,"      TARGET SPEED IS: ",targetspeed, "MPH"
                    MeasuredSpeed = self.getspeed(targetspeed,block)
 
                    # compare it to desired speed and decide whether or not to test a different throttle setting
                    difference = targetspeed - MeasuredSpeed
                    print
                    print "Difference = ",round(MeasuredSpeed - targetspeed,1), "MPH at throttle setting",throttlesetting
                    print

    #Coarse Measurement
                    if difference < -10 and targetspeed < 20 and throttlesetting > 15 : #started at 45 want to drop fast to reduce time
                        hithrottle = throttlesetting
                        throttlesetting = throttlesetting - 5
                        if throttlesetting < lowthrottle :
                            print "Throttle setting ",throttlesetting,"is too slow"
                            throttlesetting = lowthrottle + 1
#09/17/09
                            if hithrottle-lowthrottle < 2 :
                                Done = True
                                if (hispeed - targetspeed) > (targetspeed - lowspeed) :
                                    throttlesetting = lowthrottle
                                else :
                                    throttlesetting = hithrottle     

                    elif difference < -13 and throttlesetting > 15 : # keep throttle setting > 0
                        hithrottle = throttlesetting
                        throttlesetting = throttlesetting - 6    # and don't want drastic changes
                        if throttlesetting < lowthrottle :
                            print "Throttle setting ",throttlesetting,"is too slow"

                            throttlesetting = lowthrottle + 1
#09/17/09
                            if hithrottle-lowthrottle < 2 :
                                Done = True
                                if (hispeed - targetspeed) > (targetspeed - lowspeed) :
                                    throttlesetting = lowthrottle
                                else :
                                    throttlesetting = hithrottle

                    elif difference < -8 and throttlesetting > 6 : # keep throttle setting > 0
                        hithrottle = throttlesetting
                        throttlesetting = throttlesetting - 3
                        if throttlesetting < lowthrottle :
                            print "Throttle setting ",throttlesetting,"is too slow"
                            throttlesetting = lowthrottle + 1
#09/17/09
                            if hithrottle-lowthrottle < 2 :
                                Done = True
                                if (hispeed - targetspeed) > (targetspeed - lowspeed) :
                                    throttlesetting = lowthrottle
                                else :
                                    throttlesetting = hithrottle

                    elif difference > 13 and throttlesetting < 121 : # keep throtte setting < 128
                        lowthrottle = throttlesetting
                        throttlesetting = throttlesetting + 7
                        if throttlesetting > hithrottle :
                            print "Throttle setting ",throttlesetting,"is too fast"
                            throttlesetting = hithrottle - 1
                    elif difference > 8 and throttlesetting < 123 : # keep throtte setting < 128
                        lowthrottle = throttlesetting
                        throttlesetting = throttlesetting + 4
                        if throttlesetting > hithrottle :
                            print "Throttle setting ",throttlesetting,"is too fast"
                            throttlesetting = hithrottle - 1
                    elif difference > 5 and targetspeed < 20 and throttlesetting > 10 : #for motors that need a lot at the beginning
                        lowthrottle = throttlesetting
                        throttlesetting = throttlesetting + 5
                        if throttlesetting > hithrottle :
                            print "Throttle setting ",throttlesetting,"is too fast"
                            throttlesetting = hithrottle - 1

                    else :
                        #Fine Measurement
                        if minimumdifference > abs(difference) :
                            minimumdifference = abs(difference)
                            savethrottlesetting = throttlesetting
                        elif beenupone == True and beendownone == True :
                            Done = True
                            throttlesetting = savethrottlesetting
                            lowthrottle = throttlesetting + 1

#09/11/08   added print
                            print "Closest throttle setting is ", throttlesetting, "   On to next speed step"
#09/22/08

                        if difference < 0  and Done != True :
                            throttlesetting = throttlesetting - 1
                            beendownone = True
                        elif difference > 0 and Done != True :
                            throttlesetting = throttlesetting + 1
                            lowthrottle = throttlesetting
                            beenupone = True
                        else :
                            Done = True
                            throttlesetting = savethrottlesetting
                            lowthrottle = throttlesetting + 1

                    if throttlesetting < 1 :
                        print
                        print "Cannot create speedtable"
                        print "Locomotive has mechanical or decoder problems"
                        print
                        Done = True
                        badlocomotive = True
                        throttlesetting = 1
    
                    if throttlesetting > 127 :
                        print
                        print "Locomotive can not reach ",targetspeed, " MPH"
                        print
                        Done = True
                        throttlesetting = 127

                lowthrottle = throttlesetting
                if difference < -3 :        #changed from -5 to provide better average ccuracy and smallest variation
                    stepvaluelist.append(int(round((throttlesetting - .5) * 2.008)))
                elif difference > 3 :
                    stepvaluelist.append(int(round((throttlesetting + .5) * 2.008)))        #changed from -5 to provide better average ccuracy and smallest variation
                else :
                    stepvaluelist.append(int(round(throttlesetting * 2.008)))
                throttlesetting = throttlesetting + 9   # EWB -- Changed value from 10 to 7 to decrease time it takes to find each target speed.
                                                        # no need test a value already in the table
                                                        # time to do the next speed step

        #09/17/09   had instance where prior statment set speed to 128
                if throttlesetting > 127 :
                    throttlsetting = 127

        # Stop locomotive

            self.throttle.speedSetting = 0.0
            self.waitMsec(3000)

        #Calculate speed step values inbetween measured ones (python index "[]" begin at zero; index of 4 = 0,1,2,3)

            if badlocomotive == False:
                stepvaluelist.insert(0,0)   #create extra spot at beginning of list for calculated speed steps at low end; index is now [0,0,0,0,measured #,0,0,measured #,...]
                print
                print "Measured Values"
                print stepvaluelist
                print

        # Ensure first measured anchor has a minimum value
                if stepvaluelist[4] < 4 :
                    stepvaluelist[4] = 4

            # --- Bottom-end extrapolation (0–4) ---
                if stepvaluelist[4] != 0 and stepvaluelist[7] != 0:
                    # Compute stepvaluelist[0]
                    slope74 = (stepvaluelist[7] - stepvaluelist[4]) / 3
                    stepvaluelist[0] = stepvaluelist[4] - (slope74 * 4)     #trying to improve the bottom end performance using slope between [7] and [4]

            # making sure none of the speedsteps are < 1
                    if ((stepvaluelist[4] - stepvaluelist[0]) / 4) + stepvaluelist[0] < 1 :
                        stepvaluelist[0] = 0
                    print("Extrapolated stepvaluelist[0] =", stepvaluelist[0])
        
            # Compute first interpolated step above base [0]
                    slope40 = (stepvaluelist[4] - stepvaluelist[0]) / 4
                    stepvaluelist[1] = stepvaluelist[4] - (slope40 * 3)    ##trying to improve the bottom end performance using slope between [4] and [0]
                                
                else:
                    print("Anchors [4] and [7] not ready — skipping low-end extrapolation")

# --- Standard 2-step interpolation for remaining anchors ---
# Only loop over measured anchors (4,7,10,...)
                
                for  z in range (4, 29, 3) :
                    
                    # Ensure each measured anchor is at least slightly larger than previous
                    if stepvaluelist[z] - stepvaluelist[z - 3] < 1:
                        stepvaluelist[z] = stepvaluelist[z - 3] + 3
                    elif stepvaluelist[z] - stepvaluelist[z - 3] < 2:
                        stepvaluelist[z] = stepvaluelist[z - 3] + 2
                    elif stepvaluelist[z] - stepvaluelist[z - 3] < 3:
                        stepvaluelist[z] = stepvaluelist[z - 3] + 1

                    if stepvaluelist[z] > 255 : #can't have a value greater than 255
                        stepvaluelist[z] = 255
 


            # 3-step interpolation between previous and current anchor; # Create calculated speed steps
                    y = stepvaluelist[z] - stepvaluelist[z - 3]
                    x = y / 3.0
                    stepvaluelist[z - 2] = stepvaluelist[z] - round(2 * x)
                    stepvaluelist[z - 1] = stepvaluelist[z] - round(x)
                    

                    
#01/09/09   some TCS decoders will stop if a speed step value is 250 or greater

                if decodertype == "TCS" :
                    print
                    print "Values before TCS correction"
                    print stepvaluelist
                    print
                    counter = 0
                    for  z in range (21, 29, 1) :
                        #print "z= ",z," ",stepvaluelist[z],"counter = ",counter
                        if stepvaluelist[z] > 242 + counter:
                            stepvaluelist[z] = 242 + counter
                        counter = counter + 1
                print"Turn on acceleration and deceleration"    # Turn on acceleration and deceleration 
                print "Writing value to CV3: ",self.cv3.text
                self.programmer.writeCV("3", int(self.cv3.text), None)  #Acceleration changed to user setting from input panel.
                self.waitMsec(1000)
                print "Writing value to CV4: ",self.cv4.text
                self.programmer.writeCV("4", int(self.cv4.text), None)  #Deceleration changed to user setting from input panel.
                self.programmer.writeCV("29", 50, None)  #note: CV29 set to use speed table, 28/128 speed steps, forward direction, analog off.
                self.waitMsec(250)

                print
                print "All Speed Table CV Values"
                print stepvaluelist     #Displays whole range of speed table values on JMRI system console.
                print
                print "Writing Speed Table CV Values to Locomotive"

                
                if decodersoundYN == "Yes" :
                    for z in range (67, 95) :
                        print "CV",z," = ", int(stepvaluelist[z - 66])
                        self.programmer.writeCV(str(z), int(stepvaluelist[z - 66]), None)
                        #08/28/09
                        self.waitMsec(2000)     # Added 1 extra second to make sure sound decoder is programmed correctly.  May need to be increased.
                
                else :
                    for z in range (67, 95) :
                        print "CV",z," = ", int(stepvaluelist[z - 66])
                        self.programmer.writeCV(str(z), int(stepvaluelist[z - 66]), None)
                        #08/28/09
                        self.waitMsec(1000)
                print
                print "Turn on speed table"
                # Re-enable JMRI speed profile after CV programming is complete
                print
#06/28/09
                if decodertype == "SoundtraxxDSD" or decodertype == "Tsunami" :         
                    self.programmer.writeCV("25", 16, None)
                    #09/15/09
                    self.waitMsec(2000)
                    
                if decodertype == "QSI-BLI" :
                    self.programmer.writeCV("25", 1, None)
                
                if self.long == True :
                    self.programmer.writeCV("29", 50, None) #note: CV29 set to use speed table, 28/128 speed steps, forward direction, analog off.
                else:
                    self.programmer.writeCV("29", 18, None) #CV29 set to use speed table, 28/128 speed steps, forward direction, analog off. 2 digit DCC

#Uncomment for Windows or Linux                
                self.outfilename = "C:/Users/ericw/OneDrive/Desktop/SMT Text Files/" + "Loco No. " + self.locoaddress.text + " DCC No. " + self.dccaddress.text + "-" + decodertype + ".txt" #Linux
                #STRR Laptop - "C:/Users/ipara/Desktop/SMT Text Files/" + "Loco No. " + self.locoaddress.text + " DCC No. " + self.dccaddress.text + "-" + decodertype + ".txt" #Linux
                #self.outfilename = "C:/script/" + "Loco " + self.locoaddress.text + "_""DCC# " + self.dccaddress.text + "_" +decodertype + ".txt" #Windows
                #Creates a file in .jmri in the following manner:  "Loco 1234_DCC# 4321_Digitrax.txt"
                
                print
                print "Transferring Data to a Text File to to a Desktop Folder for future use: ",self.outfilename
                print
                self.ofl = open(self.outfilename, "a")
                self.ofl.write (self.Scale.getSelectedItem() + "\n")    #Records scale used in text file.
                self.ofl.write ("-----\n")                              # New line created.
                self.ofl.write ("-----\n")
                self.ofl.write ("CV3 is set to " + self.cv3.text + "\n")    #Records what CV3 was set to as per input panel.
                self.ofl.write ("CV4 is set to " + self.cv4.text + "\n")    #Records what CV4 was set to as per input panel.
                self.ofl.write ("\n")
                self.ofl.write ("Speed Matching Direction is set to " + self.SetDirection.getSelectedItem()  + "\n")    #Records loco direction used for speed matching.
                self.ofl.write ("\n")
                self.ofl.write ("Max Forward Speed is " + str(int(fwdmaxspeed))+ " MPH" + "\n") #Records max forward speed obtained.
                self.ofl.write ("Max Reverse Speed is " + str(int(revmaxspeed)) + " MPH" + "\n")        #Records max reverse speed obtained.
                self.ofl.write ("-----\n")
                self.ofl.write ("-----\n")
                self.ofl.write ("Speed Table Values" + "\n")        
                
# Write Speed Table to file
                for z in range (67, 95) :
                    x = int(stepvaluelist[z - 66])
                    self.ofl.write ("CV " + str(z) + " --- " + str(x))      #Records Speed Table CV values from CV 67 to CV94.
                    self.ofl.write ("\n")
                self.ofl.write ("\n")
                self.ofl.flush()
                self.ofl.close()
                                
                self.status.text = "Done"
            else :
                self.status.text = "Done - Locomotive has decoder or mechanical problem; cannot create speed table"

        else :
            self.status.text = "Done - Unknown Decoder Cannot Proceed"
    
        
        
        self.throttle.setF8(False)
        self.throttle.setF0(False)
        endtesttime = java.lang.System.currentTimeMillis()
        print
        print "Test Time = ",((endtesttime - starttesttime) / 1000) / 60, " min."       #Displays time it took to complete the speedmatching of locomotive.

# done!

        self.throttle.release(None)
#re-enable button
        self.startButton.enabled = True
# and stop


# cycle track power because some Digitrax decoders don't stop

        jmri.InstanceManager.getDefault(jmri.PowerManager).setPower(jmri.PowerManager.OFF)
        self.waitMsec(2000)
        jmri.InstanceManager.getDefault(jmri.PowerManager).setPower(jmri.PowerManager.ON)
        self.memory25.value = "Done - Ready for next locomotive"

        return 0
#---------------------------------------------------------------
    # define what buttons do when clicked and attach that routine to the button
    def whenMyButtonClicked(self,event) :
        self.start()
        # we leave the button off
        self.startButton.enabled = False

        return
#---------------------------------------------------------------
    # routine to show the user input panel, starting the whole process
    # the panel collects the locomotive address, scale being used, and the decoder type if known
    def setup(self):

        DecoderList = ["Select the BRAND of DCC Decoder you have in your locomotive", "Digitrax", "TCS", "NCE", "Tsunami" , "QSI-BLI", "ESU", "SoundtraxxDSD", "Lenz Gen 5",  "Atlas/Lenz XF", "MRC" ] 
    
        # create a frame to hold the button, set up for nice layout
        f = javax.swing.JFrame("STRR SMT Input Panel Ver4.2 (NC+STRR+Extra+99) 11-2025")      # argument is the frames title
        f.setLocation(765,355)  # This will put the input panel in the bottom right corner of the laptop desktop.
        f.contentPane.setLayout(javax.swing.BoxLayout(f.contentPane, javax.swing.BoxLayout.Y_AXIS))

        # create the DCC text field
        self.dccaddress = javax.swing.JTextField(5) # sized to hold 5 characters, initially empty

        # put the text field on a line preceded by a label
        temppanel1 = javax.swing.JPanel()
        temppanel1.add(javax.swing.JLabel("Enter DCC Address"))
        temppanel1.add(self.dccaddress)

        # create the LOCO text field
        self.locoaddress = javax.swing.JTextField(5)    # sized to hold 5 characters, initially empty

        # put the LOCO text field on a line preceded by a label
        temppanel5 = javax.swing.JPanel()
        temppanel5.add(javax.swing.JLabel("Enter Loco number"))
        temppanel5.add(self.locoaddress)
        
# create the momentum value fields
        self.cv3 = javax.swing.JTextField(3)    # sized to hold 3 characters, initially empty
        self.cv4 = javax.swing.JTextField(3)    # sized to hold 3 characters, initially empty

# put the text field on a line preceded by a label
        temppanel4 = javax.swing.JPanel()
        temppanel4.add(javax.swing.JLabel("  Enter Accel. Momentum CV_3 "))
        temppanel4.add(self.cv3)
        temppanel4.add(javax.swing.JLabel("  Enter Decel. Momentum CV_4 "))
        temppanel4.add(self.cv4)

#SN changed default to 22
        self.cv3.setText("1")       #Prefer to have at least a little Acceleration momentum as a standard.
        self.cv4.setText("1")       #Prefer to have at least a little Deceleration momentum as a standard.
          
# create the start button
        self.startButton = javax.swing.JButton("Start")
        self.startButton.actionPerformed = self.whenMyButtonClicked
 
 #User-entered text boxes or drop down selection boxes.
        self.status = javax.swing.JLabel("Enter Info and then press Start          ")
        
        self.Scale = javax.swing.JComboBox()
        self.Scale.addItem("N Scale")

        self.Locomotive = javax.swing.JComboBox()
        self.Locomotive.addItem("Select DIESEL or STEAM for the type of loco on the track")
        self.Locomotive.addItem("Diesel")
        self.Locomotive.addItem("Steam")

        self.SetDirection = javax.swing.JComboBox()
        self.SetDirection.addItem("Select FORWARD or REVERSE for speed matching direction")
        self.SetDirection.addItem("Forward")
        self.SetDirection.addItem("Reverse")

        self.MaxSpeed = javax.swing.JTextField(3)

        temppanel3 = javax.swing.JPanel()
        temppanel3.add(javax.swing.JLabel("Max N-Scale Speed Desired"))
        temppanel3.add(self.MaxSpeed)
        self.MaxSpeed.setText("99") 

        self.DecoderBrand = javax.swing.JComboBox(DecoderList)
        self.DecoderBrand.addItem("Select the BRAND of DCC Decoder in the loco")
        self.DecoderBrand.addItem(DecoderList)

        self.DecoderSound = javax.swing.JComboBox()
        self.DecoderSound.addItem("Select YES or NO if your loco contains a SOUND DECODER")
        self.DecoderSound.addItem("No")
        self.DecoderSound.addItem("Yes")
        


# Put contents in frame and display
        f.contentPane.add(temppanel5)
        f.contentPane.add(temppanel1)
        temppanel2 = javax.swing.JPanel()
        f.contentPane.add(self.Scale)
        f.contentPane.add(self.Locomotive)
        f.contentPane.add(self.DecoderBrand)
        f.contentPane.add(self.DecoderSound)
        f.contentPane.add(temppanel4)
        f.contentPane.add(self.SetDirection)
        f.contentPane.add(temppanel3)
        temppanel2.add(self.startButton)
        f.contentPane.add(temppanel2)
        f.contentPane.add(self.status)
        f.pack()
        f.setSize(480, 325); 
        f.show()

        return
#---------------------------------------------------------------
# create one of these
a = AutoSpeedTable()

# set the name, as a example of configuring it
a.setName("STRR Automated Speed Table")

# and show the initial panel
a.setup()

    





