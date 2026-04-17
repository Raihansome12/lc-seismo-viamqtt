#!/usr/bin/env python3
"""
Seismic Data Acquisition and Visualization System
Integrates ADS1256 geophone data collection with ObsPy visualization
Author: Seismic Data Analysis System
"""

import time
import csv
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timezone
from threading import Thread, Event
import queue
import os

# ADS1256 imports
from pipyadc import ADS1256
from ADS1256_definitions import *
import waveshare_config

# ObsPy imports
from obspy import Stream, Trace, UTCDateTime
from obspy.core.trace import Stats
import matplotlib.dates as mdates

class SeismicDataAcquisition:
    """Real-time seismic data acquisition using ADS1256"""
    
    def __init__(self, sample_rate=50, gain=GAIN_1, channel=POS_AIN0 | NEG_AIN1):
        self.sample_rate = sample_rate
        self.gain = gain
        self.channel = channel
        self.data_queue = queue.Queue()
        self.stop_event = Event()
        self.ads = None
        
    def setup_adc(self):
        """Configure the ADS1256 with specified parameters"""
        try:
            self.ads = ADS1256(waveshare_config)
            self.ads.drate = DRATE_50  # Set 50 SPS
            self.ads.pga_gain = 1  # Set gain to 1
            self.ads.mux = self.channel  # Set the channel
            self.ads.sync()  # Sync to start new conversion cycle
            print("ADS1256 initialized successfully")
            return True
        except Exception as e:
            print(f"Error initializing ADS1256: {e}")
            return False
    
    def collect_data_thread(self, duration=60):
        """Data collection thread function"""
        start_time = time.time()
        sample_count = 0
        
        print(f"Starting data acquisition for {duration} seconds...")
        
        while not self.stop_event.is_set() and (time.time() - start_time) < duration:
            try:
                raw_value = self.ads.read_async()
                voltage = raw_value * self.ads.v_per_digit
                timestamp = time.time()
                
                # Put data in queue for visualization
                self.data_queue.put((timestamp, raw_value, voltage))
                sample_count += 1
                
                # Calculate expected sleep time to maintain sample rate
                expected_time = start_time + (sample_count / self.sample_rate)
                sleep_time = expected_time - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                print(f"Error in data collection: {e}")
                break
        
        print(f"Data collection completed. Total samples: {sample_count}")
    
    def start_acquisition(self, duration=60):
        """Start data acquisition in a separate thread"""
        if not self.setup_adc():
            return False
            
        self.stop_event.clear()
        self.acquisition_thread = Thread(target=self.collect_data_thread, args=(duration,))
        self.acquisition_thread.start()
        return True
    
    def stop_acquisition(self):
        """Stop data acquisition"""
        self.stop_event.set()
        if hasattr(self, 'acquisition_thread'):
            self.acquisition_thread.join()
        if self.ads:
            self.ads.stop()

class SeismicVisualization:
    """Real-time seismic data visualization using ObsPy"""
    
    def __init__(self, station_code="RPI01", network_code="XX", location_code="00", channel_code="HHZ"):
        self.station_code = station_code
        self.network_code = network_code
        self.location_code = location_code
        self.channel_code = channel_code
        
        # Initialize plotting
        plt.ion()  # Interactive mode
        self.fig, self.axes = plt.subplots(2, 1, figsize=(12, 8))
        self.fig.suptitle('Real-time Seismic Data Visualization', fontsize=14)
        
        # Setup axes
        self.axes[0].set_title('Raw Voltage Data (Real-time)')
        self.axes[0].set_ylabel('Voltage (V)')
        self.axes[0].grid(True, alpha=0.3)
        
        self.axes[1].set_title('ObsPy Trace Visualization')
        self.axes[1].set_ylabel('Amplitude')
        self.axes[1].set_xlabel('Time')
        self.axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Data storage
        self.timestamps = []
        self.voltages = []
        self.raw_values = []
        self.max_points = 1000  # Maximum points to display
        
    def create_obspy_trace(self, timestamps, voltages, sample_rate=50):
        """Create ObsPy Trace from collected data"""
        if len(voltages) == 0:
            return None
            
        # Create trace statistics
        stats = Stats()
        stats.network = self.network_code
        stats.station = self.station_code
        stats.location = self.location_code
        stats.channel = self.channel_code
        stats.npts = len(voltages)
        stats.sampling_rate = sample_rate
        stats.starttime = UTCDateTime(timestamps[0])
        
        # Create trace
        trace = Trace(data=np.array(voltages), header=stats)
        return trace
    
    def update_plot(self, data_queue):
        """Update plots with new data"""
        # Get all available data from queue
        new_data = []
        try:
            while True:
                new_data.append(data_queue.get_nowait())
        except queue.Empty:
            pass
        
        if not new_data:
            return
        
        # Add new data to storage
        for timestamp, raw_value, voltage in new_data:
            self.timestamps.append(timestamp)
            self.voltages.append(voltage)
            self.raw_values.append(raw_value)
        
        # Limit data points for performance
        if len(self.timestamps) > self.max_points:
            self.timestamps = self.timestamps[-self.max_points:]
            self.voltages = self.voltages[-self.max_points:]
            self.raw_values = self.raw_values[-self.max_points:]
        
        # Update raw data plot
        self.axes[0].clear()
        self.axes[0].plot(self.timestamps, self.voltages, 'b-', linewidth=0.5)
        self.axes[0].set_title(f'Raw Voltage Data - {len(self.timestamps)} samples')
        self.axes[0].set_ylabel('Voltage (V)')
        self.axes[0].grid(True, alpha=0.3)
        
        # Format x-axis for better readability
        if len(self.timestamps) > 1:
            time_range = self.timestamps[-1] - self.timestamps[0]
            if time_range > 0:
                self.axes[0].set_xlim(self.timestamps[0], self.timestamps[-1])
        
        # Create and plot ObsPy trace
        if len(self.voltages) > 10:  # Need minimum data points
            trace = self.create_obspy_trace(self.timestamps, self.voltages)
            if trace:
                # Plot using ObsPy-style visualization
                self.axes[1].clear()
                
                # Create time array for plotting
                time_array = trace.times(type='timestamp')
                
                self.axes[1].plot(time_array, trace.data, 'r-', linewidth=0.8)
                self.axes[1].set_title(f'ObsPy Trace: {trace.id} | SR: {trace.stats.sampling_rate} Hz')
                self.axes[1].set_ylabel('Amplitude')
                self.axes[1].set_xlabel('Time (UTC)')
                self.axes[1].grid(True, alpha=0.3)
                
                # Format time axis
                if len(time_array) > 1:
                    self.axes[1].set_xlim(time_array[0], time_array[-1])
        
        plt.tight_layout()
        plt.pause(0.01)  # Small pause for plot update
    
    def save_obspy_trace(self, filename="seismic_trace.mseed"):
        """Save current data as ObsPy trace in MiniSEED format"""
        if len(self.voltages) > 0:
            trace = self.create_obspy_trace(self.timestamps, self.voltages)
            if trace:
                # Create stream and save
                stream = Stream(traces=[trace])
                stream.write(filename, format='MSEED')
                print(f"Trace saved as {filename}")
                
                # Print trace information
                print("\nTrace Information:")
                print(f"Network: {trace.stats.network}")
                print(f"Station: {trace.stats.station}")
                print(f"Channel: {trace.stats.channel}")
                print(f"Start time: {trace.stats.starttime}")
                print(f"End time: {trace.stats.endtime}")
                print(f"Sampling rate: {trace.stats.sampling_rate} Hz")
                print(f"Number of samples: {trace.stats.npts}")
                print(f"Duration: {trace.stats.endtime - trace.stats.starttime} seconds")
                
                return stream
        return None

def main():
    """Main function to run the seismic data acquisition and visualization"""
    
    print("Seismic Data Acquisition and Visualization System")
    print("=" * 50)
    
    # Initialize components
    acquisition = SeismicDataAcquisition(sample_rate=50)
    visualization = SeismicVisualization()
    
    # Configuration
    duration = 30  # seconds
    
    try:
        # Start data acquisition
        if not acquisition.start_acquisition(duration):
            print("Failed to start data acquisition")
            return
        
        print(f"Data acquisition started. Visualizing for {duration} seconds...")
        print("Close the plot window to stop early.")
        
        # Real-time visualization loop
        start_time = time.time()
        while (time.time() - start_time) < duration:
            try:
                visualization.update_plot(acquisition.data_queue)
                
                # Check if plot window is still open
                if not plt.get_fignums():
                    print("Plot window closed. Stopping acquisition...")
                    break
                    
                time.sleep(0.1)  # Update rate
                
            except KeyboardInterrupt:
                print("\nKeyboard interrupt received. Stopping...")
                break
        
        # Stop acquisition
        acquisition.stop_acquisition()
        
        # Save final trace
        print("\nSaving final trace...")
        stream = visualization.save_obspy_trace("raspberry_pi_seismic.mseed")
        
        if stream:
            print("\nFinal trace statistics:")
            print(stream[0].stats)
            
            # Create a final summary plot
            plt.figure(figsize=(12, 6))
            stream.plot(fig=plt.gcf())
            plt.suptitle('Final Seismic Trace - ObsPy Visualization')
            plt.tight_layout()
            plt.savefig('final_seismic_trace.png', dpi=300, bbox_inches='tight')
            print("Final plot saved as 'final_seismic_trace.png'")
        
        print("\nVisualization completed!")
        plt.show(block=True)  # Keep final plot open
        
    except Exception as e:
        print(f"Error in main execution: {e}")
        acquisition.stop_acquisition()
    
    finally:
        plt.ioff()

if __name__ == "__main__":
    main()