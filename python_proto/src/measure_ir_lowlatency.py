import numpy as np
import sounddevice as sd
import scipy.signal as sps
import matplotlib.pyplot as plt

def find_ks_devices():
    """Находит индексы устройств WDM-KS для входа и выхода."""
    devices = sd.query_devices()
    ks_in, ks_out = None, None
    for i, dev in enumerate(devices):
        name = dev['name'].lower()
        if 'wdm-ks' in name:
            if dev['max_input_channels'] > 0 and ks_in is None:
                ks_in = i
                print(f"Найден WDM-KS вход: {i} - {dev['name']}")
            if dev['max_output_channels'] > 0 and ks_out is None:
                ks_out = i
                print(f"Найден WDM-KS выход: {i} - {dev['name']}")
    return ks_in, ks_out

def measure_ir(fs=48000, duration=3.0, input_device=None, output_device=None):
    """
    Измерение ИХ с автоматическим подбором режима.
    fs: частота дискретизации (48000 обычно поддерживается)
    """
    # Генерация свипа
    t = np.arange(int(fs * duration)) / fs
    f0, f1 = 20.0, fs/2.0 * 0.9  # небольшой запас до Найквиста
    sweep = sps.chirp(t, f0, duration, f1, method='logarithmic', phi=-90)
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
            outdata[:, 0] = sweep[pos:end]
            recorded[pos:end] = indata[:, 0]
        else:
            rem = len(sweep) - pos
            if rem > 0:
                outdata[:rem, 0] = sweep[pos:]
                recorded[pos:] = indata[:rem, 0]
            outdata[rem:, 0] = 0
        pos += frames

    # Попытка 1: WASAPI exclusive с указанной частотой
    print(f"\n=== Попытка WASAPI exclusive (fs={fs} Гц) ===")
    try:
        stream = sd.Stream(
            samplerate=fs,
            blocksize=128,
            device=(input_device, output_device),
            channels=(1, 1),
            callback=callback,
            dtype='float32',
            extra_settings=sd.WasapiSettings(exclusive=True)
        )
        print("Успешно! Используется WASAPI exclusive.")
        mode = "wasapi_ex"
    except Exception as e:
        print(f"WASAPI exclusive ошибка: {e}")
        
        # Попытка 2: WDM-KS
        print("\n=== Попытка WDM-KS ===")
        ks_in, ks_out = find_ks_devices()
        if ks_in is not None and ks_out is not None:
            try:
                stream = sd.Stream(
                    samplerate=fs,
                    blocksize=128,
                    device=(ks_in, ks_out),
                    channels=(1, 1),
                    callback=callback,
                    dtype='float32'
                )
                print(f"Успешно! Используется WDM-KS (вход={ks_in}, выход={ks_out}).")
                mode = "wdm_ks"
            except Exception as e2:
                print(f"WDM-KS ошибка: {e2}")
                mode = None
        else:
            print("WDM-KS устройства не найдены.")
            mode = None

    # Попытка 3: WASAPI shared (fallback)
    if mode is None:
        print("\n=== Попытка WASAPI shared ===")
        try:
            stream = sd.Stream(
                samplerate=fs,
                blocksize=256,
                device=(input_device, output_device),
                channels=(1, 1),
                callback=callback,
                dtype='float32'
            )
            print("Успешно! Используется WASAPI shared (возможна доп. задержка).")
            mode = "wasapi_shared"
        except Exception as e:
            print(f"Все попытки провалились: {e}")
            return None

    print("Запись импульсной характеристики...")
    with stream:
        sd.sleep(int(duration * 1000) + 500)

    # Деконволюция
    inv_filter = sweep[::-1] * np.exp(np.linspace(0, np.log(f1/f0), len(sweep)))
    ir = sps.fftconvolve(recorded, inv_filter, mode='full')
    
    # Обрезаем до 50 мс (при 48 кГц это 2400 сэмплов)
    ir_len = int(0.05 * fs)
    ir = ir[:ir_len]
    ir = ir / np.max(np.abs(ir))

    # Визуализация
    time_ms = np.arange(len(ir)) / fs * 1000
    plt.figure(figsize=(10,4))
    plt.plot(time_ms, ir)
    plt.xlabel('Время (мс)')
    plt.ylabel('Амплитуда')
    plt.title(f'Импульсная характеристика ({mode})')
    plt.grid(True)
    peak_idx = np.argmax(np.abs(ir))
    peak_time = peak_idx / fs * 1000
    plt.axvline(peak_time, color='r', linestyle='--', label=f'Пик {peak_time:.2f} мс')
    plt.legend()
    plt.show()

    np.save('sec_path_ir.npy', ir)
    print(f"ИХ сохранена в 'sec_path_ir.npy'")
    print(f"Частота дискретизации: {fs} Гц")
    print(f"Длина ИХ: {len(ir)} сэмплов ({len(ir)/fs*1000:.1f} мс)")
    print(f"Задержка пика: {peak_time:.2f} мс")
    return ir

if __name__ == "__main__":
    print(sd.query_devices())
    
    # Рекомендуемые индексы для WASAPI
    in_dev = 14   # Микрофон Realtek WASAPI
    out_dev = 12  # Динамики Realtek WASAPI
    
    # Пробуем частоту 48000 Гц (стандарт для Windows)
    ir = measure_ir(fs=48000, input_device=in_dev, output_device=out_dev)
    
    if ir is None:
        print("\nПопробуйте вручную указать WDM-KS индексы:")
        ks_in, ks_out = find_ks_devices()
        if ks_in and ks_out:
            print(f"Вход: {ks_in}, Выход: {ks_out}")
            ir = measure_ir(fs=48000, input_device=ks_in, output_device=ks_out)