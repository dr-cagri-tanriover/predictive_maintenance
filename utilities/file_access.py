import json
import os
import csv

_DIR = os.path.dirname(os.path.abspath(__file__))
_RANDOM_SEED = 1974

def read_waveform_definitions(source_folder: str) -> dict:
    in_waveform_filepath = os.path.join(source_folder, "waveform_definitions.json")

    with open(in_waveform_filepath, "r", encoding="utf-8") as f:
        waveforms_dict = json.load(f) 

    return waveforms_dict


def read_brake_definitions(source_folder: str) -> dict:
    in_brake_filepath = os.path.join(source_folder, "brake_definitions.json")

    with open(in_brake_filepath, "r", encoding="utf-8") as f:
        brake_dict = json.load(f)

    return brake_dict


def read_all_runs_init_csv_file():

    parent_folder = os.path.dirname(_DIR)  # one folder above this script file
    filepath = os.path.join(parent_folder, "Pi3_Bplus", "dataset", "manifests", "all_runs_init.csv")
    
    with open(filepath, "r", encoding="utf-8") as f:
        listDicts = list(csv.DictReader(f))

    return listDicts