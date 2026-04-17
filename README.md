# Low-Cost Seismometer with Real-Time Monitoring System

## Overview

This project presents the design and implementation of a **low-cost seismic monitoring system** capable of capturing ground motion and displaying data in real time via a web interface.

The system integrates **hardware (sensor + electronics)** and **software (data processing + web visualization)** into a complete end-to-end solution.

---

## Key Features

* Real-time seismic data acquisition
* Live data visualization via web dashboard
* Custom-built hardware system
* Frequency response analysis & calibration
* End-to-end pipeline (sensor → processing → web)

---

## System Architecture

### Hardware Components

* Geophone (ground motion sensor)
* Signal Conditioning Circuit (amplification & filtering)
* ADC (Analog-to-Digital Converter)
* Raspberry Pi 3 B+ (data acquisition & processing)

### Software Components

* Data acquisition script (Python)
* Real-time data streaming
* Web-based monitoring dashboard (in diff repo*)

---

## Hardware Implementation

* Designed and assembled **custom PCB**
* Integrated geophone with signal conditioning circuit
* Built **mechanical enclosure** for system stability
* Connected ADC to Raspberry Pi for digital processing

---

## Data Processing & Analysis

* Converted analog signals into digital data
* Processed seismic signals in real time
* Performed **frequency response analysis** to evaluate sensor performance
* Validated system using a **seismic simulator**

---

## Key Learnings

* Integration of **hardware and software systems**
* Real-time data processing challenges
* Signal conditioning and noise handling
* Building full-stack engineering solutions

---

## Limitations

* Sensitivity limited by low-cost components
* Environmental noise may affect readings
* Requires calibration for different conditions

---

## Future Improvements

* Improve signal filtering and noise reduction
* Use higher precision ADC
* Deploy system to cloud for remote monitoring
* Integrate alert system for seismic events

---

## 📎 Author

**Raihan Ahmad**

---

## 🔗 Repository Link

https://github.com/Raihansome12/seismic-monitoring
