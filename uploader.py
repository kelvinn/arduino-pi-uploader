import serial
import os
import sys
import logging
import time
import xively
from datetime import datetime, timedelta
from collections import deque
import math

# Setup Syslog for logging
LOG_FILENAME = 'arduino-pi-uploader.log'
logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG)


if os.getenv('KEY_ID') and os.getenv('FEED_ID'):
    KEY_ID = str(os.getenv('KEY_ID'))
    FEED_ID = str(os.getenv('FEED_ID'))
    api = xively.XivelyAPIClient(KEY_ID)
    feed = api.feeds.get(FEED_ID)
else:
    msg = "You need to set the KEY_ID and FEED_ID environment variables."
    print msg
    logging.info(msg)
    api = None
    feed = None

def lookupid(x):
    return {
        'concentration': "0",
        'ratio': "1",
        'humidity': "2",
        'temperature': "3",
        'light': "4",
        'airquality': "5",
        'no2': "7", #6 is used for VPD
        'co': "8",
    }[x]

ser = serial.Serial("/dev/ttyUSB0", 9600, timeout=10)
data = {'concentration':deque(),'ratio':deque(),'humidity':deque(),'temperature':deque(),
        'light':deque(),'airquality':deque(),'no2':deque(),'co':deque()}

logging.info("Beginning sensor collection")
last_update = datetime.now()

def vpd_calc(T, RH):
    e_st = 0.61365*math.exp(17.502*T/(240.97+T))
    vpd = (e_st - (RH / 100.0) * e_st) * 1000
    return vpd

def send(cosm_id, sensor_type, value):
    print last_update, "ID: ", cosm_id, "Value: ", value
    if feed and api:
        datastream = feed.datastreams.get(cosm_id)
        datastream.current_value = value
        datastream.update(fields=['current_value'])

while True:
    try:
        line = ser.readline()
        line_list = line.split(",")
        val = 0.0
    except serial.SerialException:
        logging.info("Unable to read from serial port")

    if datetime.now() > last_update + timedelta(minutes = 5) or ser.isOpen() == False:
        logging.info("Frozen for unknown reason")
        ser.setDTR(0)
        time.sleep(0.1)
        ser.setDTR(1)
        ser.close()
        time.sleep(5)
        ser = serial.Serial("/dev/ttyUSB0", 9600, timeout=10)
        last_update = datetime.now()

    try:
        if len(line_list) == 2:
            sensor_type = line_list[0]
            sensor_reading = line_list[1].strip()

            if len(data[sensor_type]) > 5:
                data[sensor_type].popleft()
            fl_trunk = "%.2f" % float(sensor_reading)
            data[sensor_type].append(float(fl_trunk))

            if datetime.now() > last_update + timedelta(minutes = 1):
                print "Sending to cosm"
                last_update = datetime.now()

                if len(data['temperature']) > 0:
                    t_avg = sum(data['temperature'])/len(data['temperature'])
                    rh_avg = sum(data['humidity'])/len(data['humidity'])
                    vpd = vpd_calc(t_avg, rh_avg)

                    if float(vpd) is not 0.0:
                        send('6', 'vpd', int(vpd))

                for sensor_type in data.keys():
                    if len(data[sensor_type]) > 0:
                        val = sum(data[sensor_type])/len(data[sensor_type])
                        if float(val) is not 0.0:
                            cosm_id = lookupid(sensor_type)
                            send(cosm_id, sensor_type, round(val,3))

    except Exception, e:
        print e
        logging.info(e)
