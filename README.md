# FxLMS ANC Lab

Research lab for **active noise control** prototypes: offline FxLMS simulation, secondary-path IR measurement, and realtime experiments on Windows (WASAPI).

> Author: Gleb Voronkov · **Non-commercial research license** · Honest status: **research prototype**, not a shipping consumer product.

## Why it matters
Speaker-mode ANC is physically constrained by latency and the λ/10 quiet zone. This repo documents measured secondary-path delay on a laptop bench (**~43.7 ms @ 48 kHz** in one IR capture), correct FxLMS structure notes, and measurement protocols — the kind of engineering that prevents false “AI magic” claims.

## Layout
- `python_proto/` — FxLMS sim, IR measurement, realtime experiments
- `docs/` — project audit, auditory science notes, hardware protocols
- `cpp_rt/` — C++/Eigen realtime stub (scaffold)

## Quickstart (simulation)
```powershell
cd python_proto
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src/fxlms_sim.py
```

See `docs/PROJECT_AUDIT.md` and `docs/RESEARCH_AUDITORY_SCIENCE.md` before expecting realtime cancellation.

## License & commercial use
Non-Commercial Research License (`LICENSE`). Commercial / product licensing: `mybook3@mail.ru` / `@Gleb_Voronkov`.

## Disclaimer
Do not claim medical benefits or “room silence” from a phone speaker. Realistic near-term speaker ANC targets low-frequency drone near the device, often combined with masking.