import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))

_REPO_ROOT = os.path.dirname(_DIR)  # parent of Pi3_Bplus
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_METADATA_FOLDER = os.path.join(_DIR, "dataset", "metadata")
if not os.path.exists(_METADATA_FOLDER):
    assert False, f"Metadata folder does not exist: {_METADATA_FOLDER}"

#import utilities.file_access as ufa


def run_data_collection():

    ########### SET USER DEFINED PARAMETERS BELOW ###########
    # User defined parameters for the data collection
    run_id_range = (1, 170)  # inclusive range of run ids. Zero is invalid!

    # Generate the metadata file for each run
    start_run_id, end_run_id = run_id_range[0], run_id_range[1]
    
    # metadata_folder = os.path.join(_DIR, "dataset", "metadata")
    # if not os.path.exists(metadata_folder):
    #     assert False, f"Metadata folder does not exist: {metadata_folder}"

    for run_id in range(start_run_id, end_run_id + 1):

        run_id_str = f"{run_id:04d}"
        metadata_filename = f"run_{run_id_str}_metadata.json"
        metadata_filepath = os.path.join(_METADATA_FOLDER, metadata_filename)
        
        if not os.path.exists(metadata_filepath):
            assert False, f"Metadata file does not exist: {metadata_filepath}"

        with open(metadata_filepath, "r", encoding="utf-8") as f:
            run_meta_dict = json.load(f)  # read the data from the metadata json file

        # THIS IS THE POINT WHERE Pi Zero and Pi Pico will be prompted with the run
        # metadata required to run the data collection.
        # Other async tasks will buffer incoming data from Pi Zero and 
        # Pi Pico, and 

        run_meta_dict["run_duration_sec_actual"] = "TESTING"  # Will be populated based on Pi Zero timer.

        # Update the metadata file to reflect the collected data.
        with open(metadata_filepath, "w", encoding="utf-8") as f:
            json.dump(run_meta_dict, f, indent=4)

def get_minMax_runs() -> tuple[int, int]:
    # Following places all files in _METADATA_FOLDER into a list and returns the min and max run IDs.
    # Expected file format: run_{run_id_str}_metadata.json
    metadata_files = os.listdir(_METADATA_FOLDER)

    if len(metadata_files) == 0:
        return (0, 0)

    min_run_id = min(int(file.split("_")[1]) for file in metadata_files if file.startswith("run_"))
    max_run_id = max(int(file.split("_")[1]) for file in metadata_files if file.startswith("run_"))
    return (min_run_id, max_run_id)


def get_run_metadata(run_id: int) -> dict:
    
    run_id_str = f"{run_id:04d}"

    metadata_filename = f"run_{run_id_str}_metadata.json"
    metadata_filepath = os.path.join(_METADATA_FOLDER, metadata_filename)
    
    if not os.path.exists(metadata_filepath):
        print(f"Metadata file does not exist: {metadata_filepath}")
        return {}  # empty dictionary returned if file does not exist
    
    with open(metadata_filepath, "r", encoding="utf-8") as f:
        run_meta_dict = json.load(f)

    return run_meta_dict


if __name__ == "__main__":
    
    run_data_collection()
