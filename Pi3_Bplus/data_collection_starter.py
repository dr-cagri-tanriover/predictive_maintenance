import json
import os
import csv
import random
import copy

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
    filepath = os.path.join(_DIR, "dataset", "manifests", "all_runs_init.csv")
    
    with open(filepath, "r", encoding="utf-8") as f:
        listDicts = list(csv.DictReader(f))

    return listDicts


def get_waveform_and_brake_sequence_details(runDict: dict) -> dict:
    
    waveDict = read_waveform_definitions(_DIR)
    brakeDict = read_brake_definitions(_DIR)
    
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

        runDict['(duty, duration)'].append((duty, duration))

    # Process the brake details next
    brake_mode = runDict['brake_id'].split('-')[0]  # string
    brake_idx = runDict['brake_id'].split('-')[1]  # string

    brake_dict = brakeDict[runDict['wave_group']][runDict['wave_id']][brake_mode][brake_idx]['sequence']
    for brakeKey in brake_dict.keys():
        durMin, durMax = brake_dict[brakeKey]['timeSec'][0], brake_dict[brakeKey]['timeSec'][1]
        duration = random.randint(durMin, durMax)  # inclusive of the boundaries
        level = int(brake_dict[brakeKey]['level'][-1]) # extract the integer digit of the level string
        runDict['(level, duration)'].append((level, duration))

    return runDict  # modified dictionary is returned


def run_data_collection():

    random.seed(_RANDOM_SEED)  # initialize known random seed for reproducibility

    ########### SET USER DEFINED PARAMETERS BELOW ###########
    # User defined parameters for the data collection
    run_id_range = (1, 169)  # inclusive range of run ids. Zero is invalid!
    session_id = 1  # make sure there is a matching session file under sessions folder
    operator_notes = f"This is a test run for session {session_id:04d}"  # Update note as needed before execution.
    pwm_freq_hz = 1000
    sample_rate_hz = 200
    firmware_version = "1.0.0"  # github tag can be used here.


    #######################################
    metadata_dict = {
        "run_id": None,
        "session_id": None,
        "operator_notes": None,
        "pwm_freq_hz": None,
        "sample_rate_hz": None,
        "firmware_version": None,
        "run_duration_sec": None,
        "wave_group": None,
        "wave_id": None,
        "(duty, duration)": [],
        "brake_id": None,
        "(level, duration)": [],
    }

    # Generate the metadata file for each run
    start_run_id, end_run_id = run_id_range[0], run_id_range[1]
    
    metadata_folder = os.path.join(_DIR, "dataset", "metadata")
    if not os.path.exists(metadata_folder):
        os.makedirs(metadata_folder)

    for run_id in range(start_run_id, end_run_id + 1):

        run_id_str = f"{run_id:04d}"
        metadata_filename = f"run_{run_id_str}_metadata.json"
        metadata_filepath = os.path.join(metadata_folder, metadata_filename)
        
        if os.path.exists(metadata_filepath):
            # Extract data collection information from existing metadata file
            print(f"Metadata file already exists for run {run_id_str}.")
            print(f"Re-running the data collection...")
            print(f"Metadata file will be overwritten with the new data collection...")
        
        else:
            # Create a new metadata file and run the corresponding data collection
            runsListDicts = read_all_runs_init_csv_file()  # list of dictionaries returned
            matches = [lst for lst in runsListDicts if lst.get("run_id") == run_id_str]
            
            assert len(matches) == 1, f"Multiple or no atches found for run_id: {run_id_str}"
            runDict = matches[0]  # includes dataset details for target run_id

            run_meta_dict = copy.deepcopy(metadata_dict) # initialize with defaults #metadata_dict.deepcopy()
            run_meta_dict["run_id"] = runDict.get("run_id")
            run_meta_dict["session_id"] = f"{session_id:04d}"
            run_meta_dict["operator_notes"] = operator_notes
            run_meta_dict["pwm_freq_hz"] = pwm_freq_hz
            run_meta_dict["sample_rate_hz"] = sample_rate_hz
            run_meta_dict["firmware_version"] = firmware_version
            run_meta_dict["wave_group"] = runDict.get("wave_group")
            run_meta_dict["wave_id"] = runDict.get("wave_id") 
            run_meta_dict["brake_id"] = runDict.get("brake_id")

            # Waveform and brake sequence details will be populated nest
            run_meta_dict = get_waveform_and_brake_sequence_details(run_meta_dict)

            # THIS IS THE POINT WHERE Pi Zero and Pi Pico will be prompted with the run
            # metadata required to run the data collection.
            # Other async tasks will buffer incoming data from Pi Zero and 
            # Pi Pico, and 

            run_meta_dict["run_duration_sec"] = "TBD"  # Will be populated based on Pi Zero timer.

            # Write the metadata dictionary to a file
            with open(metadata_filepath, "w", encoding="utf-8") as f:
                json.dump(run_meta_dict, f, indent=4)

def generate_all_runs_csv_file():
    filepath = os.path.join(_DIR, "dataset", "manifests", "all_runs.csv")


if __name__ == "__main__":
    
    run_data_collection()
