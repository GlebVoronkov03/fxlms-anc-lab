import numpy as np
import sounddevice as sd
import scipy.signal as sps
import time

class FxLMS_RT:
    def __init__(self, filter_len, sec_path, mu=1e-5):
        self.filter_len = filter_len
        self.mu = mu
        self.w = np.zeros(filter_len)
        self.sec_path = sec_path
        self.sec_len = len(sec_path)
        self.x_buf = np.zeros(filter_len)
        self.x_filt_buf = np.zeros(self.sec_len)
        self.leakage = 0.9999

    def process(self, x, d):
        self.x_buf[1:] = self.x_buf[:-1]
        self.x_buf[0] = x
        y = np.dot(self.w, self.x_buf)
        y = np.clip(y, -0.5, 0.5)
        self.x_filt_buf[1:] = self.x_filt_buf[:-1]
        self.x_filt_buf[0] = y
        y_filt = np.dot(self.sec_path, self.x_filt_buf)
        e = d - y_filt
        x_filt = sps.lfilter(self.sec_path, 1, self.x_buf)[::-1][:self.filter_len]
        self.w = self.leakage * self.w + self.mu * e * x_filt
        self.w = np.clip(self.w, -1.0, 1.0)
        return y

rms_ref = 0.0; rms_err = 0.0; rms_out = 0.0; alpha = 0.99

def audio_callback(indata, outdata, frames, time_info, status, fxlms):
    global rms_ref, rms_err, rms_out
    if status: print(f"Status: {status}")
    GAIN_REF = 1.0   # подкорректируйте после калибровки
    GAIN_ERR = 1.0
    x_chunk = indata[:, 0] * GAIN_REF
    d_chunk = indata[:, 1] * GAIN_ERR
    y_chunk = np.zeros(frames, dtype=np.float32)
    for i in range(frames):
        y_chunk[i] = fxlms.process(x_chunk[i], d_chunk[i])
    outdata[:, 0] = y_chunk
    outdata[:, 1:] = 0
    rms_ref = alpha * rms_ref + (1-alpha) * np.sqrt(np.mean(x_chunk**2))
    rms_err = alpha * rms_err + (1-alpha) * np.sqrt(np.mean(d_chunk**2))
    rms_out = alpha * rms_out + (1-alpha) * np.sqrt(np.mean(y_chunk**2))

def main():
    SAMPLE_RATE = 48000
    BLOCKSIZE = 1024
    MU = 1e-5
    INPUT_DEVICE = 18    # или None
    OUTPUT_DEVICE = 15   # или None

    try:
        ir_full = np.load('sec_path_ir.npy')
        peak = np.argmax(np.abs(ir_full))
        if ir_full[peak] < 0:
            ir_full = -ir_full
            print("ИХ инвертирована.")
        FILTER_LEN = min(len(ir_full), 256)
        sec_path = ir_full[:FILTER_LEN]
        print(f"Загружена ИХ длиной {FILTER_LEN}")
    except FileNotFoundError:
        print("Файл sec_path_ir.npy не найден! Сначала запустите measure_ir_wasapi_default.py")
        return

    fxlms = FxLMS_RT(FILTER_LEN, sec_path, MU)

    try:
        stream = sd.Stream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCKSIZE,
            device=(INPUT_DEVICE, OUTPUT_DEVICE),
            channels=(2, 2),
            callback=lambda *args: audio_callback(*args, fxlms=fxlms),
            dtype='float32'
        )
        print("Поток открыт")
    except Exception as e:
        print(f"Ошибка открытия потока: {e}")
        return

    print("ANC запущен. ГРОМКОСТЬ НА МИНИМУМ! Ctrl+C для остановки.")
    with stream:
        last_print = time.time()
        try:
            while True:
                time.sleep(0.1)
                if time.time() - last_print > 1.0:
                    print(f"RMS: ref={rms_ref:.3f}, err={rms_err:.3f}, out={rms_out:.3f}")
                    last_print = time.time()
        except KeyboardInterrupt:
            pass
    print("Остановлено.")

if __name__ == "__main__":
    main()