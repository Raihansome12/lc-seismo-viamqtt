from obspy import Inventory
from obspy.core.inventory import Network, Station, Channel, Site, Comment, Equipment
from obspy.core.inventory.util import Azimuth, ClockDrift, Distance
from obspy.core.inventory.response import Response, InstrumentSensitivity
from obspy.core.inventory.response import PolesZerosResponseStage, CoefficientsTypeResponseStage
from obspy.core.inventory.response import FIRResponseStage
import numpy as np
import os
from datetime import datetime, timedelta
import uuid

def create_inventory(station_code="STMKG", network_code="IA", 
                    channel_code="SHZ", location_code="00", 
                    latitude=-6.2088, longitude=106.8456, elevation=8.0,
                    depth=0.0, sample_rate=50.0,
                    sensor_description="EGL EG-4.5-II Geophone with ADS1256 on Raspberry Pi 3B+",
                    start_date=None,
                    digitizer_params=None):
    """
    Membuat inventory ObsPy untuk seismometer yang dibuat sendiri dengan ADS1256 dan Raspberry Pi
    Args:
        station_code: Kode stasiun (default: STMKG)
        network_code: Kode jaringan (default: IA)
        channel_code: Kode channel (default: SHZ)
        location_code: Kode lokasi (default: "00")
        latitude: Latitude dalam derajat (default: -6.2088 - Jakarta)
        longitude: Longitude dalam derajat (default: 106.8456 - Jakarta)
        elevation: Elevasi dalam meter (default: 8.0)
        depth: Kedalaman sensor dalam meter (default: 0.0)
        sample_rate: Sample rate dalam Hz (default: 50.0)
        sensor_description: Deskripsi sensor 
        start_date: Tanggal mulai dalam format datetime atau string (YYYY-MM-DD HH:MM:SS)
                   Jika None, akan menggunakan waktu saat ini
        digitizer_params: Parameter untuk digitizer ADS1256
        
    Returns:
        Inventory ObsPy
    """
    # Handle start_date
    if start_date is None:
        start_date = datetime.now()
    elif isinstance(start_date, str):
        try:
            start_date = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise ValueError("start_date string must be in format 'YYYY-MM-DD HH:MM:SS'")
    elif not isinstance(start_date, datetime):
        raise TypeError("start_date must be either None, a datetime object, or a string in format 'YYYY-MM-DD HH:MM:SS'")
    
    # Jika digitizer_params tidak ditentukan, gunakan default
    if digitizer_params is None:
        digitizer_params = {
            'adc_range': 5.0,
            'bit_depth': 24,
            'gain': 1,
            'filter_type': 'SINC3',
            'buffer_enabled': True,
            'dither_enabled': False
        }
    
    # Buat network
    net = Network(
        code=network_code,
        stations=[],
        description=f"{network_code} Network - Independent Seismic Station",
        start_date=start_date
    )
    
    # Buat stasiun
    sta = Station(
        code=station_code,
        latitude=latitude,
        longitude=longitude,
        elevation=elevation,
        creation_date=start_date,
        site=Site(name=f"{station_code} Independent Site"),
        channels=[],
        start_date=start_date,
        description="Independent seismic station with custom hardware"
    )
    
    # Buat channel dengan response
    sensor_equipment = Equipment(
        type=sensor_description,
        description=sensor_description,
        resource_id=f"urn:uuid:{str(uuid.uuid4())}"
    )
    
    data_logger_equipment = Equipment(
        type=f"Raspberry Pi 3B+ with ADS1256 ADC (Gain: {digitizer_params['gain']})",
        description=f"Raspberry Pi 3B+ with ADS1256 ADC (Gain: {digitizer_params['gain']})",
        resource_id=f"urn:uuid:{str(uuid.uuid4())}"
    )
    
    cha = Channel(
        code=channel_code,
        location_code=location_code,
        latitude=latitude,
        longitude=longitude,
        elevation=elevation,
        depth=depth,
        azimuth=0.0,
        dip=-90.0,  # -90 untuk arah vertikal ke bawah (SHZ)
        sample_rate=sample_rate,
        start_date=start_date,
        sensor=sensor_equipment,
        data_logger=data_logger_equipment,
        response=create_geophone_ads1256_response(sample_rate, digitizer_params)
    )
    
    # Tambahkan comments pada channel
    comments = [
        Comment("Digitizer: ADS1256 24-bit ADC on Raspberry Pi 3B+"),
        Comment(f"ADC Gain: {digitizer_params['gain']}"),
        Comment(f"Filter Type: {digitizer_params['filter_type']}"),
        Comment(f"Buffer Enabled: {digitizer_params['buffer_enabled']}"),
        Comment(f"Dither Enabled: {digitizer_params['dither_enabled']}")
    ]
    
    cha.comments = comments
    
    # Tambahkan channel ke stasiun
    sta.channels.append(cha)
    
    # Tambahkan stasiun ke network
    net.stations.append(sta)
    
    # Buat inventory
    inv = Inventory(
        networks=[net],
        source=f"Manual via Python - {datetime.now().strftime('%Y-%m-%d')}",
        sender="ObsPy PPSD XML Generator for Independent Station",
        created=datetime.now(),
        module="ObsPy",
        module_uri="https://www.obspy.org"
    )
    
    # Add comments using proper Comment objects
    inv.comments = [
        Comment("Metadata for independent seismic station using EGL EG-4.5-II Geophone with Raspberry Pi and ADS1256")
    ]
    
    return inv

def create_geophone_ads1256_response(sample_rate=50.0, digitizer_params=None):
    """
    Membuat respon untuk geophone EGL EG-4.5-II dan ADS1256 digitizer
    
    Args:
        sample_rate: Sample rate dalam Hz
        digitizer_params: Parameter untuk digitizer ADS1256
        
    Returns:
        Response ObsPy
    """
    response = Response()
    
    # Parameter default digitizer jika tidak ditentukan
    if digitizer_params is None:
        digitizer_params = {
            'adc_range': 5.0,
            'bit_depth': 24,
            'gain': 1,
            'filter_type': 'SINC3',
            'buffer_enabled': True,
            'dither_enabled': False
        }
    
    # Sensitivitas dari datasheet EG-4.5-II
    sensitivity = 28.8  # V/(m/s) - Dari datasheet (28.8 v/m/s ±5%)
    
    # Stage 1: PolesZeros (Sensor Geophone)
    # Parameter dari datasheet EG-4.5-II
    natural_freq = 4.5  # Hz - natural frequency 4.5±10% Hz
    damping = 0.6      # Damping 0.6±5% dari datasheet
    
    # Kalkulasi poles dan zeros berdasarkan parameter geophone
    w0 = 2 * np.pi * natural_freq  # Konversi ke rad/s
    h = damping
    
    # Poles untuk high-pass filter dengan frekuensi natural dan damping
    real_pole = -h * w0
    imag_pole = w0 * np.sqrt(1 - h**2) if h < 1 else 0
    
    stage1 = PolesZerosResponseStage(
        stage_sequence_number=1,
        stage_gain=sensitivity,
        stage_gain_frequency=1.0,
        input_units="M/S",  # meter per detik (kecepatan)
        output_units="V",   # volt
        pz_transfer_function_type="LAPLACE (RADIANS/SECOND)",
        normalization_frequency=1.0,
        zeros=[0j],  # Satu zero pada origin untuk konversi dari displacement ke velocity
        poles=[complex(real_pole, imag_pole), complex(real_pole, -imag_pole)]  # Poles berdasarkan frekuensi natural dan damping
    )
    response.response_stages.append(stage1)
    
    # Stage 2: Preamp/Buffer (Jika ada)
    if digitizer_params['buffer_enabled']:
        # Buffer biasanya memiliki gain sekitar 1 (unity gain)
        buffer_gain = 1.0
        
        stage2 = CoefficientsTypeResponseStage(
            stage_sequence_number=2,
            stage_gain=buffer_gain,
            stage_gain_frequency=1.0,
            input_units="V",     # volt
            output_units="V",    # volt
            cf_transfer_function_type="ANALOG (RADIANS/SECOND)",
            numerator=[1.0],
            denominator=[1.0]
        )
        response.response_stages.append(stage2)
        stage_count = 3
    else:
        stage_count = 2
    
    # Stage 3/4: ADS1256 ADC dengan gain yang dapat dikonfigurasi
    adc_range = digitizer_params['adc_range']  # Volt (peak-to-peak)
    bit_depth = digitizer_params['bit_depth'] # 24-bit untuk ADS1256
    adc_gain = digitizer_params['gain']  # Gain dari ADS1256
    
    # Hitung faktor konversi V ke count dengan mempertimbangkan gain
    input_voltage_range = adc_range / adc_gain
    counts_per_volt = 2**(bit_depth-1) / (input_voltage_range/2)
    
    stage_adc = CoefficientsTypeResponseStage(
        stage_sequence_number=stage_count,
        stage_gain=counts_per_volt * adc_gain,
        stage_gain_frequency=1.0,
        input_units="V",     # volt
        output_units="COUNTS", # digital counts
        cf_transfer_function_type="DIGITAL (Z-TRANSFORM)",
        numerator=[1.0],
        denominator=[1.0]
    )
    response.response_stages.append(stage_adc)
    stage_count += 1
    
    # Stage 4/5: Digital filter ADS1256 (SINC3/SINC4)
    if digitizer_params['filter_type'] in ['SINC3', 'SINC4']:
        # Koefisien filter perkiraan untuk SINC3/SINC4
        if digitizer_params['filter_type'] == 'SINC3':
            filter_gain = 1.0
            filter_coeffs = [0.05, 0.15, 0.30, 0.45, 0.30, 0.15, 0.05]  # Perkiraan sederhana SINC3
        else:  # SINC4
            filter_gain = 1.0
            filter_coeffs = [0.03, 0.08, 0.15, 0.25, 0.33, 0.25, 0.15, 0.08, 0.03]  # Perkiraan sederhana SINC4
        
        stage_filter = FIRResponseStage(
            stage_sequence_number=stage_count,
            stage_gain=filter_gain,
            stage_gain_frequency=1.0,
            input_units="COUNTS",
            output_units="COUNTS",
            symmetry="ODD",
            coefficients=filter_coeffs
        )
        response.response_stages.append(stage_filter)
    
    # Calculate total sensitivity
    total_gain = 1.0
    for stage in response.response_stages:
        total_gain *= stage.stage_gain
    
    # Set the overall response sensitivity
    response.instrument_sensitivity = InstrumentSensitivity(
        value=total_gain,
        frequency=1.0,
        input_units="M/S",
        output_units="COUNTS"
    )
    
    return response

def get_ads1256_info():
    """
    Mendapatkan informasi tentang konfigurasi ADS1256
    
    Returns:
        dictionary dengan informasi ADS1256
    """
    print("\n--- Informasi ADS1256 Digitizer pada Raspberry Pi ---")
    
    # ADC Range
    print("\nPilih range tegangan input ADC:")
    print("1: ±2.5V (default)")
    print("2: ±5.0V")
    print("3: ±10.0V (jika menggunakan penguat eksternal)")
    print("4: Lainnya (masukkan nilai)")
    
    choice = input("Pilihan Anda [1-4]: ").strip() or "1"
    
    if choice == "1":
        adc_range = 5.0  # ±2.5V = 5.0V peak-to-peak
    elif choice == "2":
        adc_range = 10.0  # ±5.0V = 10.0V peak-to-peak
    elif choice == "3":
        adc_range = 20.0  # ±10.0V = 20.0V peak-to-peak
    elif choice == "4":
        try:
            adc_range = float(input("Masukkan range peak-to-peak dalam Volt: ").strip())
        except ValueError:
            print("Nilai tidak valid, menggunakan default 5.0V")
            adc_range = 5.0
    else:
        adc_range = 5.0  # Default
    
    # ADS1256 Gain
    print("\nPilih gain ADS1256:")
    print("1: 1 (default)")
    print("2: 2")
    print("3: 4")
    print("4: 8")
    print("5: 16")
    print("6: 32")
    print("7: 64")
    
    gain_choice = input("Pilihan Anda [1-7]: ").strip() or "1"
    gain_map = {"1": 1, "2": 2, "3": 4, "4": 8, "5": 16, "6": 32, "7": 64}
    gain = gain_map.get(gain_choice, 1)
    
    # Filter type
    print("\nPilih tipe filter digital ADS1256:")
    print("1: SINC3 (default)")
    print("2: SINC4")
    print("3: Tanpa filter")
    
    filter_choice = input("Pilihan Anda [1-3]: ").strip() or "1"
    filter_map = {"1": "SINC3", "2": "SINC4", "3": "NONE"}
    filter_type = filter_map.get(filter_choice, "SINC3")
    
    # Buffer enabled
    buffer_choice = input("\nApakah buffer input ADS1256 diaktifkan? (y/n, default: y): ").strip().lower() or "y"
    buffer_enabled = buffer_choice == "y"
    
    # Dither enabled
    dither_choice = input("\nApakah fitur dither ADS1256 diaktifkan? (y/n, default: n): ").strip().lower() or "n"
    dither_enabled = dither_choice == "y"
    
    return {
        "adc_range": adc_range,
        "bit_depth": 24,  # ADS1256 selalu 24-bit
        "gain": gain,
        "filter_type": filter_type,
        "buffer_enabled": buffer_enabled,
        "dither_enabled": dither_enabled
    }

def save_inventory_to_xml(inventory, output_dir=".", filename=None):
    """
    Menyimpan inventory ke file XML
    
    Args:
        inventory: Inventory ObsPy
        output_dir: Direktori output (default: ".")
        filename: Nama file output (default: None)
        
    Returns:
        Path ke file XML yang disimpan
    """
    os.makedirs(output_dir, exist_ok=True)
    
    if filename is None:
        net_code = inventory.networks[0].code
        sta_code = inventory.networks[0].stations[0].code
        filename = f"{net_code}.{sta_code}.xml"
    
    output_path = os.path.join(output_dir, filename)
    inventory.write(output_path, format="STATIONXML")
    
    return output_path

if __name__ == "__main__":
    # Contoh penggunaan
    print("Program Pembuatan File XML untuk PPSD ObsPy - EG-4.5-II dengan ADS1256 pada Raspberry Pi")
    print("======================================================================================")
    
    # Konfigurasi default
    network_code = "IA"
    station_code = "STMKG"
    channel_code = "SHZ"
    location_code = "00"
    sample_rate = 50.0
    
    # Input lokasi dan parameter stasiun (opsional)
    use_default = input("Gunakan parameter default stasiun (y/n)? ").strip().lower() == 'y'
    
    if not use_default:
        network_code = input(f"Kode jaringan (default: {network_code}): ").strip() or network_code
        station_code = input(f"Kode stasiun (default: {station_code}): ").strip() or station_code
        channel_code = input(f"Kode channel (default: {channel_code}): ").strip() or channel_code
        location_code = input(f"Kode lokasi (default: {location_code}): ").strip() or location_code
        
        lat_input = input("Latitude (derajat, default: -6.2088): ").strip()
        latitude = float(lat_input) if lat_input else -6.2088
        
        lon_input = input("Longitude (derajat, default: 106.8456): ").strip()
        longitude = float(lon_input) if lon_input else 106.8456
        
        elev_input = input("Elevasi (meter, default: 8.0): ").strip()
        elevation = float(elev_input) if elev_input else 8.0
        
        depth_input = input("Kedalaman sensor (meter, default: 0.0): ").strip()
        depth = float(depth_input) if depth_input else 0.0
        
        rate_input = input(f"Sample rate (Hz, default: {sample_rate}): ").strip()
        sample_rate = float(rate_input) if rate_input else sample_rate
        
        # Input start date
        start_date_input = input("Tanggal mulai (format: YYYY-MM-DD HH:MM:SS, kosongkan untuk waktu sekarang): ").strip()
        if start_date_input:
            try:
                start_date = datetime.strptime(start_date_input, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                print("Format tanggal tidak valid. Menggunakan waktu sekarang.")
                start_date = None
        else:
            start_date = None
    else:
        latitude = -6.2088    # Default Jakarta
        longitude = 106.8456  # Default Jakarta
        elevation = 8.0       # Default
        depth = 0.0           # Default
        start_date = None     # Default to current time
    
    # Dapatkan informasi ADS1256 dari pengguna
    digitizer_params = get_ads1256_info()
    
    # Deskripsi sensor lengkap
    sensor_description = f"EGL EG-4.5-II Geophone (4.5Hz, 28.8V/m/s) with ADS1256 on Raspberry Pi 3B+"
    
    # Membuat inventory
    inventory = create_inventory(
        station_code=station_code,
        network_code=network_code,
        channel_code=channel_code,
        location_code=location_code,
        latitude=latitude,
        longitude=longitude,
        elevation=elevation,
        depth=depth,
        sample_rate=sample_rate,
        sensor_description=sensor_description,
        start_date=start_date,
        digitizer_params=digitizer_params
    )
    
    # Menyimpan ke file XML
    output_dir = input("Direktori output (default: .): ").strip() or "."
    filename = f"{network_code}.{station_code}.xml"
    custom_filename = input(f"Nama file output (default: {filename}): ").strip()
    if custom_filename:
        filename = custom_filename
    
    output_path = save_inventory_to_xml(inventory, output_dir, filename)
    
    print(f"\nFile XML telah disimpan di: {output_path}")
    print("\nFile ini dapat digunakan untuk analisis PPSD dengan ObsPy.")
    print("Contoh penggunaan dalam Python:")
    print("----------------------------")
    print(f"from obspy import read_inventory")
    print(f'inventory = read_inventory("{output_path}")')
    print(f'from obspy import read')
    print(f'st = read("your_miniseed_file.mseed")')
    print(f'from obspy.signal import PPSD')
    print(f'ppsd = PPSD(st[0].stats, inventory)')
    print(f'ppsd.add(st)')
    print(f'ppsd.plot()')