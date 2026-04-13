import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
import os

# Configuration
DATA_DIR = "gesture_data"
GESTURES = ['up', 'down', 'left', 'right']
FILE_IDS = ['08', '15']  # Picking 2 distinct files
FS = 100  # Sample rate in Hz

def perform_fft(data, fs=100):
    """Computes FFT using the math engine from your original script."""
    data = data - np.mean(data) # Remove DC offset
    n = len(data)
    if n == 0:
        return np.array([]), np.array([])
    X = np.fft.fft(data, n=n)
    freqs = np.fft.fftfreq(n, d=1.0 / fs)
    mags = (2.0 / n) * np.abs(X[:n//2])
    return freqs[:n//2], mags

def plot_time_domain(data_type='Accel'):
    """Generates an 8-graph figure for the Time Domain."""
    fig, axes = plt.subplots(4, 2, figsize=(13, 9))  # Made slightly smaller
    unit = "g" if data_type == 'Accel' else "°/s"
    fig.suptitle(f"{data_type} Analysis: TIME DOMAIN", fontsize=18, fontweight='bold')
    
    for row, gesture in enumerate(GESTURES):
        for col, file_id in enumerate(FILE_IDS):
            ax = axes[row, col]
            filename = os.path.join(DATA_DIR, f"{gesture}_{file_id}.txt")
            
            if not os.path.exists(filename):
                ax.set_title(f"NOT FOUND")
                continue
                
            df = pd.read_csv(filename)
            time = df['Timestamp_ms'] / 1000.0
            
            ax.plot(time, df[f'{data_type}_X'], label='X', color='r')
            ax.plot(time, df[f'{data_type}_Y'], label='Y', color='g')
            ax.plot(time, df[f'{data_type}_Z'], label='Z', color='b')
            
            # --- MATRIX AESTHETICS ---
            # 1. Print File ID ONLY on the top row
            if row == 0:
                ax.set_title(f"FILE {file_id}", fontsize=14, fontweight='bold')
                
            # 2. Print Gesture Name ONLY on the far right edge of the right column
            if col == 1:
                ax.text(1.05, 0.5, gesture.upper(), transform=ax.transAxes,
                        fontsize=16, fontweight='bold', rotation=270, 
                        va='center', ha='left')
                
            ax.set_xlabel("Time (s)")
            
            # Only label the Y-axis on the left column to keep it clean
            if col == 0:
                ax.set_ylabel(f"Magnitude ({unit})")
                
            ax.grid(True, alpha=0.3)
            if row == 0 and col == 0:
                ax.legend(loc='upper right')
                
    # Changed rect to leave 7% empty space on the right for the new text labels
    plt.tight_layout(rect=[0, 0.03, 0.93, 0.95])
    plt.show()

def plot_fft_domain(data_type='Accel'):
    """Generates an 8-graph figure for the Frequency Domain (FFT)."""
    fig, axes = plt.subplots(4, 2, figsize=(13, 9))
    fig.suptitle(f"{data_type} Analysis: FREQUENCY DOMAIN (FFT)", fontsize=18, fontweight='bold')
    
    for row, gesture in enumerate(GESTURES):
        for col, file_id in enumerate(FILE_IDS):
            ax = axes[row, col]
            filename = os.path.join(DATA_DIR, f"{gesture}_{file_id}.txt")
            
            if not os.path.exists(filename):
                continue
                
            df = pd.read_csv(filename)
            f_x, mag_x = perform_fft(df[f'{data_type}_X'].values, FS)
            f_y, mag_y = perform_fft(df[f'{data_type}_Y'].values, FS)
            f_z, mag_z = perform_fft(df[f'{data_type}_Z'].values, FS)
            
            ax.plot(f_x, mag_x, label='X FFT', color='r')
            ax.plot(f_y, mag_y, label='Y FFT', color='g')
            ax.plot(f_z, mag_z, label='Z FFT', color='b')
            
            # --- MATRIX AESTHETICS ---
            if row == 0:
                ax.set_title(f"FILE {file_id}", fontsize=14, fontweight='bold')
                
            if col == 1:
                ax.text(1.05, 0.5, gesture.upper(), transform=ax.transAxes,
                        fontsize=16, fontweight='bold', rotation=270, 
                        va='center', ha='left')
                
            ax.set_xlabel("Frequency (Hz)")
            if col == 0:
                ax.set_ylabel("Magnitude")
                
            ax.grid(True, alpha=0.3)
            if row == 0 and col == 0:
                ax.legend(loc='upper right')
                
    plt.tight_layout(rect=[0, 0.03, 0.93, 0.95])
    plt.show()

def plot_spectrogram_domain(data_type='Accel'):
    """Generates an 8-graph figure for the Spectrograms."""
    fig, axes = plt.subplots(4, 2, figsize=(13, 9))
    fig.suptitle(f"{data_type} Analysis: SPECTROGRAMS (Total Energy)", fontsize=18, fontweight='bold')
    
    for row, gesture in enumerate(GESTURES):
        for col, file_id in enumerate(FILE_IDS):
            ax = axes[row, col]
            filename = os.path.join(DATA_DIR, f"{gesture}_{file_id}.txt")
            
            if not os.path.exists(filename):
                continue
                
            df = pd.read_csv(filename)
            x = df[f'{data_type}_X'].values
            y = df[f'{data_type}_Y'].values
            z = df[f'{data_type}_Z'].values
            
            x_c, y_c, z_c = x - np.mean(x), y - np.mean(y), z - np.mean(z)
            magnitude = np.sqrt(x_c**2 + y_c**2 + z_c**2)
            
            f_spec, t_spec, Sxx = signal.spectrogram(magnitude, fs=FS, nperseg=64, noverlap=48)
            
            pcm = ax.pcolormesh(t_spec, f_spec, 10 * np.log10(Sxx + 1e-10), shading='gouraud', cmap='viridis')
            fig.colorbar(pcm, ax=ax, label='Power (dB)')
            
            # --- MATRIX AESTHETICS ---
            if row == 0:
                ax.set_title(f"FILE {file_id}", fontsize=14, fontweight='bold')
                
            if col == 1:
                # Because the colorbar takes up space, we push this text further to the right
                ax.text(1.3, 0.5, gesture.upper(), transform=ax.transAxes,
                        fontsize=16, fontweight='bold', rotation=270, 
                        va='center', ha='left')
                
            ax.set_xlabel("Time (s)")
            if col == 0:
                ax.set_ylabel("Frequency (Hz)")
            
    # Leave extra space on the right so the label clears the colorbars
    plt.tight_layout(rect=[0, 0.03, 0.90, 0.95])
    plt.show()

if __name__ == "__main__":
    print("Generating beautifully formatted matrix figures...")
    print("Close the current window to load the next one!")
    
    # 1. Accelerometer Data (3 Windows)
    plot_time_domain('Accel')
    plot_fft_domain('Accel')
    plot_spectrogram_domain('Accel')
    
    # 2. Gyroscope Data (3 Windows)
    plot_time_domain('Gyro')
    plot_fft_domain('Gyro')
    plot_spectrogram_domain('Gyro')
    
    print("Analysis complete!")