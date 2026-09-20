"""Сравнение двух пар петличных микрофонов и USB-микшера Q-12M.

Запускать через run_hardware_compare.bat. Записи и отчёты сохраняются
в python_proto/measurements/hardware_compare.
"""

from __future__ import annotations

import csv
import json
import math
import os
import queue
import threading
import time
import tkinter as tk
import winreg
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import numpy as np
import sounddevice as sd
from scipy.io import wavfile


APP_TITLE = "QuietRadius — сравнение железа"
SAMPLE_RATE = 48_000
BLOCK_SIZE = 256
BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "measurements" / "hardware_compare"
EPS = 1e-12
CLICK_OFFSET_S = 0.35
CLICK_AMP = 0.22

PAIRS = {
    "Boya BY-M1": {
        "id": "boya_bym1",
        "has_battery": True,
        "setup": (
            "Q-12M: USB в ноутбук, переключатель Stereo, 48V выкл, HPF/80 Hz выкл, "
            "эквалайзер в ноль. Два одинаковых BY-M1: свежая LR44, режим Camera. "
            "Каждый через переходник 3.5 TRRS → 6.35 TS. Микрофон 1 → Input 1, "
            "микрофон 2 → Input 2. Gain обоих каналов одинаковый, без клиппинга."
        ),
    },
    "Maono AU-402L": {
        "id": "maono_au402l",
        "has_battery": False,
        "setup": (
            "Q-12M: Stereo, 48V выкл, HPF выкл. У AU-402L нет батареи — питание "
            "только plug-in power. Два одинаковых AU-402L через 3.5 → 6.35 TS в "
            "Input 1 и Input 2. Если оба канала почти молчат, вход 6.35 мм, "
            "скорее всего, не питает капсюль: это брак питания, не «плохой звук»."
        ),
    },
}

TESTS = {
    "Живые уровни (без лимита)": {
        "duration": None,
        "kind": "live",
        "needs_output": False,
        "instruction": (
            "Говорите по очереди в каждый микрофон и смотрите, какой столбик "
            "растёт. Нажмите «Стоп», когда закончите."
        ),
    },
    "Тишина / собственный шум — 8 с": {
        "duration": 8,
        "kind": "silence",
        "needs_output": False,
        "instruction": (
            "Положите оба микрофона рядом, не касайтесь стола и молчите. "
            "Закройте окна. Этот тест нужен и для пары, и для шума микшера."
        ),
    },
    "Микрофон 1 (вход 1 / L) — 8 с": {
        "duration": 8,
        "kind": "mic1",
        "needs_output": False,
        "instruction": (
            "Изолируйте микрофон 2 тканью или рукой. Говорите вплотную только "
            "в микрофон 1. Должен вырасти левый канал."
        ),
    },
    "Микрофон 2 (вход 2 / R) — 8 с": {
        "duration": 8,
        "kind": "mic2",
        "needs_output": False,
        "instruction": (
            "Изолируйте микрофон 1. Говорите вплотную только в микрофон 2. "
            "Должен вырасти правый канал."
        ),
    },
    "Маршрут 1 → пауза → 2 — 12 с": {
        "duration": 12,
        "kind": "route",
        "needs_output": False,
        "instruction": (
            "0–4 с: только микрофон 1. 4–6 с: тишина. 6–12 с: только микрофон 2. "
            "Программа сама разрежет запись на три окна."
        ),
    },
    "Задержка микшера (клик) — 3 с": {
        "duration": 3,
        "kind": "latency",
        "needs_output": True,
        "instruction": (
            "Это тест микшера, не микрофонов. Подключите наушники или колонки к "
            "выходу Q-12M. Поднесите микрофон 1 вплотную к динамику. Громкость "
            "низкая. Прозвучит короткий щелчок."
        ),
    },
}


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(abs(value), EPS))


def safe_corr(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 2 or np.std(left) < EPS or np.std(right) < EPS:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def fmt(value: float | None, suffix: str = "", digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}{suffix}"


def slug(text: str) -> str:
    return (
        text.lower()
        .replace("—", "_")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(" ", "_")
    )


@dataclass
class TestResult:
    timestamp: str
    test: str
    kind: str
    pair: str
    mixer_mode: str
    mic_power: str
    device: str
    device_index: int
    output_device: str
    host_api: str
    sample_rate: int
    channels: int
    duration_s: float
    rms_left_dbfs: float
    rms_right_dbfs: float | None
    peak_left_dbfs: float
    peak_right_dbfs: float | None
    dc_left: float
    dc_right: float | None
    clipping_left_pct: float
    clipping_right_pct: float | None
    correlation_lr: float | None
    difference_dbfs: float | None
    balance_db: float | None
    separation_db: float | None
    win1_balance_db: float | None
    win_pause_rms_dbfs: float | None
    win2_balance_db: float | None
    route_swapped: bool | None
    latency_ms: float | None
    verdict: str
    wav_file: str


class HardwareCompareApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1180x860")
        self.root.minsize(980, 740)

        self.stream: sd.Stream | sd.InputStream | None = None
        self.running = False
        self.started_at = 0.0
        self.stop_timer: str | None = None
        self.audio_chunks: list[np.ndarray] = []
        self.level_queue: queue.Queue[tuple[float, float, str]] = queue.Queue()
        self.input_map: dict[str, int] = {}
        self.output_map: dict[str, int] = {}
        self.session_results: list[TestResult] = []
        self.current_context: dict[str, object] = {}
        self.summary_signatures: set[str] = set()
        self.playback = np.zeros(1, dtype=np.float32)
        self.playback_pos = 0

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.show_all_devices_var = tk.BooleanVar(value=False)
        self.device_hint_var = tk.StringVar(
            value="Q-12M в Windows называется «MP3-Audio». Ищите строку с Q-12M ★ и WASAPI."
        )
        self.test_var = tk.StringVar(value=next(iter(TESTS)))
        self.pair_var = tk.StringVar(value="Boya BY-M1")
        self.mixer_mode_var = tk.StringVar(value="Stereo")
        self.mic_power_var = tk.StringVar(value="Camera / LR44")
        self.status_var = tk.StringVar(value="Готово. Сначала Boya, потом Maono.")
        self.recommend_var = tk.StringVar(
            value="Рекомендация появится после тестов «Микрофон 1» и «Микрофон 2» для обеих пар."
        )
        self.timer_var = tk.StringVar(value="00:00")
        self.left_db_var = tk.StringVar(value="−∞ dBFS")
        self.right_db_var = tk.StringVar(value="−∞ dBFS")
        self.instruction_var = tk.StringVar()
        self.setup_var = tk.StringVar()
        self.windows_status_var = tk.StringVar(value="Проверяю Windows…")

        self._configure_style()
        self._build_ui()
        self.refresh_devices()
        self.refresh_windows_status()
        self._on_pair_changed()
        self._on_test_changed()
        self.root.after(80, self._poll_levels)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure(".", font=("Segoe UI", 11))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 18))
        style.configure("Heading.TLabel", font=("Segoe UI Semibold", 12))
        style.configure("Instruction.TLabel", font=("Segoe UI Semibold", 13))
        style.configure("Recommend.TLabel", font=("Segoe UI Semibold", 12), wraplength=1100)
        style.configure("Big.TButton", font=("Segoe UI Semibold", 12), padding=(18, 10))
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text=APP_TITLE, style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=(
                "Цель: оставить одну пару микрофонов и понять, годится ли Q-12M "
                "как двухканальный вход для ANC. Записи только на этом ПК."
            ),
        ).pack(anchor=tk.W, pady=(2, 10))

        settings = ttk.LabelFrame(outer, text="1. Что проверяем", padding=10)
        settings.pack(fill=tk.X)
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Вход (микшер):").grid(row=0, column=0, sticky=tk.W)
        self.input_combo = ttk.Combobox(
            settings, textvariable=self.input_var, state="readonly", width=78, height=18
        )
        self.input_combo.grid(row=0, column=1, sticky=tk.EW)
        self.input_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_device_hint())
        ttk.Button(settings, text="Обновить", command=self.refresh_devices).grid(
            row=0, column=2, padx=(8, 0)
        )

        ttk.Label(settings, text="Выход (для задержки):").grid(
            row=1, column=0, sticky=tk.W, pady=(8, 0)
        )
        self.output_combo = ttk.Combobox(
            settings, textvariable=self.output_var, state="readonly", width=78, height=18
        )
        self.output_combo.grid(row=1, column=1, sticky=tk.EW, pady=(8, 0))
        self.output_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_device_hint())

        hint_frame = ttk.Frame(settings)
        hint_frame.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(6, 0))
        ttk.Label(hint_frame, textvariable=self.device_hint_var, wraplength=980).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Checkbutton(
            hint_frame,
            text="Показать все устройства",
            variable=self.show_all_devices_var,
            command=self.refresh_devices,
        ).pack(side=tk.RIGHT)

        ttk.Label(settings, text="Пара микрофонов:").grid(
            row=3, column=0, sticky=tk.W, pady=(8, 0)
        )
        pair_frame = ttk.Frame(settings)
        pair_frame.grid(row=3, column=1, sticky=tk.W, pady=(8, 0))
        ttk.Radiobutton(
            pair_frame,
            text="Boya BY-M1",
            variable=self.pair_var,
            value="Boya BY-M1",
            command=self._on_pair_changed,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            pair_frame,
            text="Maono AU-402L",
            variable=self.pair_var,
            value="Maono AU-402L",
            command=self._on_pair_changed,
        ).pack(side=tk.LEFT, padx=(20, 0))

        ttk.Label(settings, text="Режим Q-12M:").grid(
            row=4, column=0, sticky=tk.W, pady=(8, 0)
        )
        mix_frame = ttk.Frame(settings)
        mix_frame.grid(row=4, column=1, sticky=tk.W, pady=(8, 0))
        ttk.Radiobutton(
            mix_frame, text="Stereo", variable=self.mixer_mode_var, value="Stereo"
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            mix_frame, text="Mono (только для проверки)", variable=self.mixer_mode_var, value="Mono"
        ).pack(side=tk.LEFT, padx=(20, 0))

        ttk.Label(settings, text="Питание микрофона:").grid(
            row=5, column=0, sticky=tk.W, pady=(8, 0)
        )
        self.power_combo = ttk.Combobox(
            settings,
            textvariable=self.mic_power_var,
            values=("Camera / LR44", "OFF / Smartphone", "Без батареи / plug-in"),
            state="readonly",
            width=36,
        )
        self.power_combo.grid(row=5, column=1, sticky=tk.W, pady=(8, 0))

        ttk.Label(settings, text="Тест:").grid(row=6, column=0, sticky=tk.W, pady=(8, 0))
        self.test_combo = ttk.Combobox(
            settings,
            textvariable=self.test_var,
            values=list(TESTS),
            state="readonly",
            width=78,
        )
        self.test_combo.grid(row=6, column=1, sticky=tk.EW, pady=(8, 0))
        self.test_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_test_changed())

        win_frame = ttk.Frame(settings)
        win_frame.grid(row=7, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0))
        ttk.Label(win_frame, textvariable=self.windows_status_var).pack(side=tk.LEFT)
        ttk.Button(win_frame, text="Звук Windows", command=self.open_sound_settings).pack(
            side=tk.RIGHT
        )
        ttk.Button(
            win_frame, text="Доступ к микрофону", command=self.open_privacy_settings
        ).pack(side=tk.RIGHT, padx=8)

        setup = ttk.LabelFrame(outer, text="2. Подключение сейчас", padding=10)
        setup.pack(fill=tk.X, pady=10)
        ttk.Label(
            setup,
            textvariable=self.setup_var,
            wraplength=1100,
            justify=tk.LEFT,
        ).pack(anchor=tk.W)
        ttk.Label(
            setup,
            textvariable=self.instruction_var,
            style="Instruction.TLabel",
            wraplength=1100,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X)
        self.start_button = ttk.Button(
            controls, text="▶  Старт", style="Big.TButton", command=self.start_test
        )
        self.start_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(
            controls,
            text="■  Стоп",
            style="Big.TButton",
            command=self.stop_test,
            state=tk.DISABLED,
        )
        self.stop_button.pack(side=tk.LEFT, padx=10)
        ttk.Label(controls, textvariable=self.status_var, style="Heading.TLabel").pack(
            side=tk.LEFT, padx=12
        )
        ttk.Label(controls, textvariable=self.timer_var, style="Title.TLabel").pack(
            side=tk.RIGHT
        )

        meters = ttk.LabelFrame(outer, text="3. Живые уровни", padding=10)
        meters.pack(fill=tk.X, pady=10)
        meters.columnconfigure(1, weight=1)
        ttk.Label(meters, text="Вход 1 / L", width=12).grid(row=0, column=0, sticky=tk.W)
        self.left_meter = ttk.Progressbar(meters, maximum=60)
        self.left_meter.grid(row=0, column=1, sticky=tk.EW, padx=8)
        ttk.Label(meters, textvariable=self.left_db_var, width=12).grid(row=0, column=2)
        ttk.Label(meters, text="Вход 2 / R", width=12).grid(row=1, column=0, sticky=tk.W)
        self.right_meter = ttk.Progressbar(meters, maximum=60)
        self.right_meter.grid(row=1, column=1, sticky=tk.EW, padx=8, pady=(8, 0))
        ttk.Label(meters, textvariable=self.right_db_var, width=12).grid(
            row=1, column=2, pady=(8, 0)
        )
        ttk.Label(
            meters,
            text="Речь: примерно −30…−12 dBFS. Не доходите до 0 dBFS.",
        ).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(8, 0))

        rec = ttk.LabelFrame(outer, text="4. Рекомендация", padding=8)
        rec.pack(fill=tk.X)
        ttk.Label(rec, textvariable=self.recommend_var, style="Recommend.TLabel").pack(
            anchor=tk.W
        )

        results = ttk.LabelFrame(outer, text="5. Результаты сессии", padding=8)
        results.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        columns = ("pair", "test", "left", "right", "corr", "sep", "extra", "verdict")
        self.tree = ttk.Treeview(results, columns=columns, show="headings", height=8)
        headings = {
            "pair": "Пара",
            "test": "Тест",
            "left": "RMS L",
            "right": "RMS R",
            "corr": "Корр.",
            "sep": "Разд.",
            "extra": "Маршрут / мс",
            "verdict": "Вывод",
        }
        widths = {
            "pair": 130,
            "test": 200,
            "left": 78,
            "right": 78,
            "corr": 70,
            "sep": 70,
            "extra": 130,
            "verdict": 320,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        scrollbar = ttk.Scrollbar(results, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh_devices(self) -> None:
        current_in = self.input_var.get()
        current_out = self.output_var.get()
        self.input_map.clear()
        self.output_map.clear()
        inputs: list[str] = []
        outputs: list[str] = []
        show_all = bool(self.show_all_devices_var.get())
        try:
            host_apis = sd.query_hostapis()
            raw_in: list[tuple[int, str, int]] = []
            raw_out: list[tuple[int, str, int]] = []
            for index, device in enumerate(sd.query_devices()):
                host_name = str(host_apis[device["hostapi"]]["name"])
                name = str(device["name"])
                in_ch = int(device["max_input_channels"])
                out_ch = int(device["max_output_channels"])
                rate = int(device["default_samplerate"])
                if in_ch >= 1 and self._keep_device(name, host_name, in_ch, show_all):
                    label = self._device_label(index, name, host_name, in_ch, rate, "in")
                    self.input_map[label] = index
                    raw_in.append((self._sort_key(name, host_name, in_ch), index, label))
                if out_ch >= 1 and self._keep_device(name, host_name, out_ch, show_all):
                    label = self._device_label(index, name, host_name, out_ch, rate, "out")
                    self.output_map[label] = index
                    raw_out.append((self._sort_key(name, host_name, out_ch), index, label))
            raw_in.sort()
            raw_out.sort()
            inputs = [item[2] for item in raw_in]
            outputs = [item[2] for item in raw_out]
        except Exception as exc:
            messagebox.showerror("Аудиоустройства", f"Не удалось получить список:\n{exc}")
            return

        self.input_combo["values"] = inputs
        self.output_combo["values"] = outputs
        self.input_var.set(self._prefer_device(inputs, current_in))
        self.output_var.set(self._prefer_device(outputs, current_out))
        self._update_device_hint()

    @staticmethod
    def _is_mixer_name(name: str) -> bool:
        low = name.lower()
        return any(
            marker in low
            for marker in ("mp3-audio", "q-12", "q12", "teyun", "bomge")
        )

    @classmethod
    def _keep_device(cls, name: str, host: str, channels: int, show_all: bool) -> bool:
        if show_all:
            return True
        if "WASAPI" not in host:
            return False
        if cls._is_mixer_name(name):
            return True
        return channels >= 2

    @classmethod
    def _sort_key(cls, name: str, host: str, channels: int) -> int:
        mixer = cls._is_mixer_name(name)
        wasapi = "WASAPI" in host
        if mixer and wasapi:
            return 0
        if mixer:
            return 1
        if wasapi and channels >= 2:
            return 2
        return 3

    @classmethod
    def _device_label(
        cls,
        index: int,
        name: str,
        host: str,
        channels: int,
        rate: int,
        direction: str,
    ) -> str:
        prefix = "Q-12M ★  " if cls._is_mixer_name(name) else ""
        return (
            f"{prefix}{index}: {name}  |  {host}  |  "
            f"{channels} ch {direction}  |  {rate} Hz"
        )

    def _prefer_device(self, labels: list[str], current: str) -> str:
        if current in labels:
            return current
        preferred = next(
            (
                label
                for label in labels
                if "Q-12M ★" in label and "WASAPI" in label and "2 ch" in label
            ),
            None,
        )
        if preferred:
            return preferred
        preferred = next(
            (label for label in labels if "WASAPI" in label and "2 ch" in label),
            None,
        )
        if preferred:
            return preferred
        return labels[0] if labels else ""

    def _update_device_hint(self) -> None:
        in_label = self.input_var.get()
        out_label = self.output_var.get()
        if "Q-12M ★" in in_label and "Q-12M ★" in out_label and "WASAPI" in in_label:
            self.device_hint_var.set(
                "Выбрано верно: Q-12M отображается как MP3-Audio, WASAPI, 2 канала. "
                "Realtek и DroidCam не нужны."
            )
        elif "MP3-Audio" in in_label or "Q-12M ★" in in_label:
            self.device_hint_var.set(
                "Вход найден. Для теста задержки выход тоже должен быть MP3-Audio / Q-12M ★, WASAPI."
            )
        elif not in_label:
            self.device_hint_var.set(
                "Микшер не найден. Проверьте USB и нажмите «Обновить». "
                "В Windows он называется «MP3-Audio», не Q-12M."
            )
        else:
            self.device_hint_var.set(
                "Сейчас выбран не микшер. Откройте список и возьмите строку «Q-12M ★» "
                "с WASAPI. Не Realtek и не DroidCam."
            )

    def refresh_windows_status(self) -> None:
        self.windows_status_var.set(
            f"Windows: микрофон — {self._read_privacy_status()}; "
            "формат теста — 2 ch / 48 кГц; эффекты микшера в Windows лучше выключить"
        )

    @staticmethod
    def _read_privacy_status() -> str:
        path = (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion"
            r"\CapabilityAccessManager\ConsentStore\microphone"
        )
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                value, _ = winreg.QueryValueEx(key, "Value")
            return "разрешён" if value == "Allow" else str(value)
        except OSError:
            return "не удалось проверить"

    @staticmethod
    def open_sound_settings() -> None:
        os.startfile("ms-settings:sound")  # type: ignore[attr-defined]

    @staticmethod
    def open_privacy_settings() -> None:
        os.startfile("ms-settings:privacy-microphone")  # type: ignore[attr-defined]

    def _on_pair_changed(self) -> None:
        pair = self.pair_var.get()
        self.setup_var.set(PAIRS[pair]["setup"])
        if PAIRS[pair]["has_battery"]:
            self.mic_power_var.set("Camera / LR44")
        else:
            self.mic_power_var.set("Без батареи / plug-in")

    def _on_test_changed(self) -> None:
        self.instruction_var.set(TESTS[self.test_var.get()]["instruction"])

    def start_test(self) -> None:
        if self.running:
            return
        in_label = self.input_var.get()
        if in_label not in self.input_map:
            messagebox.showwarning("Устройство", "Выберите вход микшера.")
            return
        device_index = self.input_map[in_label]
        info = sd.query_devices(device_index)
        channels = min(2, int(info["max_input_channels"]))
        if channels < 2:
            if not messagebox.askyesno(
                "Только один канал",
                "Микшер виден как 1 входной канал. Для ANC это сразу непригодно. "
                "Запустить только измерение уровня?",
            ):
                return

        test_name = self.test_var.get()
        spec = TESTS[test_name]
        out_index: int | None = None
        out_label = self.output_var.get()
        if spec["needs_output"]:
            if out_label not in self.output_map:
                messagebox.showwarning("Выход", "Для теста задержки выберите выход Q-12M.")
                return
            out_index = self.output_map[out_label]
            if not messagebox.askokcancel(
                "Щелчок",
                "Сейчас коротко прозвучит щелчок. Громкость должна быть низкой, "
                "микрофон 1 — у динамика.",
            ):
                return

        try:
            sd.check_input_settings(
                device=device_index,
                channels=channels,
                samplerate=SAMPLE_RATE,
                dtype="float32",
            )
            self.audio_chunks.clear()
            while not self.level_queue.empty():
                self.level_queue.get_nowait()
            self.playback_pos = 0
            if spec["needs_output"] and out_index is not None:
                duration = float(spec["duration"] or 3)
                n = int(SAMPLE_RATE * duration)
                self.playback = np.zeros(n, dtype=np.float32)
                click = int(CLICK_OFFSET_S * SAMPLE_RATE)
                width = max(1, int(0.001 * SAMPLE_RATE))
                self.playback[click : click + width] = CLICK_AMP
                out_info = sd.query_devices(out_index)
                out_ch = min(2, int(out_info["max_output_channels"]))
                self.stream = sd.Stream(
                    device=(device_index, out_index),
                    channels=(channels, out_ch),
                    samplerate=SAMPLE_RATE,
                    blocksize=BLOCK_SIZE,
                    dtype="float32",
                    latency="low",
                    callback=self._duplex_callback,
                )
            else:
                self.playback = np.zeros(1, dtype=np.float32)
                self.stream = sd.InputStream(
                    device=device_index,
                    channels=channels,
                    samplerate=SAMPLE_RATE,
                    blocksize=BLOCK_SIZE,
                    dtype="float32",
                    latency="low",
                    callback=self._audio_callback,
                )
            self.current_context = {
                "test_name": test_name,
                "kind": spec["kind"],
                "pair": self.pair_var.get(),
                "mixer_mode": self.mixer_mode_var.get(),
                "mic_power": self.mic_power_var.get(),
                "device_label": in_label,
                "device_index": device_index,
                "output_label": out_label if spec["needs_output"] else "",
            }
            self.stream.start()
        except Exception as exc:
            self.stream = None
            messagebox.showerror(
                "Не удалось начать запись",
                f"{exc}\n\nЗакройте приложения, которые заняли Q-12M, "
                "и выберите WASAPI-устройство микшера.",
            )
            return

        self.running = True
        self.started_at = time.monotonic()
        self.status_var.set(
            f"Идёт • {self.pair_var.get()} • Q-12M {self.mixer_mode_var.get()}"
        )
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        duration = spec["duration"]
        if duration:
            self.stop_timer = self.root.after(int(duration * 1000), self.stop_test)
        self._update_timer()

    def _push_levels(self, chunk: np.ndarray, status: sd.CallbackFlags) -> None:
        left_rms = float(np.sqrt(np.mean(chunk[:, 0] ** 2)))
        right_rms = (
            float(np.sqrt(np.mean(chunk[:, 1] ** 2))) if chunk.shape[1] > 1 else 0.0
        )
        self.level_queue.put((dbfs(left_rms), dbfs(right_rms), str(status) if status else ""))

    def _audio_callback(
        self,
        indata: np.ndarray,
        _frames: int,
        _time_info: sd.CallbackFlags,
        status: sd.CallbackFlags,
    ) -> None:
        if not self.running and self.started_at != 0:
            return
        chunk = indata.copy()
        self.audio_chunks.append(chunk)
        self._push_levels(chunk, status)

    def _duplex_callback(
        self,
        indata: np.ndarray,
        outdata: np.ndarray,
        _frames: int,
        _time_info: sd.CallbackFlags,
        status: sd.CallbackFlags,
    ) -> None:
        frames = outdata.shape[0]
        start = self.playback_pos
        end = start + frames
        block = np.zeros(frames, dtype=np.float32)
        if start < len(self.playback):
            take = min(frames, len(self.playback) - start)
            block[:take] = self.playback[start : start + take]
        self.playback_pos = end
        outdata[:] = 0
        outdata[:, 0] = block
        if outdata.shape[1] > 1:
            outdata[:, 1] = block
        if self.running or self.started_at == 0:
            chunk = indata.copy()
            self.audio_chunks.append(chunk)
            self._push_levels(chunk, status)

    def _poll_levels(self) -> None:
        latest: tuple[float, float, str] | None = None
        try:
            while True:
                latest = self.level_queue.get_nowait()
        except queue.Empty:
            pass
        if latest:
            left, right, status = latest
            self.left_db_var.set(f"{left:.1f} dBFS")
            self.right_db_var.set(f"{right:.1f} dBFS")
            self.left_meter["value"] = max(0.0, min(60.0, left + 60.0))
            self.right_meter["value"] = max(0.0, min(60.0, right + 60.0))
            if status:
                self.status_var.set(f"Аудио: {status}")
        self.root.after(80, self._poll_levels)

    def _update_timer(self) -> None:
        if not self.running:
            return
        elapsed = time.monotonic() - self.started_at
        self.timer_var.set(f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}")
        self.root.after(200, self._update_timer)

    def stop_test(self) -> None:
        if not self.running:
            return
        self.running = False
        if self.stop_timer:
            self.root.after_cancel(self.stop_timer)
            self.stop_timer = None
        stream = self.stream
        self.stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set("Анализирую и сохраняю…")
        chunks = self.audio_chunks[:]
        self.audio_chunks.clear()
        threading.Thread(target=self._analyze_and_save, args=(chunks,), daemon=True).start()

    def _analyze_and_save(self, chunks: list[np.ndarray]) -> None:
        try:
            if not chunks:
                raise ValueError("Нет записанных данных.")
            audio = np.concatenate(chunks, axis=0)
            result = self._analyze(audio)
            self.session_results.append(result)
            self._write_session_files()
            self.root.after(0, lambda: self._show_result(result))
        except Exception as exc:
            self.root.after(
                0,
                lambda: messagebox.showerror("Анализ", f"Не удалось обработать тест:\n{exc}"),
            )
            self.root.after(0, lambda: self.status_var.set("Ошибка анализа."))

    def _analyze(self, audio: np.ndarray) -> TestResult:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        test_name = str(self.current_context["test_name"])
        kind = str(self.current_context["kind"])
        pair = str(self.current_context["pair"])
        mixer_mode = str(self.current_context["mixer_mode"])
        mic_power = str(self.current_context["mic_power"])
        stem = f"{timestamp}_{slug(pair)}_{slug(test_name)}"
        wav_path = OUTPUT_DIR / f"{stem}.wav"

        normalized = np.clip(audio, -1.0, 1.0)
        wavfile.write(wav_path, SAMPLE_RATE, (normalized * 32767).astype(np.int16))

        left = audio[:, 0].astype(np.float64)
        right = audio[:, 1].astype(np.float64) if audio.shape[1] > 1 else None
        rms_l = float(np.sqrt(np.mean(left**2)))
        peak_l = float(np.max(np.abs(left)))
        dc_l = float(np.mean(left))
        clip_l = float(np.mean(np.abs(left) >= 0.999) * 100.0)

        rms_r = peak_r = dc_r = clip_r = corr = diff_level = balance = separation = None
        win1 = pause_rms = win2 = None
        swapped: bool | None = None
        latency_ms: float | None = None
        verdict = "Моно: два независимых канала недоступны, микшер для ANC не подходит."

        if right is not None:
            rms_r_raw = float(np.sqrt(np.mean(right**2)))
            peak_r_raw = float(np.max(np.abs(right)))
            rms_r = dbfs(rms_r_raw)
            peak_r = dbfs(peak_r_raw)
            dc_r = float(np.mean(right))
            clip_r = float(np.mean(np.abs(right) >= 0.999) * 100.0)
            corr = safe_corr(left, right)
            difference = left - right
            diff_rms = float(np.sqrt(np.mean(difference**2)))
            diff_level = dbfs(diff_rms)
            balance = dbfs(rms_l) - dbfs(rms_r_raw)
            separation = abs(balance)
            relative_diff = diff_rms / max(rms_l, rms_r_raw, EPS)
            active = kind in {"mic1", "mic2", "route", "live"}
            loudest = max(dbfs(rms_l), dbfs(rms_r_raw))
            peakest = max(dbfs(peak_l), dbfs(peak_r_raw))
            weak = active and loudest < -40.0 and peakest < -25.0

            if kind == "route":
                win1, pause_rms, win2, swapped = self._route_windows(left, right)

            if kind == "latency":
                latency_ms = self._measure_latency(left, right)
                if latency_ms is None:
                    verdict = "Щелчок не найден. Поднесите микрофон ближе и повторите."
                elif latency_ms <= 8:
                    verdict = f"Задержка {latency_ms:.1f} мс: для лабораторного ANC приемлемо."
                elif latency_ms <= 20:
                    verdict = (
                        f"Задержка {latency_ms:.1f} мс: для широкополосного ANC слабо, "
                        "для низких частот ещё можно пробовать."
                    )
                else:
                    verdict = (
                        f"Задержка {latency_ms:.1f} мс: для активного подавления слишком много."
                    )
            elif clip_l > 0.01 or (clip_r is not None and clip_r > 0.01):
                verdict = "Перегрузка: убавьте gain на Q-12M и повторите."
            elif weak:
                verdict = (
                    "Полезный сигнал слишком слабый. Для Boya проверьте LR44 и Camera. "
                    "Для Maono вход 6.35 мм, вероятно, не даёт plug-in power."
                )
            elif kind == "silence":
                if loudest > -28:
                    verdict = "Тишина шумная: уберите источники или снизьте gain."
                elif loudest < -50:
                    verdict = "Очень тихо: либо отличный шум пола, либо микрофоны без питания."
                else:
                    verdict = "Шум пола записан. Сравните две пары по этому числу."
            elif relative_diff < 0.001 or (corr is not None and corr > 0.9995 and separation < 0.2):
                verdict = "Каналы дублируются: микшер в Mono или USB отдаёт моно-сумму."
            elif kind == "route":
                if swapped:
                    verdict = "Маршрут верный: сначала L, затем R. Микшер разделяет входы."
                elif win1 is not None and win2 is not None and win1 * win2 > 0:
                    verdict = "Доминирующий канал не сменился: микшер смешивает или один вход мёртв."
                else:
                    verdict = "Маршрут неоднозначен. Повторите с лучшей изоляцией."
            elif kind == "mic1" and separation is not None and balance is not None:
                if separation >= 15 and balance > 0:
                    verdict = "Хорошее разделение: вход 1 уверенно в левом канале."
                elif separation >= 6 and balance > 0:
                    verdict = "Разделение слабое, но направление верное (L громче)."
                elif balance < 0:
                    verdict = "Вырос правый канал: перепутаны кабели или Stereo выключен."
                else:
                    verdict = "Разделение слабое. Повторите с изоляцией микрофона 2."
            elif kind == "mic2" and separation is not None and balance is not None:
                if separation >= 15 and balance < 0:
                    verdict = "Хорошее разделение: вход 2 уверенно в правом канале."
                elif separation >= 6 and balance < 0:
                    verdict = "Разделение слабое, но направление верное (R громче)."
                elif balance > 0:
                    verdict = "Вырос левый канал: перепутаны кабели или Stereo выключен."
                else:
                    verdict = "Разделение слабое. Повторите с изоляцией микрофона 1."
            elif separation is not None and separation >= 15:
                verdict = "Каналы хорошо разделены в этом прогоне."
            elif corr is not None and corr > 0.98:
                verdict = "Каналы очень похожи: суммирование или сильный crosstalk."
            else:
                verdict = "Каналы различаются. Для вывода сделайте тесты микрофонов 1 и 2."

        device_index = int(self.current_context["device_index"])
        info = sd.query_devices(device_index)
        host_api = sd.query_hostapis(info["hostapi"])["name"]
        result = TestResult(
            timestamp=timestamp,
            test=f"{test_name} [{mixer_mode} / {mic_power}]",
            kind=kind,
            pair=pair,
            mixer_mode=mixer_mode,
            mic_power=mic_power,
            device=str(info["name"]),
            device_index=device_index,
            output_device=str(self.current_context.get("output_label", "")),
            host_api=str(host_api),
            sample_rate=SAMPLE_RATE,
            channels=audio.shape[1],
            duration_s=len(audio) / SAMPLE_RATE,
            rms_left_dbfs=dbfs(rms_l),
            rms_right_dbfs=rms_r,
            peak_left_dbfs=dbfs(peak_l),
            peak_right_dbfs=peak_r,
            dc_left=dc_l,
            dc_right=dc_r,
            clipping_left_pct=clip_l,
            clipping_right_pct=clip_r,
            correlation_lr=corr,
            difference_dbfs=diff_level,
            balance_db=balance,
            separation_db=separation,
            win1_balance_db=win1,
            win_pause_rms_dbfs=pause_rms,
            win2_balance_db=win2,
            route_swapped=swapped,
            latency_ms=latency_ms,
            verdict=verdict,
            wav_file=str(wav_path),
        )
        with (OUTPUT_DIR / f"{stem}.json").open("w", encoding="utf-8") as file:
            json.dump(asdict(result), file, ensure_ascii=False, indent=2)
        return result

    @staticmethod
    def _route_windows(
        left: np.ndarray, right: np.ndarray
    ) -> tuple[float | None, float | None, float | None, bool | None]:
        n = min(len(left), len(right))
        if n < SAMPLE_RATE * 8:
            return None, None, None, None

        def slice_rms(start_s: float, end_s: float) -> tuple[float, float]:
            start = min(n, max(0, int(start_s * SAMPLE_RATE)))
            end = min(n, max(start + 1, int(end_s * SAMPLE_RATE)))
            l_rms = float(np.sqrt(np.mean(left[start:end] ** 2)))
            r_rms = float(np.sqrt(np.mean(right[start:end] ** 2)))
            return l_rms, r_rms

        a_l, a_r = slice_rms(0.3, 3.8)
        p_l, p_r = slice_rms(4.3, 5.7)
        b_l, b_r = slice_rms(6.5, 11.5)
        win1 = dbfs(a_l) - dbfs(a_r)
        win2 = dbfs(b_l) - dbfs(b_r)
        pause = dbfs(max(p_l, p_r))
        strong_a = max(dbfs(a_l), dbfs(a_r)) >= -38
        strong_b = max(dbfs(b_l), dbfs(b_r)) >= -38
        swapped = bool(strong_a and strong_b and win1 >= 6.0 and win2 <= -6.0)
        return win1, pause, win2, swapped

    @staticmethod
    def _measure_latency(left: np.ndarray, right: np.ndarray | None) -> float | None:
        channel = left
        if right is not None and float(np.max(np.abs(right))) > float(np.max(np.abs(left))):
            channel = right
        start = int(CLICK_OFFSET_S * SAMPLE_RATE)
        if start >= len(channel):
            return None
        tail = np.abs(channel[start:])
        if float(np.max(tail)) < 0.01:
            return None
        peak = int(np.argmax(tail))
        return 1000.0 * peak / SAMPLE_RATE

    def _write_session_files(self) -> None:
        if not self.session_results:
            return
        rows = [asdict(item) for item in self.session_results]
        csv_path = OUTPUT_DIR / "latest_session.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        report = self._build_recommendation()
        (OUTPUT_DIR / "latest_recommendation.txt").write_text(report, encoding="utf-8")

    def _show_result(self, result: TestResult) -> None:
        extra = "—"
        if result.latency_ms is not None:
            extra = f"{result.latency_ms:.1f} мс"
        elif result.win1_balance_db is not None and result.win2_balance_db is not None:
            extra = f"{result.win1_balance_db:+.1f} → {result.win2_balance_db:+.1f}"
        self.tree.insert(
            "",
            tk.END,
            values=(
                result.pair,
                result.test,
                fmt(result.rms_left_dbfs, " dB"),
                fmt(result.rms_right_dbfs, " dB"),
                fmt(result.correlation_lr),
                fmt(result.separation_db, " dB"),
                extra,
                result.verdict,
            ),
        )
        for line in self._pair_summaries():
            signature = line
            if signature not in self.summary_signatures:
                self.summary_signatures.add(signature)
                self.tree.insert("", tk.END, values=("", "ИТОГ пары", "—", "—", "—", "—", "—", line))
        recommendation = self._build_recommendation()
        self.recommend_var.set(recommendation.splitlines()[0])
        self.status_var.set(f"Готово: {result.verdict}")

    def _latest(self, pair: str, kind: str) -> TestResult | None:
        matches = [
            item
            for item in self.session_results
            if item.pair == pair and item.kind == kind and item.mixer_mode == "Stereo"
        ]
        return matches[-1] if matches else None

    def _pair_independence(self, pair: str) -> tuple[str, int]:
        mic1 = self._latest(pair, "mic1")
        mic2 = self._latest(pair, "mic2")
        if mic1 is None or mic2 is None:
            return f"{pair}: нет пары тестов микрофон 1 + 2.", 0
        loud1 = max(mic1.rms_left_dbfs, mic1.rms_right_dbfs or -120.0)
        loud2 = max(mic2.rms_left_dbfs, mic2.rms_right_dbfs or -120.0)
        if loud1 < -40 or loud2 < -40:
            return (
                f"{pair}: сигнал слишком слабый; независимость не подтверждена.",
                0,
            )
        if (
            mic1.separation_db is not None
            and mic2.separation_db is not None
            and mic1.balance_db is not None
            and mic2.balance_db is not None
            and mic1.separation_db >= 15
            and mic2.separation_db >= 15
            and mic1.balance_db * mic2.balance_db < 0
        ):
            return f"{pair}: два независимых канала подтверждены.", 50
        route = self._latest(pair, "route")
        if route is not None and route.route_swapped:
            return f"{pair}: маршрут L→R подтверждён, разделение среднее.", 35
        if (
            mic1.correlation_lr is not None
            and mic2.correlation_lr is not None
            and mic1.correlation_lr > 0.9995
            and mic2.correlation_lr > 0.9995
        ):
            return f"{pair}: каналы дублируются.", 0
        return f"{pair}: результат неоднозначен, повторите с изоляцией.", 10

    def _pair_summaries(self) -> list[str]:
        lines = []
        for pair in PAIRS:
            if self._latest(pair, "mic1") and self._latest(pair, "mic2"):
                lines.append(self._pair_independence(pair)[0])
        return lines

    def _pair_score(self, pair: str) -> tuple[int, str]:
        summary, score = self._pair_independence(pair)
        silence = self._latest(pair, "silence")
        if silence is not None:
            noise = max(silence.rms_left_dbfs, silence.rms_right_dbfs or -120.0)
            if -50 <= noise <= -32:
                score += 10
            elif noise < -50:
                score += 4
        route = self._latest(pair, "route")
        if route is not None and route.route_swapped:
            score += 15
        return score, summary

    def _build_recommendation(self) -> str:
        latency_results = [item for item in self.session_results if item.kind == "latency"]
        mixer_lines = []
        if any(item.channels < 2 for item in self.session_results):
            mixer_lines.append("Микшер виден как 1 канал — для ANC не подходит.")
        pair_ready = {
            pair: self._latest(pair, "mic1") and self._latest(pair, "mic2") for pair in PAIRS
        }
        scores = {pair: self._pair_score(pair) for pair, ready in pair_ready.items() if ready}
        independents = [pair for pair, (score, text) in scores.items() if score >= 50]
        duplicated = [pair for pair, (_score, text) in scores.items() if "дублируются" in text]

        if independents:
            mixer_lines.append("Q-12M в Stereo разделяет входы: микшер для стенда пригоден.")
        elif len(duplicated) == 2:
            mixer_lines.append(
                "Обе пары дают моно-сумму: скорее виноват Q-12M (режим Mono или USB-микс)."
            )
        elif len(duplicated) == 1 and any("слабый" in scores[p][1] for p in scores):
            mixer_lines.append(
                "Одна пара дублируется или молчит: сначала проверьте питание этой пары, "
                "микшер пока не браковать."
            )
        elif scores:
            mixer_lines.append("Маршрут микшера ещё не доказан. Нужны чистые тесты 1 и 2.")
        else:
            mixer_lines.append("Сделайте тесты микрофонов 1 и 2 хотя бы для одной пары.")

        if latency_results and latency_results[-1].latency_ms is not None:
            ms = latency_results[-1].latency_ms
            mixer_lines.append(f"Измеренная задержка USB round-trip: {ms:.1f} мс.")

        if len(scores) == 2:
            ranked = sorted(scores.items(), key=lambda item: item[1][0], reverse=True)
            best, (best_score, best_text) = ranked[0]
            other, (other_score, other_text) = ranked[1]
            if best_score == 0 and other_score == 0:
                keep = "Ни одну пару пока не оставлять: обе не дали независимых каналов."
            elif best_score >= other_score + 10:
                keep = f"Оставить {best}. {best_text} Вторую пару можно возвращать."
            else:
                keep = (
                    f"Пока ничья ({best} {best_score} / {other} {other_score}). "
                    f"{best_text} {other_text}"
                )
        elif len(scores) == 1:
            pair = next(iter(scores))
            keep = f"Пока проверена только {pair}. Подключите вторую пару и повторите тесты 1 и 2."
        else:
            keep = "Рекомендация появится после тестов «Микрофон 1» и «Микрофон 2»."

        return " ".join([keep] + mixer_lines)

    def _on_close(self) -> None:
        if self.running:
            self.stop_test()
        self.root.after(100, self.root.destroy)


def main() -> None:
    root = tk.Tk()
    HardwareCompareApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
