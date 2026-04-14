import json
import os
import csv
import random

_DIR = os.path.dirname(os.path.abspath(__file__))


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


def get_waveform_and_brake_sequence_details(runDict: dict) -> dict:
    
    parent_folder = os.path.dirname(_DIR)  # one folder above this script file

    waveDict = read_waveform_definitions(os.path.join(parent_folder, "common"))
    brakeDict = read_brake_definitions(os.path.join(parent_folder, "common"))
    
    # Process waveform details first
    wave_dict = waveDict[runDict['wave_group']][runDict['wave_id']]
    for waveKey in wave_dict.keys():
        
        if len(wave_dict[waveKey]['timeSec']) == 0:
            # waveform duration is not specified. It will run indefinitely until stopped.
            duration = 0
        elif len(wave_dict[waveKey]['timeSec']) == 1:
            # a fixed duration is specified
            duration = wave_dict[waveKey]['timeSec'][0]
        elif len(wave_dict[waveKey]['timeSec']) == 2:
            # a minimum and maximum duration is specified
            durMin, durMax = wave_dict[waveKey]['timeSec'][0], wave_dict[waveKey]['timeSec'][1]
            duration = random.randint(durMin, durMax)  # inclusive of the boundaries
        else:
            # Unexpected error!
            raise ValueError(f"Invalid number of duration values for waveform {waveKey}: {len(wave_dict[waveKey]['timeSec'])}")
            duration = -1 # unexpected error!

        # Update the run dictionary with the waveform details
        duty = wave_dict[waveKey]['duty']

        runDict['(duty, duration)'].append([duty, duration])

    # Process the brake details next
    brake_mode = runDict['brake_id'].split('-')[0]  # string
    brake_idx = runDict['brake_id'].split('-')[1]  # string

    runDict['run_duration_sec_requested'] = 0  # will be accumulated in the for loop with random time picks
    brake_dict = brakeDict[runDict['wave_group']][runDict['wave_id']][brake_mode][brake_idx]['sequence']
    for brakeKey in brake_dict.keys():
        durMin, durMax = brake_dict[brakeKey]['timeSec'][0], brake_dict[brakeKey]['timeSec'][1]
        duration = random.randint(durMin, durMax)  # inclusive of the boundaries
        level = int(brake_dict[brakeKey]['level'][-1]) # extract the integer digit of the level string
        runDict['(level, duration)'].append([level, duration])
        runDict['run_duration_sec_requested'] += duration  # accumulated duration of the run

    return runDict  # modified dictionary is returned