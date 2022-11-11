import pandas as pd
import numpy as np


def convert_f2k_to_geometry_table(custom_f2k: str, source: str = "prometheus"):
    """Converts f2k files from simulation engines to graphnet compliant geometry tables. Other, future sources must comply with naming convention of the xyz of the sensors.

    Args:
        custom_f2k (str): path to f2k file
        outdir (str): the directory to which the file is saved_any
        source (str, optional): the source of the f2k file. Defaults to 'prometheus'.
    """
    if source == "prometheus":
        geometry_table = pd.read_csv(
            custom_f2k, sep="\t", lineterminator="\n", header=None
        )
        geometry_table.columns = [
            "hash_1",
            "hash_1",
            "sensor_x",
            "sensor_y",
            "sensor_z",
            "string_idx",
            "pmt_idx",
        ]

    if source == "prometheus_v2":
        geometry_table = pd.read_csv(custom_f2k).drop(columns=["Unnamed: 0"])
        print(geometry_table.columns)
        geometry_table.columns = [
            "pmt_idx",
            "sensor_x",
            "sensor_y",
            "sensor_z",
            "string_idx",
        ]

    return geometry_table
