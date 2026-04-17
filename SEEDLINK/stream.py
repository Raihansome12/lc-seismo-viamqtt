import numpy as np
from obspy.core import Trace,Stream,UTCDateTime
import Queue
import itertools
from threading import Thread
from ADS1256_definitions import *
import ADS1256_default_config as cfg_2
from pipyadc import ADS1256
import os
import sys
import time
import subprocess
import wiringpi as wp
#import spidev
#spi = spidev.SpiDev()

if not os.path.exists("/dev/spidev0.0"):
    raise IOError("Error: No SPI device. Check settings in /boot/config.txt")


DIFF1, DIFF2, DIFF3 = POS_AIN2|NEG_AIN3, POS_AIN4|NEG_AIN5, POS_AIN6|NEG_AIN7
CH_SEQUENCE = (DIFF1, DIFF2, DIFF3)


#CH_OFFSET = np.array((-10,   0, -85), dtype=np.int)
#GAIN_CAL  = np.array((1.0, 1.0, 1.0), dtype=np.float)


#Queue and threading >> Banyak Data setiap mseed
block_length = 128

queue = Queue.Queue()
adsMee = ADS1256(cfg_2)

adsMee.SPI_FREQUENCY = 1500000
adsMee.cal_self()
adsMee.pga_gain = 1
adsMee.drate = DRATE_500
#FILTER_SIZE = 2



chip_ID = adsMee.chip_ID
print("ADC conected ! ID value are : {}.".format(chip_ID))
    # When the value is not correct, user code should exit here.
if chip_ID != 3:
        print("\nRead incorrect chip ID for ADS1256. Is the hardware connected?")
    # Passing that step because this is an example:
    #    sys.exit(1)


def read_data():
    #for x in range ():
   
    
    while True:
        packet = [0,0,0,0]
        ### STEP 3: Get data:
        
        raw_data = adsMee.read_continue(CH_SEQUENCE)
               
        sample1 = raw_data[0]
        sample2 = raw_data[1]
        sample3 = raw_data[2]
        timenow = UTCDateTime()
        

        #value1 += (sample1 - value1) / smoothing
        
        packet[0] = sample1
        packet[1] = sample2
        packet[2] = sample3
        packet[3] = timenow

        #print sample1,timenow
        queue.put(packet)

mseedEHZ_directory = 'mseed/RAW/EHZ/'
mergedEHZ_directory = 'mseed/loggedFiles/EHZ/'

mseedEHE_directory = 'mseed/RAW/EHE/'
mergedEHE_directory = 'mseed/loggedFiles/EHE/'

mseedEHN_directory = 'mseed/RAW/EHN/'
mergedEHN_directory = 'mseed/loggedFiles/EHN/'


global starttime


def save_data():
    global blockID
    blockID = 0
    while True:
        #if que += 1
        #print(queue.qsize())
        blockID += 1
        
        data1=np.zeros(block_length,dtype=np.int32)
        data2=np.zeros(block_length,dtype=np.int32)
        data3=np.zeros(block_length,dtype=np.int32)
        
        
        packet = queue.get()
        data1[0] = packet[0]
        data2[0] = packet[1]
        data3[0] = packet[2]
        starttime = packet[3]
        
        queue.task_done()
        
        for x in range(1,block_length):
            packet = queue.get()
            data1[x] = packet[0]
            data2[x] = packet[1]
            data3[x] = packet[2]
            queue.task_done()
            
        tag = queue.qsize()
        
        
        stats1 = {'network':'ID','station':'LUCX','location':'00',
                 'channel':'EHZ','npts': block_length,'sampling_rate':200,
                 'mseed':{'dataquality':'D'},'starttime':starttime}
                 
        stats2 = {'network':'ID','station':'LUCX','location':'00',
                 'channel':'EHE','npts': block_length,'sampling_rate':200,
                 'mseed':{'dataquality':'D'},'starttime':starttime}
                 
        stats3 = {'network':'ID','station':'LUCX','location':'00',
                 'channel':'EHN','npts': block_length,'sampling_rate':200,
                 'mseed':{'dataquality':'D'},'starttime':starttime}
                 
        sample1_stream = Stream([Trace(data=data1, header=stats1)])
        
        sample2_stream = Stream([Trace(data=data2, header=stats2)])
        
        sample3_stream = Stream([Trace(data=data3, header=stats3)])
        
        
        #jitter_stream = Stream([Trace(data=jitter)])
            
        #sample_stream.plot()
            #write sample data
        
        #t = time.localtime()
        #current_time = time.strftime("%H:%M:%S", t)    
        
        File1 = mseedEHZ_directory +'EHZ'+ '_'+str(sample1_stream[0].stats.starttime.date)+'_'+str(blockID)+'.mseed'
        temp_file = mseedEHZ_directory+".temp.tmp"
        
        sample1_stream.write(File1,format='MSEED',encoding='INT32',reclen=512)
        
        
        File2 = mseedEHE_directory +'EHE'+ '_'+str(sample2_stream[0].stats.starttime.date)+'_'+str(blockID)+'.mseed'
        temp_file = mseedEHE_directory+".temp.tmp"
        
        sample2_stream.write(File2,format='MSEED',encoding='INT32',reclen=512)
        
        
        File3 = mseedEHN_directory +'EHN'+ '_'+str(sample3_stream[0].stats.starttime.date)+'_'+str(blockID)+'.mseed'
        temp_file = mseedEHN_directory+".temp.tmp"
        
        sample3_stream.write(File3,format='MSEED',encoding='INT32',reclen=512)
        
        
        
        if blockID > 3600:
            tailTime1 = sample1_stream[0].stats.starttime
            tailTime2 = sample2_stream[0].stats.starttime
            tailTime3 = sample3_stream[0].stats.starttime
            
            mergedSeed1=mergedEHZ_directory+str(tailTime1.date)+"_"+str(tailTime1.hour)+".mseed"
            subprocess.call("cat $(ls -tr mseed/EHZ/*.mseed) >> "+mergedSeed1,shell=True)
            subprocess.call("rm -f "+mseedEHZ_directory+"*.mseed",shell=True)
            
            mergedSeed2=mergedEHE_directory+str(tailTime2.date)+"_"+str(tailTime2.hour)+".mseed"
            subprocess.call("cat $(ls -tr mseed/EHE/*.mseed) >> "+mergedSeed2,shell=True)
            subprocess.call("rm -f "+mseedEHE_directory+"*.mseed",shell=True)
            
            
            mergedSeed3=mergedEHN_directory+str(tailTime3.date)+"_"+str(tailTime3.hour)+".mseed"
            subprocess.call("cat $(ls -tr mseed/EHN/*.mseed) >> "+mergedSeed3,shell=True)
            subprocess.call("rm -f "+mseedEHN_directory+"*.mseed",shell=True)
            
            
            blockID = 0

def cleanMseed():
    subprocess.call("rm -f mseed/EHZ/*.mseed && rm -f mseed/EHE/*.mseed && rm -f mseed/EHN/*.mseed",shell=True)
            
cleanMseed()


#clean_adc()

worker_sample = Thread(target=save_data)
worker_sample.start()

read_data()