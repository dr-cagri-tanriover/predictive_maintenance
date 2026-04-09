import json
import os
import csv
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))

_REPO_ROOT = os.path.dirname(_DIR)  # parent of Pi3_Bplus
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from host_computer.preprocessor import read_brake_definitions, read_waveform_definitions


def read_all_runs_init_csv_file():
    filepath = os.path.join(_DIR, "dataset", "manifests", "all_runs_init.csv")
    
    with open(filepath, "r", encoding="utf-8") as f:
        listDicts = list(csv.DictReader(f))

    return listDicts


def get_waveform_and_brake_sequence_details(runDict: dict) -> dict:
    
    waveform_defs = read_waveform_definitions(_DIR)
    brake_defs = read_brake_definitions(_DIR)
    
   
    return runDict  # modified dictionary is returned


def run_data_collection():

    ########### SET USER DEFINED PARAMETERS BELOW ###########
    # User defined parameters for the data collection
    run_id_range = (1, 10)  # inclusive range of run ids. Zero is invalid!
    session_id = 1  # make sure there is a matching session file under sessions folder
    operator_notes = f"This is a test run for session {session_id}"  # Update note as needed before execution.
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
    # Check if a metadata file already exists for a run.
    # If a metdata file already exists, the data collection needs to be
    # repeated using the same information in that metadata file.
    # Else, create a new metadata file and run the corresponding data collection
    # for the firs time.

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
            pass
        else:
            # Create a new metadata file and run the corresponding data collection
            runsListDicts = read_all_runs_init_csv_file()  # list of dictionaries returned
            matches = [lst for lst in runsListDicts if lst.get("run_id") == run_id_str]
            
            assert len(matches) == 1, f"Multiple or no atches found for run_id: {run_id_str}"
            runDict = matches[0]  # includes dataset details for target run_id

            run_dict = metadata_dict.copy()
            run_dict["run_id"] = runDict.get("run_id")
            run_dict["session_id"] = f"session_{session_id:04d}"
            run_dict["operator_notes"] = operator_notes
            run_dict["pwm_freq_hz"] = pwm_freq_hz
            run_dict["sample_rate_hz"] = sample_rate_hz
            run_dict["firmware_version"] = firmware_version
            run_dict["wave_group"] = runDict.get("wave_group")
            run_dict["wave_id"] = runDict.get("wave_id") 
            run_dict["brake_id"] = runDict.get("brake_id")

            # Waveform and brake sequence details will be populated nest
            run_dict = get_waveform_and_brake_sequence_details(runDict)
            #run_dict["(duty, duration)"] = 
            #run_dict["(level, duration)"] = 


            run_dict["run_duration_sec"] = "TBD"  # Will be populated based on Pi Zero timer.

def generate_all_runs_csv_file():
    filepath = os.path.join(_DIR, "dataset", "manifests", "all_runs.csv")


if __name__ == "__main__":
    
    run_data_collection()
