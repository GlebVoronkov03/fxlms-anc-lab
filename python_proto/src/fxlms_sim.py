import numpy as np
import scipy.signal as sps
import matplotlib.pyplot as plt
import soundfile as sf

class FxLMS:
    def __init__(self, filter_len, sec_path, mu=0.0001):
        self.filter_len = filter_len
        self.mu = mu
        self.w = np.zeros(filter_len)
        self.sec_path = np.array(sec_path)
        self.sec_len = len(self.sec_path)
        self.x_buf = np.zeros(filter_len)
        self.x_filt_buf = np.zeros(self.sec_len)

    def step(self, x, d):
        # Сдвиг буфера x
        self.x_buf[1:] = self.x_buf[:-1]
        self.x_buf[0] = x

        # Генерация антишума с защитой от переполнения
        y = np.dot(self.w, self.x_buf)
        if np.isnan(y) or np.isinf(y) or abs(y) > 10.0:
            y = 0.0  # Обрезаем выбросы

        # Фильтрация y через вторичный тракт
        self.x_filt_buf[1:] = self.x_filt_buf[:-1]
        self.x_filt_buf[0] = y
        y_filt = np.dot(self.sec_path, self.x_filt_buf[:self.sec_len])
        if np.isnan(y_filt) or np.isinf(y_filt):
            y_filt = 0.0

        e = d - y_filt

        # x_filt для обновления весов
        x_filt = sps.lfilter(self.sec_path, 1, self.x_buf)[::-1][:self.filter_len]

        # Обновление весов с ограничением
        self.w += self.mu * e * x_filt
        # Ограничиваем рост весов
        max_weight = 2.0
        self.w = np.clip(self.w, -max_weight, max_weight)

        return y, e

def create_realistic_sec_path(fs=16000):
    sec_len = 256
    sec_path = np.zeros(sec_len)
    delay_direct = int(0.002 * fs)
    sec_path[delay_direct] = 0.6
    sec_path[delay_direct + 5] = 0.15
    sec_path[delay_direct + 8] = 0.1
    sec_path[delay_direct + 12] = 0.08
    sec_path[delay_direct + 20] = 0.05
    window = np.hanning(5)
    window /= window.sum()
    sec_path = np.convolve(sec_path, window, mode='same')
    sec_path /= np.max(np.abs(sec_path))
    return sec_path

def simulate_anc(noise_file=None, sec_path=None, filter_len=256, mu=0.0001):
    fs = 16000

    if noise_file is None:
        duration = 5.0
        t = np.arange(int(fs * duration)) / fs
        # Нормализуем амплитуду, чтобы избежать перегрузки
        noise = 0.3 * np.sin(2 * np.pi * 100 * t) + 0.03 * np.random.randn(len(t))
        sf.write('test_noise.wav', noise, fs)
        print("Сгенерирован тестовый шум 'test_noise.wav' (амплитуда ограничена)")
    else:
        noise, fs = sf.read(noise_file)
        # Нормализация, если амплитуда слишком велика
        max_val = np.max(np.abs(noise))
        if max_val > 0.9:
            noise = noise / max_val * 0.5
            print("Амплитуда входного файла уменьшена для стабильности.")

    if sec_path is None:
        sec_path = create_realistic_sec_path(fs)
        print("Используется реалистичная модель вторичного тракта.")

    # Первичный тракт (шум -> микрофон ошибки)
    primary_delay = int(0.003 * fs)
    primary_path = np.zeros(primary_delay + 20)
    primary_path[primary_delay] = 0.8
    primary_path[primary_delay + 10] = 0.1
    d_signal = np.convolve(noise, primary_path, mode='same')

    fxlms = FxLMS(filter_len, sec_path, mu)

    y_out = np.zeros(len(noise))
    e_out = np.zeros(len(noise))

    print("Запуск симуляции...")
    for i, x in enumerate(noise):
        d = d_signal[i]
        y, e = fxlms.step(x, d)
        y_out[i] = y
        e_out[i] = e

    # Проверка на наличие некорректных значений
    if np.any(np.isnan(y_out)) or np.any(np.isinf(y_out)):
        print("Внимание: в выходных данных обнаружены NaN/Inf. Попробуйте уменьшить mu.")
    if np.any(np.isnan(e_out)) or np.any(np.isinf(e_out)):
        print("Внимание: в сигнале ошибки обнаружены NaN/Inf.")

    # Замена NaN на нули для визуализации
    y_out = np.nan_to_num(y_out, nan=0.0, posinf=0.0, neginf=0.0)
    e_out = np.nan_to_num(e_out, nan=0.0, posinf=0.0, neginf=0.0)

    # Визуализация первых 2 секунд
    plot_end = min(int(2 * fs), len(noise))
    time_axis = np.arange(plot_end) / fs

    plt.figure(figsize=(12, 10))
    plt.subplot(3, 1, 1)
    plt.plot(time_axis, noise[:plot_end])
    plt.title("Исходный шум (первые 2 сек)")
    plt.xlabel("Время (с)")
    plt.grid(True)

    plt.subplot(3, 1, 2)
    plt.plot(time_axis, y_out[:plot_end])
    plt.title("Антишум")
    plt.xlabel("Время (с)")
    plt.grid(True)

    plt.subplot(3, 1, 3)
    plt.plot(time_axis, e_out[:plot_end])
    plt.title("Остаточный шум (ошибка)")
    plt.xlabel("Время (с)")
    plt.grid(True)

    plt.tight_layout()
    plt.show()

    sf.write('residual_noise.wav', e_out, fs)
    print("Симуляция завершена. Результат сохранен в 'residual_noise.wav'")
    rms_noise = np.sqrt(np.mean(noise**2))
    rms_residual = np.sqrt(np.mean(e_out**2))
    print(f"RMS исходного шума: {rms_noise:.4f}")
    print(f"RMS остаточного шума: {rms_residual:.4f}")
    if rms_residual < rms_noise:
        reduction_db = 20 * np.log10(rms_noise / rms_residual)
        print(f"Подавление: {reduction_db:.2f} дБ")
    else:
        print("Подавления не произошло (проверьте параметры).")

    return e_out

if __name__ == "__main__":
    simulate_anc()