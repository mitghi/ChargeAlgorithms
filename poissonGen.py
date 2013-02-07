import sys
import math
import random
import Queue
from vehicle import *
from chargePorts import *
from operator import attrgetter

if len( sys.argv ) != 2:
    print 'Wrong Number of Arguments you sent', sys.argv
    print 'interval'
    sys.exit()
#print 'parameters: ',sys.argv    

interval = int( sys.argv[ 1 ] )

# ----------- Constants -------------

avgArrivalRate = .5

# chargeRateMu
# chargeRateSigma

# chargeNeeded - the charge needed at the end 
chargeNeededMu = 45 #kwh
chargeNeededSigma = 5 #kwh

currentChargeSigma = 3 #kwh
currentChargeMu = 12 #kwh

uniformMaxCapacity = 60 #kwh
uniformChargeRate = 30 #kw

doneChargingLot = []
failedLot = []
edfQueue = []
queue = Queue.Queue( 0 ) # infinite size
currentTime = 0 


# ------------ Poisson Generator ------------

# the main function for generating an interval on which to run an algorithmn
# will create a 2-level array, the top level being the length of the interval
# level 2 contains an array of the vehicle objects that will arrive during that minute
def simulateInterval():
    arrivalTimes = []
    prevArrival = 0

    while True:
        nextArrival = math.floor( vehicleArrives( prevArrival ) )
        if nextArrival >= interval:
            break
        arrivalTimes.append( nextArrival )
        prevArrival = nextArrival

    arrivalsPerMin = [ 0 ] * interval

    for arrivalTime in arrivalTimes:
        arrivalsPerMin[int(arrivalTime)]+= 1
    
    print "total number of vehicles:  " , len(arrivalTimes)
    
    vehicles = vehicleGen( arrivalsPerMin )
    return vehicles

def vehicleArrives( prevArrival ):
    return prevArrival + random.expovariate( avgArrivalRate )

def vehicleGen( arrayOfArrivalsPerMin ):
    vehicles = []

    for minute, arrivalesDuringMin in enumerate( arrayOfArrivalsPerMin ):
        if arrivalesDuringMin != 0 :
            vehiclesDuringMin = []

            for i in range( 0, arrivalesDuringMin ):
                depart = minute + random.randint( 60, 180 )
                chargeNeeded = random.gauss( chargeNeededMu, chargeNeededSigma )
                currentCharge = random.gauss( currentChargeMu, currentChargeSigma )
                chargeRate = uniformChargeRate
                maxCapacity = uniformMaxCapacity
                vehiclesDuringMin.append( Vehicle( minute, depart, chargeNeeded, currentCharge, chargeRate, maxCapacity ) )
            
            vehicles.append( vehiclesDuringMin )

        else:
            vehicles.append( [] )

    return vehicles

#  ------------- The Algorithms -------------


#  ------ LLF ------

# laxity is defined as freeTime/totalTime where freeTime = (departure - arrival - chargeTime) and totalTime = (departure - arrival) initially )
# laxity needs to be updated each minute where freeTime = ( departure - current time - chargeTime ) and totalTime = ( departure - currentTime )
# 
# for both cases, caluclate totalTime, then free time will just be totalTime - chargeTime.
#
# not sure what the unit for laxity is going to be. I'm guessing we'll want freeTime / totalTime // laxity will constantly be updated each step



#  ------ EDF ------
earliestDLIndex = -1;

# the main function for Earliest Deadline First Algorithm
# takes in an array of vehicle interval arrays
def simulateEDF( arrayOfVehicleArrivals ):
    global currentTime
    global earliestDLIndex

    # iterate through each vehicle in each minute
    for minute, numVehiclesPerMin in enumerate( arrayOfVehicleArrivals ):
        for vehicle in numVehiclesPerMin:
            port = openChargePort()

            if port is not None:
                chargePorts[ port ] = vehicle
            else:
                edfQueue.append( vehicle )
                if earliestDLIndex == -1 or vehicle.depTime < edfQueue[ earliestDLIndex ].depTime:
                    earliestDLIndex = len( edfQueue ) - 1

        updateVehiclesEDF()
        currentTime += 1

    print "status:  " , openChargePort() , "  " , len(edfQueue) == 0

    # vehicles done arriving, now continue with the simulation
    while chargePortsEmpty() == False or not len( edfQueue ) == 0:
        updateVehiclesEDF()
        currentTime += 1

    print ( "status:  " , openChargePort() ,
            "  " , len( edfQueue ) == 0 ,
            " which evaluated to " , 
            not len( edfQueue ) == 0 or openChargePort() is None
            )

    print ( "current time: " , currentTime , 
            "  done charging lot: " , len( doneChargingLot ) ,
            "  failed charing lot: " , len( failedLot ) ,
            "  edfQueue size:  " , len( edfQueue ) ,
            "  chargePort " , chargePorts
        )

# called to update the vehicles for each minute of simulation
def updateVehiclesEDF():
    global earliestDLIndex

    # cheack each chargePort
    for index, vehicle in enumerate( chargePorts ):

        # add one minute of charge
        if vehicle is not None:
            vehicle.currentCharge += (vehicle.chargeRate) / 60

            print "Charge:  " , vehicle.currentCharge , "   " , vehicle.chargeNeeded
            
            #check if done charging
            if vehicle.currentCharge >= vehicle.chargeNeeded:
                doneChargingLot.append( vehicle )
                
                if len(edfQueue) > 0:
                    chargePorts[index] = edfQueue[earliestDLIndex]
                    del edfQueue[earliestDLIndex]  
                    earliestDLIndex = earliestDL()
                else:
                    chargePorts[index] = None
            
            print "Timing:  " , currentTime , "   ",  vehicle.depTime 

            # check if deadline reached
            if currentTime >= vehicle.depTime:
                failedLot.append( vehicle )
                
                if len(edfQueue) > 0:
                    chargePorts[index] = edfQueue[earliestDLIndex]
                    del edfQueue[earliestDLIndex] 
                    earliestDLIndex = earliestDL()
                else:
                    chargePorts[index] = None

            # check if all cars in chargePorts still have best deadlines
            if earliestDLIndex != -1 and vehicle.depTime > edfQueue[ earliestDLIndex ].depTime:

                # swap index of earliestDLIndex with the current vehicle in the loop
                temp = vehicle
                chargePorts[ index ] = edfQueue[ earliestDLIndex ]
                edfQueue[ earliestDLIndex ] = temp

                # earliestDLIndex is unchanged and still correct

# gets the earliest deadline of all the vehicles in edfQueue
def earliestDL():
    if len( edfQueue ) == 0:
        return -1
    return edfQueue.index( min( edfQueue, key = attrgetter( 'depTime' ) ) )


# ------ FCFS ------

# the main implementation of the First Come First Serve algorithm
# takes in an array of arrays of vehicle minutes ( 2-level )
def simulateFCFS( arrayOfVehicleArrivals ):
    global currentTime

    # iterate through each vehicle in each minute
    for minute, numVehiclesPerMin in enumerate( arrayOfVehicleArrivals ):
        for vehicle in numVehiclesPerMin:           
            port = openChargePort()

            if port is not None:
                chargePorts[ port ] = vehicle
            else:
                queue.put( vehicle )

        updateVehiclesFCFS()
        currentTime += 1

    print "status:  " , openChargePort() , "  " , queue.empty()
    
    while chargePortsEmpty() == False or not queue.empty():
        updateVehiclesFCFS()
        currentTime += 1
    
    print ( "status:  " , openChargePort() ,
            "  " , queue.empty() ,
            " which evaluated to " ,
            not queue.empty() or openChargePort() is None
            )

    print ( "current time: " , currentTime ,
            "  done charging lot: " , len( doneChargingLot ) ,
            "  failed charing lot: " , len( failedLot ) ,
            "  queue size:  " , queue.qsize() ,
            " chargePort " , chargePorts
            )

# called to update the vehicles for each minute of simulation
def updateVehiclesFCFS():

    # check each chargePort
    for index, vehicle in enumerate( chargePorts ):        

        # add 1 minute of charge
        if vehicle is not None:
            vehicle.currentCharge += ( vehicle.chargeRate ) / 60

            print "Charge:  " , vehicle.currentCharge , "   " , vehicle.chargeNeeded

            # check if done charging
            if vehicle.currentCharge >= vehicle.chargeNeeded:
                doneChargingLot.append( vehicle )
                if not queue.empty():
                    chargePorts[ index ] = queue.get()   #careful
                else:
                    chargePorts[ index ] = None

            print "Timing:  " , currentTime , "   " ,  vehicle.depTime 

            # check if deadline reached            
            if currentTime >= vehicle.depTime:
                failedLot.append( vehicle )
                if not queue.empty():
                    chargePorts[ index ] = queue.get()
                else:
                    chargePorts[ index ] = None


#  -------- Simulations ------------

# print simulateInterval()

# simulateFCFS( simulateInterval() )

simulateEDF( simulateInterval() )


# -------- GARBAGE -----------

    # arrivalsPerTimestep = [0] * int(math.ceil(interval / timestep))    
    # for arrivalTime in arrivalTimes:
    #     arrivalsPerTimestep[int(math.floor(arrivalTime/timestep))]+=1
    # print 'total arrivals = ',sum(arrivalsPerTimestep)
    #return arrivalsPerTimestep