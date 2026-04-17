#!/usr/bin/env python3
"""
SeedLink Data Analysis and Format Conversion Tool
Analyzes saved seismic data and prepares it for SeedLink protocol
Compatible with SeisComp integration
"""

import numpy as np
import matplotlib.pyplot as plt
from obspy import read, Stream, Trace, UTCDateTime
from obspy.core.trace import Stats
from obspy.signal import filter
from obspy.signal.trigger import classic_sta_lta, trigger_onset
import os
from datetime import datetime, timedelta

class SeedLinkAnalyzer:
    """Analyze and convert seismic data for SeedLink compatibility"""
    
    def __init__(self):
        self.stream = None
        self.station_config = {
            'network': 'XX',
            'station': 'RPI01',
            'location': '00',
            'channel': 'HHZ',
            'sample_rate': 50.0,
            'gain': 1.0
        }
    
    def load_data(self, filename):
        """Load seismic data from MiniSEED file"""
        try:
            self.stream = read(filename)
            print(f"Loaded data from {filename}")
            print(f"Stream contains {len(self.stream)} trace(s)")
            
            for i, trace in enumerate(self.stream):
                print(f"Trace {i}: {trace.id}")
                print(f"  Start: {trace.stats.starttime}")
                print(f"  End: {trace.stats.endtime}")
                print(f"  Samples: {trace.stats.npts}")
                print(f"  Sample Rate: {trace.stats.sampling_rate} Hz")
            
            return True
        except Exception as e:
            print(f"Error loading data: {e}")
            return False
    
    def apply_preprocessing(self, trace_index=0):
        """Apply basic preprocessing suitable for SeedLink data"""
        if not self.stream:
            print("No data loaded")
            return False
        
        trace = self.stream[trace_index].copy()
        original_trace = self.stream[trace_index].copy()
        
        print("Applying preprocessing...")
        
        # Remove mean (detrend)
        trace.detrend('demean')
        print("- Mean removed")
        
        # Apply bandpass filter (typical for earthquake detection)
        try:
            trace.filter('bandpass', freqmin=1.0, freqmax=20.0, corners=4, zerophase=True)
            print("- Bandpass filter applied (1-20 Hz)")
        except Exception as e:
            print(f"- Filter error: {e}")
        
        # Plot comparison
        fig, axes = plt.subplots(3, 1, figsize=(12, 10))
        
        # Original data
        t_orig = original_trace.times()
        axes[0].plot(t_orig, original_trace.data, 'b-', linewidth=0.5)
        axes[0].set_title('Original Data')
        axes[0].set_ylabel('Amplitude')
        axes[0].grid(True, alpha=0.3)
        
        # Processed data
        t_proc = trace.times()
        axes[1].plot(t_proc, trace.data, 'r-', linewidth=0.5)
        axes[1].set_title('Processed Data (Detrended + Filtered)')
        axes[1].set_ylabel('Amplitude')
        axes[1].grid(True, alpha=0.3)
        
        # Frequency spectrum
        from scipy import signal
        f, Pxx = signal.welch(trace.data, trace.stats.sampling_rate, nperseg=1024)
        axes[2].semilogy(f, Pxx)
        axes[2].set_title('Power Spectral Density')
        axes[2].set_xlabel('Frequency (Hz)')
        axes[2].set_ylabel('PSD (V²/Hz)')
        axes[2].grid(True, alpha=0.3)
        axes[2].set_xlim(0, 25)
        
        plt.tight_layout()
        plt.savefig('preprocessing_analysis.png', dpi=300, bbox_inches='tight')
        print("Preprocessing analysis saved as 'preprocessing_analysis.png'")
        
        # Update stream with processed data
        self.stream[trace_index] = trace
        
        return True
    
    def detect_events(self, trace_index=0, sta_len=1.0, lta_len=10.0, thr_on=3.0, thr_off=1.0):
        """Detect seismic events using STA/LTA algorithm"""
        if not self.stream:
            print("No data loaded")
            return []
        
        trace = self.stream[trace_index]
        
        print(f"Running STA/LTA event detection...")
        print(f"STA length: {sta_len}s, LTA length: {lta_len}s")
        print(f"Trigger on: {thr_on}, Trigger off: {thr_off}")
        
        # Calculate STA/LTA
        cft = classic_sta_lta(trace.data, int(sta_len * trace.stats.sampling_rate),
                             int(lta_len * trace.stats.sampling_rate))
        
        # Detect trigger points
        on_off = trigger_onset(cft, thr_on, thr_off)
        
        print(f"Detected {len(on_off)} potential events")
        
        # Plot results
        fig, axes = plt.subplots(2, 1, figsize=(12, 8))
        
        # Original trace
        t = trace.times()
        axes[0].plot(t, trace.data, 'k-', linewidth=0.5)
        axes[0].set_title(f'Seismic Data with Event Detections: {trace.id}')
        axes[0].set_ylabel('Amplitude')
        
        # Mark detected events
        for i, (on, off) in enumerate(on_off):
            on_time = on / trace.stats.sampling_rate
            off_time = off / trace.stats.sampling_rate
            axes[0].axvline(on_time, color='red', linestyle='--', alpha=0.7, label='Event Start' if i == 0 else "")
            axes[0].axvline(off_time, color='blue', linestyle='--', alpha=0.7, label='Event End' if i == 0 else "")
            
            # Add event annotation
            axes[0].annotate(f'Event {i+1}', 
                           xy=(on_time, np.max(trace.data) * 0.8),
                           xytext=(on_time, np.max(trace.data) * 0.9),
                           ha='center', fontsize=8,
                           bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7))
        
        if len(on_off) > 0:
            axes[0].legend()
        axes[0].grid(True, alpha=0.3)
        
        # STA/LTA function
        axes[1].plot(t, cft, 'g-', linewidth=0.7)
        axes[1].axhline(thr_on, color='red', linestyle=':', label=f'Trigger On ({thr_on})')
        axes[1].axhline(thr_off, color='blue', linestyle=':', label=f'Trigger Off ({thr_off})')
        axes[1].set_title('STA/LTA Characteristic Function')
        axes[1].set_xlabel('Time (s)')
        axes[1].set_ylabel('STA/LTA Ratio')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('event_detection.png', dpi=300, bbox_inches='tight')
        print("Event detection plot saved as 'event_detection.png'")
        
        # Create event summary
        events = []
        for i, (on, off) in enumerate(on_off):
            event_start = trace.stats.starttime + (on / trace.stats.sampling_rate)
            event_end = trace.stats.starttime + (off / trace.stats.sampling_rate)
            duration = (off - on) / trace.stats.sampling_rate
            
            events.append({
                'event_id': i + 1,
                'start_time': event_start,
                'end_time': event_end,
                'duration': duration,
                'max_amplitude': np.max(np.abs(trace.data[on:off]))
            })
            
            print(f"Event {i+1}: {event_start} | Duration: {duration:.2f}s | Max Amp: {events[i]['max_amplitude']:.6f}")
        
        return events
    
    def create_seedlink_format(self, output_dir="seedlink_data"):
        """Create data structure similar to SeedLink format"""
        if not self.stream:
            print("No data loaded")
            return False
        
        os.makedirs(output_dir, exist_ok=True)
        
        for i, trace in enumerate(self.stream):
            # Create filename following SeedLink conventions
            start_time = trace.stats.starttime
            filename = f"{trace.stats.network}.{trace.stats.station}.{trace.stats.location}.{trace.stats.channel}.D.{start_time.year}.{start_time.julday:03d}"
            
            filepath = os.path.join(output_dir, f"{filename}.mseed")
            
            # Save as MiniSEED (SeedLink standard format)
            trace.write(filepath, format='MSEED')
            print(f"Saved: {filepath}")
            
            # Create metadata file (similar to what SeisComp would use)
            metadata_file = os.path.join(output_dir, f"{filename}.meta")
            with open(metadata_file, 'w') as f:
                f.write(f"# SeedLink-compatible metadata\n")
                f.write(f"Network: {trace.stats.network}\n")
                f.write(f"Station: {trace.stats.station}\n")
                f.write(f"Location: {trace.stats.location}\n")
                f.write(f"Channel: {trace.stats.channel}\n")
                f.write(f"Start Time: {trace.stats.starttime}\n")
                f.write(f"End Time: {trace.stats.endtime}\n")
                f.write(f"Sample Rate: {trace.stats.sampling_rate}\n")
                f.write(f"Samples: {trace.stats.npts}\n")
                f.write(f"Duration: {trace.stats.endtime - trace.stats.starttime}\n")
                f.write(f"Data Quality: D\n")  # D = Raw data
                f.write(f"Instrument: Geophone + ADS1256\n")
                f.write(f"Location: Raspberry Pi Station\n")
            
            print(f"Metadata saved: {metadata_file}")
        
        # Create station configuration for SeisComp
        station_config_file = os.path.join(output_dir, "station_config.xml")
        self._create_station_xml(station_config_file)
        
        return True
    
    def _create_station_xml(self, filename):
        """Create station configuration XML for SeisComp"""
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<FDSNStationXML xmlns="http://www.fdsn.org/xml/station/1" schemaVersion="1.0">
  <Source>Raspberry Pi Seismic Station</Source>
  <Created>{datetime.utcnow().isoformat()}Z</Created>
  <Network code="{self.station_config['network']}" startDate="2025-01-01T00:00:00Z">
    <Description>Raspberry Pi Seismic Network</Description>
    <Station code="{self.station_config['station']}" startDate="2025-01-01T00:00:00Z">
      <Description>Raspberry Pi Seismic Station</Description>
      <Latitude>-6.2088</Latitude>  <!-- Example coordinates for Jakarta -->
      <Longitude>106.8456</Longitude>
      <Elevation>8.0</Elevation>
      <Site>
        <Name>Test Site</Name>
        <Description>Raspberry Pi Test Installation</Description>
      </Site>
      <Channel code="{self.station_config['channel']}" locationCode="{self.station_config['location']}" startDate="2025-01-01T00:00:00Z">
        <Latitude>-6.2088</Latitude>
        <Longitude>106.8456</Longitude>
        <Elevation>8.0</Elevation>
        <Depth>0.0</Depth>
        <Azimuth>0.0</Azimuth>
        <Dip>-90.0</Dip>
        <SampleRate>{self.station_config['sample_rate']}</SampleRate>
        <ClockDrift>0.0</ClockDrift>
        <Sensor>
          <Description>Geophone with ADS1256 ADC</Description>
        </Sensor>
        <DataLogger>
          <Description>Raspberry Pi 3 Model B+ with ADS1256</Description>
        </DataLogger>
        <Response>
          <InstrumentSensitivity>
            <Value>{self.station_config['gain']}</Value>
            <Frequency>1.0</Frequency>
            <InputUnits>
              <Name>m/s</Name>
              <Description>Velocity in Meters per Second</Description>
            </InputUnits>
            <OutputUnits>
              <Name>V</Name>
              <Description>Volts</Description>
            </OutputUnits>
          </InstrumentSensitivity>
        </Response>
      </Channel>
    </Station>
  </Network>
</FDSNStationXML>"""
        
        with open(filename, 'w') as f:
            f.write(xml_content)
        
        print(f"Station XML configuration saved: {filename}")
    
    def generate_report(self, events=None):
        """Generate comprehensive analysis report"""
        if not self.stream:
            print("No data loaded")
            return
        
        report_file = "seismic_analysis_report.txt"
        
        with open(report_file, 'w') as f:
            f.write("SEISMIC DATA ANALYSIS REPORT\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Data summary
            f.write("DATA SUMMARY:\n")
            f.write("-" * 20 + "\n")
            for i, trace in enumerate(self.stream):
                f.write(f"Trace {i}: {trace.id}\n")
                f.write(f"  Duration: {trace.stats.endtime - trace.stats.starttime} seconds\n")
                f.write(f"  Samples: {trace.stats.npts}\n")
                f.write(f"  Sample Rate: {trace.stats.sampling_rate} Hz\n")
                f.write(f"  Min/Max Amplitude: {np.min(trace.data):.6f} / {np.max(trace.data):.6f}\n")
                f.write(f"  RMS: {np.sqrt(np.mean(trace.data**2)):.6f}\n\n")
            
            # Event summary
            if events:
                f.write("EVENT DETECTION SUMMARY:\n")
                f.write("-" * 30 + "\n")
                f.write(f"Total Events Detected: {len(events)}\n\n")
                
                for event in events:
                    f.write(f"Event {event['event_id']}:\n")
                    f.write(f"  Start Time: {event['start_time']}\n")
                    f.write(f"  Duration: {event['duration']:.2f} seconds\n")
                    f.write(f"  Max Amplitude: {event['max_amplitude']:.6f}\n\n")
            
            # SeedLink compatibility notes
            f.write("SEEDLINK COMPATIBILITY:\n")
            f.write("-" * 25 + "\n")
            f.write("- Data format: MiniSEED (compatible)\n")
            f.write("- Station naming: Standard FDSN convention\n")
            f.write("- Sample rate: 50 Hz (good for regional seismology)\n")
            f.write("- Time stamps: UTC (required for SeedLink)\n")
            f.write("- Data quality: Raw (D) - suitable for real-time processing\n\n")
            
            f.write("NEXT STEPS FOR SEEDLINK INTEGRATION:\n")
            f.write("-" * 40 + "\n")
            f.write("1. Install SeisComp3/4 on your system\n")
            f.write("2. Configure seedlink plugin for your data source\n")
            f.write("3. Set up real-time data streaming\n")
            f.write("4. Configure automatic processing modules\n")
            f.write("5. Set up event detection and notification\n")
        
        print(f"Analysis report saved: {report_file}")

def main():
    """Main analysis function"""
    print("SeedLink Data Analysis Tool")
    print("=" * 30)
    
    analyzer = SeedLinkAnalyzer()
    
    # Check if data file exists
    data_file = "raspberry_pi_seismic.mseed"
    if not os.path.exists(data_file):
        print(f"Data file {data_file} not found.")
        print("Please run the main acquisition script first.")
        return
    
    # Load and analyze data
    if analyzer.load_data(data_file):
        print("\nApplying preprocessing...")
        analyzer.apply_preprocessing()
        
        print("\nDetecting events...")
        events = analyzer.detect_events()
        
        print("\nCreating SeedLink-compatible format...")
        analyzer.create_seedlink_format()
        
        print("\nGenerating report...")
        analyzer.generate_report(events)
        
        print("\nAnalysis complete!")
        print("Check the generated files:")
        print("- preprocessing_analysis.png")
        print("- event_detection.png") 
        print("- seedlink_data/ directory")
        print("- seismic_analysis_report.txt")
        
        # Show final plot
        plt.show()

if __name__ == "__main__":
    main()