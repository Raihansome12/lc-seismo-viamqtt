import time
import ADS1256
import pandas as pd

# Inisialisasi ADS1256
ADC = ADS1256.ADS1256()
ADC.ADS1256_init()

# Data logging
start_time = time.time()
data = []

while (time.time() - start_time) < 300:
    ADC_Value = ADC.ADS1256_GetAll()
    timestamp = round((time.time() - start_time) * 1000, 3)  # Waktu dalam milidetik
    row = [timestamp] + [ADC_Value[i] * 5.0 / 0x7fffff for i in range(5)]
    data.append(row)

    print("Time: %.3f ms, AD0=%.6f, AD1=%.6f, AD2=%.6f, AD3=%.6f, AD4=%.6f" % tuple(row))

# Simpan ke Excel
df = pd.DataFrame(data, columns=["Time (ms)", "AD0", "AD1", "AD2", "AD3", "AD4"])
df.to_excel("ads1256_data.xlsx", index=False)

print("Data logging selesai. File tersimpan sebagai 'ads1256_data.xlsx'")
