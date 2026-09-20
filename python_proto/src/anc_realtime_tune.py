import numpy as np
import sounddevice as sd
import scipy.signal as sps
import time
import threading

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
        self.gain = 1.0  # усиление выходного антишума

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

        return y * self.gain

# Глобальные переменные
fxlms = None
rms_ref = 0.0
rms_err = 0.0
rms_out = 0.0
alpha = 0.99

def audio_callback(indata, outdata, frames, time_info, status):
    global rms_ref, rms_err, rms_out, fxlms
    if status:
        print(f"Status: {status}")
    x_chunk = indata[:, 0].copy()
    d_chunk = indata[:, 1].copy()
    y_chunk = np.zeros(frames, dtype=np.float32)
    for i in range(frames):
        y_chunk[i] = fxlms.process(x_chunk[i], d_chunk[i])
    outdata[:, 0] = y_chunk
    outdata[:, 1:] = 0
    
    rms_ref = alpha * rms_ref + (1 - alpha) * np.sqrt(np.mean(x_chunk**2))
    rms_err = alpha * rms_err + (1 - alpha) * np.sqrt(np.mean(d_chunk**2))
    rms_out = alpha * rms_out + (1 - alpha) * np.sqrt(np.mean(y_chunk**2))

def input_listener():
    """Поток для изменения параметров через консоль."""
    global fxlms
    while True:
        cmd = input().strip().lower()
        if cmd.startswith('mu='):
            try:
                fxlms.mu = float(cmd.split('=')[1])
                print(f"MU = {fxlms.mu:.2e}")
            except:
                print("Неверный формат. Пример: mu=1e-5")
        elif cmd.startswith('gain='):
            try:
                fxlms.gain = float(cmd.split('=')[1])
                print(f"Gain = {fxlms.gain:.2f}")
            except:
                print("Неверный формат. Пример: gain=1.5")
        elif cmd == 'q':
            print("Завершение...")
            break
        else:
            print("Команды: mu=X.X, gain=X.X, q - выход")

def main():
    global fxlms
    INPUT_DEVICE = 14   # или 1, если WASAPI не работает
    OUTPUT_DEVICE = 12  # или 4/5
    SAMPLE_RATE = 16000
    BLOCKSIZE = 256
    MU = 1e-6            # начнём с очень малого шага

    try:
        sec_path_full = np.load('sec_path_ir.npy')
        max_len = 128
        if len(sec_path_full) > max_len:
            sec_path = sec_path_full[:max_len]
        else:
            sec_path = sec_path_full
        # Если пик ИХ отрицательный, инвертируем
        peak_idx = np.argmax(np.abs(sec_path))
        if sec_path[peak_idx] < 0:
            sec_path = -sec_path
            print("ИХ инвертирована для правильной фазы.")
        FILTER_LEN = len(sec_path)
        print(f"Загружена ИХ длиной {len(sec_path)}.")
    except FileNotFoundError:
        print("Файл 'sec_path_ir.npy' не найден!")
        return

    fxlms = FxLMS_RT(FILTER_LEN, sec_path, MU)
    fxlms.gain = 0.5  # начальное усиление (осторожно)

    # Создаём поток
    try:
        stream = sd.Stream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCKSIZE,
            device=(INPUT_DEVICE, OUTPUT_DEVICE),
            channels=(2, 2),
            callback=audio_callback,
            dtype='float32',
            extra_settings=sd.WasapiSettings(exclusive=True)
        )
        print("WASAPI exclusive mode.")
    except:
        stream = sd.Stream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCKSIZE,
            device=(INPUT_DEVICE, OUTPUT_DEVICE),
            channels=(2, 2),
            callback=audio_callback,
            dtype='float32'
        )
        print("Стандартный режим.")

    print(f"Вход: {INPUT_DEVICE}, Выход: {OUTPUT_DEVICE}")
    print("Запуск ANC. Команды: mu=..., gain=..., q - выход.")
    print("УБЕДИТЕСЬ, ЧТО ГРОМКОСТЬ МИНИМАЛЬНА!")
    
    # Запускаем поток ввода команд
    listener = threading.Thread(target=input_listener, daemon=True)
    listener.start()

    with stream:
        last_print = time.time()
        try:
            while listener.is_alive():
                time.sleep(0.1)
                if time.time() - last_print > 1.0:
                    print(f"RMS: ref={rms_ref:.3f}, err={rms_err:.3f}, out={rms_out:.3f} | mu={fxlms.mu:.1e}, gain={fxlms.gain:.2f}")
                    last_print = time.time()
        except KeyboardInterrupt:
            pass

    print("Поток остановлен.")

if __name__ == "__main__":
    main()