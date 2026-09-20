import sounddevice as sd

def main():
    print("=" * 50)
    print("СПИСОК ВСЕХ АУДИОУСТРОЙСТВ")
    print("=" * 50)
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        print(f"{i}: {dev['name']}")
        print(f"    Каналы ввода: {dev['max_input_channels']}, вывода: {dev['max_output_channels']}")
        print(f"    Host API: {sd.query_hostapis(dev['hostapi'])['name']}")
        print(f"    Частота дискретизации по умолчанию: {dev['default_samplerate']}")
        print()
    
    print("=" * 50)
    print("УСТРОЙСТВО ВВОДА ПО УМОЛЧАНИЮ")
    default_in = sd.query_devices(kind='input')
    print(f"Индекс: {default_in['index']}, Имя: {default_in['name']}")
    print()
    
    print("УСТРОЙСТВО ВЫВОДА ПО УМОЛЧАНИЮ")
    default_out = sd.query_devices(kind='output')
    print(f"Индекс: {default_out['index']}, Имя: {default_out['name']}")
    print()

if __name__ == "__main__":
    main()