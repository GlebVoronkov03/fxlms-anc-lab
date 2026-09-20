import numpy as np
import sounddevice as sd
import scipy.signal as sps
import matplotlib.pyplot as plt

def measure_ir(fs=16000, duration=3.0, input_device=None, output_device=None):
    """
    Измеряет импульсную характеристику вторичного тракта методом экспоненциального свип-синуса.
    """
    # Генерация свипа (логарифмический)
    t = np.arange(int(fs * duration)) / fs
    f0 = 20.0
    f1 = fs / 2.0
    sweep = sps.chirp(t, f0, duration, f1, method='logarithmic', phi=-90)
    
    # Плавное нарастание/затухание
    fade_len = int(0.01 * fs)
    fade = np.hanning(2 * fade_len)
    sweep[:fade_len] *= fade[:fade_len]
    sweep[-fade_len:] *= fade[fade_len:]
    
    recorded = np.zeros(len(sweep), dtype=np.float32)
    pos = 0
    
    def callback(indata, outdata, frames, time_info, status):
        nonlocal pos
        if status:
            print(f"Status: {status}")
        
        end = pos + frames
        if end <= len(sweep):
            # Обычный случай: копируем целый блок
            outdata[:, 0] = sweep[pos:end]
            recorded[pos:end] = indata[:, 0]
        else:
            # Последний блок: остаток свипа и тишина
            remaining = len(sweep) - pos
            if remaining > 0:
                outdata[:remaining, 0] = sweep[pos:]
                recorded[pos:] = indata[:remaining, 0]
            # Остальную часть выходного буфера заполняем нулями
            outdata[remaining:, 0] = 0
        pos += frames
    
    print("Запись импульсной характеристики...")
    stream = sd.Stream(
        samplerate=fs,
        blocksize=256,
        device=(input_device, output_device),
        channels=(1, 1),   # 1 вход (микрофон ошибки), 1 выход (динамик)
        callback=callback,
        dtype='float32'
    )
    
    with stream:
        # Ждём, пока проиграется весь свип + немного тишины для записи хвоста
        sd.sleep(int(duration * 1000) + 500)
    
    # Деконволюция для получения ИХ
    inv_filter = sweep[::-1]
    envelope = np.exp(np.linspace(0, np.log(f1/f0), len(inv_filter)))
    inv_filter = inv_filter * envelope
    
    ir = sps.fftconvolve(recorded, inv_filter, mode='full')
    # Обрезаем до 0.2 сек
    ir_len = int(0.2 * fs)
    ir = ir[:ir_len]
    # Нормализация
    ir = ir / np.max(np.abs(ir))
    
    # Визуализация
    plt.figure(figsize=(10, 4))
    time_ms = np.arange(ir_len) / fs * 1000
    plt.plot(time_ms, ir)
    plt.xlabel("Время (мс)")
    plt.ylabel("Амплитуда")
    plt.title("Измеренная импульсная характеристика вторичного тракта")
    plt.grid(True)
    plt.show()
    
    # Сохраняем
    np.save('sec_path_ir.npy', ir)
    print("ИХ сохранена в 'sec_path_ir.npy'")
    return ir

if __name__ == "__main__":
    print(sd.query_devices())
    # Укажите индексы ваших устройств (вход и выход)
    # Для WASAPI (рекомендуется низкая задержка):
    in_dev = 1   # Микрофон Realtek (WASAPI)
    out_dev = 4  # Динамики Realtek (WASAPI)
    # Если не работает, попробуйте MME: in_dev=1, out_dev=5
    ir = measure_ir(fs=16000, input_device=in_dev, output_device=out_dev)