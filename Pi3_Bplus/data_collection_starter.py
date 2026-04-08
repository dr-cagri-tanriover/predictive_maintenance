import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))

def generate_all_runs_csv_file():
    filepath = os.path.join(_DIR, "dataset", "manifests", "all_runs.csv")

if __name__ == "__main__":
    
    filepath = os.path.join(_DIR, "waveform_definitions.json")
    with open(filepath, "r", encoding="utf-8") as f:
        waveform_defs = json.load(f)

    filepath = os.path.join(_DIR, "brake_definitions.json")
    with open(filepath, "r", encoding="utf-8") as f:
        brake_defs = json.load(f)

    print(f"Waveform Definitions: {waveform_defs}")
    print(f"Brake Definitions: {brake_defs}")
