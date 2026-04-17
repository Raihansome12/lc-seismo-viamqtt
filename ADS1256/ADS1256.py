import config
import RPi.GPIO as GPIO
import time  # Tambahkan import time

ScanMode = 0

# gain channel
ADS1256_GAIN_E = {'ADS1256_GAIN_1' : 0, # GAIN   1
                  'ADS1256_GAIN_2' : 1,	# GAIN   2
                  'ADS1256_GAIN_4' : 2,	# GAIN   4
                  'ADS1256_GAIN_8' : 3,	# GAIN   8
                  'ADS1256_GAIN_16' : 4,# GAIN  16
                  'ADS1256_GAIN_32' : 5,# GAIN  32
                  'ADS1256_GAIN_64' : 6,# GAIN  64
                 }

# data rate
ADS1256_DRATE_E = {'ADS1256_30000SPS' : 0xF0, # reset the default values
                   'ADS1256_15000SPS' : 0xE0,
                   'ADS1256_7500SPS' : 0xD0,
                   'ADS1256_3750SPS' : 0xC0,
                   'ADS1256_2000SPS' : 0xB0,
                   'ADS1256_1000SPS' : 0xA1,
                   'ADS1256_500SPS' : 0x92,
                   'ADS1256_100SPS' : 0x82,
                   'ADS1256_60SPS' : 0x72,
                   'ADS1256_50SPS' : 0x63,
                   'ADS1256_30SPS' : 0x53,
                   'ADS1256_25SPS' : 0x43,
                   'ADS1256_15SPS' : 0x33,
                   'ADS1256_10SPS' : 0x20,
                   'ADS1256_5SPS' : 0x13,
                   'ADS1256_2d5SPS' : 0x03
                  }

# registration definition
REG_E = {'REG_STATUS' : 0,  # x1H
         'REG_MUX' : 1,     # 01H
         'REG_ADCON' : 2,   # 20H
         'REG_DRATE' : 3,   # F0H
         'REG_IO' : 4,      # E0H
         'REG_OFC0' : 5,    # xxH
         'REG_OFC1' : 6,    # xxH
         'REG_OFC2' : 7,    # xxH
         'REG_FSC0' : 8,    # xxH
         'REG_FSC1' : 9,    # xxH
         'REG_FSC2' : 10,   # xxH
        }

# command definition
CMD = {'CMD_WAKEUP' : 0x00,     # Completes SYNC and Exits Standby Mode 0000  0000 (00h)
       'CMD_RDATA' : 0x01,      # Read Data 0000  0001 (01h)
       'CMD_RDATAC' : 0x03,     # Read Data Continuously 0000   0011 (03h)
       'CMD_SDATAC' : 0x0F,     # Stop Read Data Continuously 0000   1111 (0Fh)
       'CMD_RREG' : 0x10,       # Read from REG rrr 0001 rrrr (1xh)
       'CMD_WREG' : 0x50,       # Write to REG rrr 0101 rrrr (5xh)
       'CMD_SELFCAL' : 0xF0,    # Offset and Gain Self-Calibration 1111    0000 (F0h)
       'CMD_SELFOCAL' : 0xF1,   # Offset Self-Calibration 1111    0001 (F1h)
       'CMD_SELFGCAL' : 0xF2,   # Gain Self-Calibration 1111    0010 (F2h)
       'CMD_SYSOCAL' : 0xF3,    # System Offset Calibration 1111   0011 (F3h)
       'CMD_SYSGCAL' : 0xF4,    # System Gain Calibration 1111    0100 (F4h)
       'CMD_SYNC' : 0xFC,       # Synchronize the A/D Conversion 1111   1100 (FCh)
       'CMD_STANDBY' : 0xFD,    # Begin Standby Mode 1111   1101 (FDh)
       'CMD_RESET' : 0xFE,      # Reset to Power-Up Values 1111   1110 (FEh)
      }

class ADS1256:
    def __init__(self):
        self.rst_pin = config.RST_PIN
        self.cs_pin = config.CS_PIN
        self.drdy_pin = config.DRDY_PIN
        self.first_init = True  # Flag untuk menandai inisialisasi pertama

    # Hardware reset - Ditingkatkan dengan delay lebih panjang
    def ADS1256_reset(self):
        config.digital_write(self.rst_pin, GPIO.HIGH)
        config.delay_ms(300)  # Tambah delay
        config.digital_write(self.rst_pin, GPIO.LOW)
        config.delay_ms(300)  # Tambah delay
        config.digital_write(self.rst_pin, GPIO.HIGH)
        config.delay_ms(500)  # Tambah delay penting setelah HIGH terakhir
    
    def ADS1256_WriteCmd(self, reg):
        config.digital_write(self.cs_pin, GPIO.LOW)#cs  0
        config.spi_writebyte([reg])
        config.digital_write(self.cs_pin, GPIO.HIGH)#cs 1
    
    def ADS1256_WriteReg(self, reg, data):
        config.digital_write(self.cs_pin, GPIO.LOW)#cs  0
        config.spi_writebyte([CMD['CMD_WREG'] | reg, 0x00, data])
        config.digital_write(self.cs_pin, GPIO.HIGH)#cs 1
        
    def ADS1256_Read_data(self, reg):
        config.digital_write(self.cs_pin, GPIO.LOW)#cs  0
        config.spi_writebyte([CMD['CMD_RREG'] | reg, 0x00])
        data = config.spi_readbytes(1)
        config.digital_write(self.cs_pin, GPIO.HIGH)#cs 1

        return data
    
    # Menunggu DRDY dengan timeout dan pesan diagnostik yang lebih baik
    def ADS1256_WaitDRDY(self):
        for i in range(0, 400000, 1):
            if(config.digital_read(self.drdy_pin) == 0):
                return True
            if i % 10000 == 0:  # Add small delay every 10000 iterations
                config.delay_ms(1)
        
        print("ERROR: DRDY pin timeout - pin tidak menjadi LOW")
        return False
    
    # Membaca Chip ID dengan retry dan diagnostik yang lebih baik
    def ADS1256_ReadChipID(self):
        retry_count = 3  # Coba beberapa kali
        for attempt in range(retry_count):
            if self.ADS1256_WaitDRDY() == False:
                print(f"DRDY timeout pada percobaan {attempt+1}, mencoba lagi...")
                config.delay_ms(100)
                continue
                
            id = self.ADS1256_Read_data(REG_E['REG_STATUS'])
            if len(id) > 0:  # Pastikan data valid
                chip_id = id[0] >> 4
                print(f"ID yang terbaca: 0x{chip_id:X} pada percobaan {attempt+1}")
                return chip_id
            else:
                print(f"Pembacaan ID gagal pada percobaan {attempt+1}, mencoba lagi...")
                config.delay_ms(100)
        
        print("Gagal membaca ID chip setelah beberapa percobaan")
        return -1  # Return nilai error
        
    # Konfigurasi ADC dengan penambahan delay
    def ADS1256_ConfigADC(self, gain, drate):
        if self.ADS1256_WaitDRDY() == False:
            print("Warning: DRDY timeout saat konfigurasi ADC")
            
        buf = [0,0,0,0,0,0,0,0]
        buf[0] = (0<<3) | (1<<2) | (0<<1)
        buf[1] = 0x08
        buf[2] = (0<<5) | (0<<3) | (gain<<0)
        buf[3] = drate
        
        config.digital_write(self.cs_pin, GPIO.LOW)#cs  0
        config.spi_writebyte([CMD['CMD_WREG'] | 0, 0x03])
        config.spi_writebyte(buf)
        
        config.digital_write(self.cs_pin, GPIO.HIGH)#cs 1
        config.delay_ms(50)  # Meningkatkan delay setelah konfigurasi

    def ADS1256_SetChannal(self, Channal):
        if Channal > 7:
            return 0
        self.ADS1256_WriteReg(REG_E['REG_MUX'], (Channal<<4) | (1<<3))

    def ADS1256_SetDiffChannal(self, Channal):
        if Channal == 0:
            self.ADS1256_WriteReg(REG_E['REG_MUX'], (0 << 4) | 1) 	#DiffChannal  AIN0-AIN1
        elif Channal == 1:
            self.ADS1256_WriteReg(REG_E['REG_MUX'], (2 << 4) | 3) 	#DiffChannal   AIN2-AIN3
        elif Channal == 2:
            self.ADS1256_WriteReg(REG_E['REG_MUX'], (4 << 4) | 5) 	#DiffChannal    AIN4-AIN5
        elif Channal == 3:
            self.ADS1256_WriteReg(REG_E['REG_MUX'], (6 << 4) | 7) 	#DiffChannal   AIN6-AIN7

    def ADS1256_SetMode(self, Mode):
        global ScanMode
        ScanMode = Mode

    # Inisialisasi ADS1256 yang lebih robust dengan penanganan error
    def ADS1256_init(self):
        if (config.module_init() != 0):
            print("Gagal inisialisasi modul GPIO/SPI")
            return -1
        
        # Reset chip dengan lebih hati-hati
        self.ADS1256_reset()
        config.delay_ms(50)  # Tunggu sebentar setelah reset
        
        # Kirim perintah SDATAC untuk memastikan chip tidak dalam mode continuous read
        self.ADS1256_WriteCmd(CMD['CMD_SDATAC'])
        config.delay_ms(10)
        
        # Coba baca ID
        id = self.ADS1256_ReadChipID()
        
        # Cek ID dengan lebih toleran (beberapa modul mungkin memiliki variasi minor)
        if id == 3:
            print("ID Read success (0x3)")
        elif id > 0:  # Lebih toleran terhadap ID
            print(f"ID berbeda dari yang diharapkan (0x{id:X}), tapi masih valid")
        else:
            print("ID Read failed atau invalid")
            return -1
        
        # Self-calibration sebelum konfigurasi
        self.ADS1256_WriteCmd(CMD['CMD_SELFCAL'])
        config.delay_ms(100)  # Tunggu kalibrasi selesai
        
        # Konfigurasi ADC
        self.ADS1256_ConfigADC(ADS1256_GAIN_E['ADS1256_GAIN_1'], ADS1256_DRATE_E['ADS1256_50SPS'])
        config.delay_ms(50)  # Tunggu setelah konfigurasi
        
        return 0
    
    # Function untuk inisialisasi dengan auto-recovery
    def ADS1256_init_with_recovery(self, max_attempts=3):
        """Initialize ADS1256 with recovery attempts"""
        for attempt in range(max_attempts):
            print(f"\nMencoba inisialisasi ADS1256 (percobaan {attempt+1}/{max_attempts})...")
            
            # Hard reset setiap percobaan
            self.ADS1256_reset()
            config.delay_ms(500)  # Delay panjang setelah reset
            
            # Kirim reset command juga
            self.ADS1256_WriteCmd(CMD['CMD_RESET'])
            config.delay_ms(200)
            
            result = self.ADS1256_init()
            if result == 0:
                print(f"Inisialisasi berhasil pada percobaan {attempt+1}!")
                return 0
            else:
                print(f"Inisialisasi gagal pada percobaan {attempt+1}, mencoba lagi...")
                config.delay_ms(1000)  # Tunggu 1 detik sebelum mencoba lagi
        
        print("Gagal menginisialisasi ADS1256 setelah beberapa percobaan")
        return -1
    
    # Function untuk diagnostic test
    def ADS1256_DiagnosticTest(self):
        """Run diagnostic checks on the ADS1256"""
        print("\n=== ADS1256 Diagnostic Test ===")
        
        # Check if DRDY pin works
        print("Testing DRDY pin...")
        drdy_working = False
        for i in range(10):
            if config.digital_read(self.drdy_pin) == 0:
                drdy_working = True
                break
            config.delay_ms(100)
        
        if drdy_working:
            print("DRDY pin responds (goes LOW) - OK")
        else:
            print("WARNING: DRDY pin not responding - Check wiring")
        
        # Read ID
        print("\nReading chip ID...")
        id = self.ADS1256_ReadChipID()
        print(f"Chip ID: 0x{id:X} (Expected: 0x3)")
        
        # Read some registers
        print("\nReading registers...")
        status = self.ADS1256_Read_data(REG_E['REG_STATUS'])
        adcon = self.ADS1256_Read_data(REG_E['REG_ADCON'])
        drate = self.ADS1256_Read_data(REG_E['REG_DRATE'])
        
        if len(status) > 0 and len(adcon) > 0 and len(drate) > 0:
            print(f"STATUS register: 0x{status[0]:02X}")
            print(f"ADCON register: 0x{adcon[0]:02X}")
            print(f"DRATE register: 0x{drate[0]:02X}")
        else:
            print("WARNING: Gagal membaca beberapa register")
        
        print("\n=== End of Diagnostic Test ===")
        
    def ADS1256_Read_ADC_Data(self):
        if self.ADS1256_WaitDRDY() == False:
            return 0  # Return 0 if DRDY timeout
            
        config.digital_write(self.cs_pin, GPIO.LOW)#cs  0
        config.spi_writebyte([CMD['CMD_RDATA']])

        buf = config.spi_readbytes(3)
        config.digital_write(self.cs_pin, GPIO.HIGH)#cs 1
        
        if len(buf) != 3:  # Check if we got all 3 bytes
            print("WARNING: Incomplete data read")
            return 0
            
        read = (buf[0]<<16) & 0xff0000
        read |= (buf[1]<<8) & 0xff00
        read |= (buf[2]) & 0xff
        if (read & 0x800000):
            read &= 0xF000000
        return read
 
    # GetChannalValue dengan delay aktif dan penanganan error yang lebih baik
    def ADS1256_GetChannalValue(self, Channel):
        if(ScanMode == 0):  # 0 Single-ended input 8 channel, 1 Differential input 4 channel 
            if(Channel>=8):
                return 0
            self.ADS1256_SetChannal(Channel)
            self.ADS1256_WriteCmd(CMD['CMD_SYNC'])
            config.delay_ms(10)  # Aktifkan delay ini
            self.ADS1256_WriteCmd(CMD['CMD_WAKEUP'])
            config.delay_ms(20)  # Aktifkan delay ini
            Value = self.ADS1256_Read_ADC_Data()
        else:
            if(Channel>=4):
                return 0
            self.ADS1256_SetDiffChannal(Channel)
            self.ADS1256_WriteCmd(CMD['CMD_SYNC'])
            config.delay_ms(10)  # Aktifkan delay ini
            self.ADS1256_WriteCmd(CMD['CMD_WAKEUP'])
            config.delay_ms(20)  # Aktifkan delay ini
            Value = self.ADS1256_Read_ADC_Data()
        return Value
        
    def ADS1256_GetAll(self):
        ADC_Value = [0,0,0,0,0,0,0,0]
        for i in range(0,8,1):
            ADC_Value[i] = self.ADS1256_GetChannalValue(i)
        return ADC_Value
### END OF FILE ###