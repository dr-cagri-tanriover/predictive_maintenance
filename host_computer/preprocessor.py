import json
import os
import pandas as pd
import sys
import random
import copy

_DIR = os.path.dirname(os.path.abspath(__file__))
_RANDOM_SEED = 1974


_REPO_ROOT = os.path.dirname(_DIR)  # parent of host_computer
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import utilities.file_access as ufa

def generate_all_runs_init_csv_file():
    parent_folder = os.path.dirname(_DIR)  # one folder above this script file

    dataset_folder = os.path.join(parent_folder, "Pi3_Bplus", "dataset")
    manifests_folder = os.path.join(dataset_folder, "manifests")
    
    if not os.path.exists(manifests_folder):
        os.makedirs(manifests_folder)

    out_filepath = os.path.join(manifests_folder, "all_runs_init.csv")

    in_waveform_folder = os.path.join(parent_folder, "common")
    in_brake_folder = os.path.join(parent_folder, "common")

    waveforms_dict = ufa.read_waveform_definitions(in_waveform_folder)
    brake_dict = ufa.read_brake_definitions(in_brake_folder)

    # all_runs.csv header columns
    columns = ["run_id", "wave_group", "wave_id", "brake_id"]

    df = pd.DataFrame(columns=columns)

    cur_run_id = 1

    # IMPORTANT: The following assumes the waveform group and wave id are the same in both waveform and brake definitions !!
    for wave_group in waveforms_dict.keys():
        for wave_id in waveforms_dict[wave_group].keys():
            for brake_mode in brake_dict[wave_group][wave_id].keys():
                #"Fail" or "No_Fail"
                for brake_pattern in brake_dict[wave_group][wave_id][brake_mode].keys():
                    #"0, 1, 2, 3, 4" as pattern idx of Fail or No Fail
                    num_repeats = brake_dict[wave_group][wave_id][brake_mode][brake_pattern]["repeat"]  # number of times the pattern needs to be repeated
                    
                    for _ in range(num_repeats):
                        # SAME BRAKE ACTION needs to be repeated in separate runs
                        # as per json file definition.
                        brake_id = f"{brake_mode}-{brake_pattern}"
                        df.loc[len(df)] = [f"{cur_run_id:04d}", wave_group, wave_id, brake_id]
                        cur_run_id += 1

    # Write full run recipe to csv
    df.to_csv(out_filepath, index=False)


def initialize_all_run_medatdata_json_files():

    random.seed(_RANDOM_SEED)  # initialize known random seed for reproducibility

    ########### SET USER DEFINED PARAMETERS BELOW ###########
    # User defined parameters for the data collection
    run_id_range = (1, 170)  # inclusive range of run ids. Zero is invalid!
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
        "run_duration_sec_requested": None,
        "run_duration_sec_actual": None,
        "wave_group": None,
        "wave_id": None,
        "(duty, duration)": [],
        "brake_id": None,
        "(level, duration)": [],
    }

    # Generate the metadata file for each run
    start_run_id, end_run_id = run_id_range[0], run_id_range[1]
    
    parent_folder = os.path.dirname(_DIR)  # one folder above host_computer

    metadata_folder = os.path.join(parent_folder, "Pi3_Bplus", "dataset", "metadata")
    if not os.path.exists(metadata_folder):
        os.makedirs(metadata_folder)

    for run_id in range(start_run_id, end_run_id + 1):

        run_id_str = f"{run_id:04d}"
        metadata_filename = f"run_{run_id_str}_metadata.json"
        metadata_filepath = os.path.join(metadata_folder, metadata_filename)
        
        if os.path.exists(metadata_filepath):
            # Overwrite notification to the user
            print(f"Metadata file already exists for run {run_id_str}.")
            print(f"Metadata file will be overwritten with the new data collection...")
               
        # Create a new metadata file and run the corresponding data collection
        runsListDicts = ufa.read_all_runs_init_csv_file()  # list of dictionaries returned
        matches = [lst for lst in runsListDicts if lst.get("run_id") == run_id_str]
        
        assert len(matches) == 1, f"Multiple or no matches found for run_id: {run_id_str}"
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
        run_meta_dict = ufa.get_waveform_and_brake_sequence_details(run_meta_dict)

        run_meta_dict["run_duration_sec_actual"] = "TBD"  # Will be populated based on Pi Zero timer.

        # Write the metadata dictionary to a file
        with open(metadata_filepath, "w", encoding="utf-8") as f:
            json.dump(run_meta_dict, f, indent=4)

if __name__ == "__main__":
    
    #generate_all_runs_init_csv_file()  # STEP 1: Generate the all_runs_init.csv file
    initialize_all_run_medatdata_json_files()  # STEP 2: Generate the all_run_medatdata.json files using all_runs_init.csv
