from abc import ABC, abstractmethod
from typing import List

try:
    from icecube import dataclasses, icetray, dataio  # pyright: reportMissingImports=false
except ImportError:
    print("icecube package not available.")

from abc import abstractmethod
from .utils import frame_has_key


class I3Extractor(ABC):
    """Extracts relevant information from physics frames."""

    def __init__(self, name):

        # Member variables
        self._i3_file = None
        self._gcd_file = None
        self._gcd_dict = None
        self._calibration = None
        self._name = name

    def set_files(self, i3_file, gcd_file):
        # @TODO: Is it necessary to set the `i3_file`? It is only used in one
        #        place in `I3TruthExtractor`, and there only in a way that might
        #        be solved another way.
        self._i3_file = i3_file
        self._gcd_file = gcd_file
        self._load_gcd_data()

    def _load_gcd_data(self):
        """Loads the geospatial information contained in the gcd-file."""
        gcd_file = dataio.I3File(self._gcd_file)
        g_frame = gcd_file.pop_frame(icetray.I3Frame.Geometry)
        c_frame = gcd_file.pop_frame(icetray.I3Frame.Calibration)
        self._gcd_dict = g_frame["I3Geometry"].omgeo
        self._calibration = c_frame["I3Calibration"]

    @abstractmethod
    def __call__(self, frame) -> dict:
        """Extracts relevant information from frame."""
        pass

    @property
    def name(self) -> str:
        return self._name


class I3ExtractorCollection(list):
    """Class to manage multiple I3Extractors."""
    def __init__(self, *extractors):
        # Check(s)
        for extractor in extractors:
            assert isinstance(extractor, I3Extractor)

        # Base class constructor
        super().__init__(extractors)

    def set_files(self, i3_file, gcd_file):
        for extractor in self:
            extractor.set_files(i3_file, gcd_file)

    def __call__(self, frame) -> List[dict]:
        return [extractor(frame) for extractor in self]


class I3FeatureExtractor(I3Extractor):
    def __init__(self, pulsemap):
        self._pulsemap = pulsemap
        super().__init__(pulsemap)

    def _get_om_keys_and_pulseseries(self, frame):
        """Gets the indicies for the gcd_dict and the pulse series

        Args:
            frame (i3 physics frame): i3 physics frame

        Returns:
            om_keys (index): the indicies for the gcd_dict
            data    (??)   : the pulse series
        """
        data = frame[self._pulsemap]
        try:
            om_keys = data.keys()
        except:
            try:
                if "I3Calibration" in frame.keys():
                    data = frame[self._pulsemap].apply(frame)
                    om_keys = data.keys()
                else:
                    frame["I3Calibration"] = self._calibration
                    data = frame[self._pulsemap].apply(frame)
                    om_keys = data.keys()
                    #del frame["I3Calibration"]  # Avoid modifying the frame in-place
            except:
                data = dataclasses.I3RecoPulseSeriesMap.from_frame(frame, self._pulsemap)
                om_keys = data.keys()
        return om_keys, data

class I3FeatureExtractorIceCube86(I3FeatureExtractor):

    def __call__(self, frame) -> dict:
        """Extract features to be used as inputs to GNN models."""

        output = {
            'charge': [],
            'dom_time': [],
            'dom_x': [],
            'dom_y': [],
            'dom_z': [],
            'width' : [],
            'pmt_area': [],
            'rde': [],
        }

        try:
            om_keys, data = self._get_om_keys_and_pulseseries(frame)
        except KeyError:
            print(f"WARN: Pulsemap {self._pulsemap} was not found in frame.")
            return output

        for om_key in om_keys:
            # Common values for each OM
            x = self._gcd_dict[om_key].position.x
            y = self._gcd_dict[om_key].position.y
            z = self._gcd_dict[om_key].position.z
            area = self._gcd_dict[om_key].area
            if "I3Calibration" in frame:  # Not available for e.g. mDOMs in IceCube Upgrade
                rde = frame["I3Calibration"].dom_cal[om_key].relative_dom_eff
            else:
                rde = -1.

            # Loop over pulses for each OM
            pulses = data[om_key]
            for pulse in pulses:
                output['charge'].append(pulse.charge)
                output['dom_time'].append(pulse.time)
                output['width'].append(pulse.width)
                output['pmt_area'].append(area)
                output['rde'].append(rde)
                output['dom_x'].append(x)
                output['dom_y'].append(y)
                output['dom_z'].append(z)

        return output

class I3FeatureExtractorIceCubeDeepCore(I3FeatureExtractorIceCube86):
    """..."""

class I3FeatureExtractorIceCubeUpgrade(I3FeatureExtractorIceCube86):

    def __call__(self, frame) -> dict:
        """Extract features to be used as inputs to GNN models."""

        output = {
            'string': [],
            'pmt_number': [],
            'dom_number': [],
            'pmt_dir_x': [],
            'pmt_dir_y': [],
            'pmt_dir_z': [],
            'dom_type': [],
        }

        try:
            om_keys, data = self._get_om_keys_and_pulseseries(frame)
        except KeyError:  # Target pulsemap does not exist in `frame`
            return output

        for om_key in om_keys:
            # Common values for each OM
            pmt_dir_x = self._gcd_dict[om_key].orientation.x
            pmt_dir_y = self._gcd_dict[om_key].orientation.y
            pmt_dir_z = self._gcd_dict[om_key].orientation.z
            string = om_key[0]
            dom_number = om_key[1]
            pmt_number = om_key[2]
            dom_type = self._gcd_dict[om_key].omtype

            # Loop over pulses for each OM
            pulses = data[om_key]
            for _ in pulses:
                output['string'].append(string)
                output['pmt_number'].append(pmt_number)
                output['dom_number'].append(dom_number)
                output['pmt_dir_x'].append(pmt_dir_x)
                output['pmt_dir_y'].append(pmt_dir_y)
                output['pmt_dir_z'].append(pmt_dir_z)
                output['dom_type'].append(dom_type)

        # Add features from IceCube86
        output_icecube86 = super().__call__(frame)
        output.update(output_icecube86)
        return output


class I3TruthExtractor(I3Extractor):
    def __init__(self, name="truth"):
        super().__init__(name)

    def __call__(self, frame, padding_value=-1) -> dict:
        """Extracts truth features."""
        is_mc = frame_is_montecarlo(frame)
        is_noise = frame_is_noise(frame)
        sim_type = find_data_type(is_mc, self._i3_file)

        output = {
            'energy': padding_value,
            'position_x': padding_value,
            'position_y': padding_value,
            'position_z': padding_value,
            'interaction_time': padding_value,
            'azimuth': padding_value,
            'zenith': padding_value,
            'pid': padding_value,
            'event_time': frame['I3EventHeader'].start_time.utc_daq_time,
            'sim_type': sim_type,
            'interaction_type': padding_value,
            'elasticity': padding_value,
            'RunID': frame['I3EventHeader'].run_id,
            'SubrunID': frame['I3EventHeader'].sub_run_id,
            'EventID': frame['I3EventHeader'].event_id,
            'SubEventID': frame['I3EventHeader'].sub_event_id,
        }

        if is_mc == True and is_noise == False:
            MCInIcePrimary, interaction_type, elasticity = get_primary_particle_interaction_type_and_elasticity(frame, sim_type)
            output.update({
                'energy': MCInIcePrimary.energy,
                'position_x': MCInIcePrimary.pos.x,
                'position_y': MCInIcePrimary.pos.y,
                'position_z': MCInIcePrimary.pos.z,
                'interaction_time': MCInIcePrimary.time,
                'azimuth': MCInIcePrimary.dir.azimuth,
                'zenith': MCInIcePrimary.dir.zenith,
                'pid': MCInIcePrimary.pdg_encoding,
                'interaction_type': interaction_type,
                'elasticity': elasticity,
            })

        return output


class I3RetroExtractor(I3Extractor):

    def __init__(self, name="retro"):
        super().__init__(name)

    def __call__(self, frame) -> dict:
        """Extracts RETRO reco. and associated quantities if available."""
        output = {}

        if frame_contains_retro(frame):
            output.update({
                'azimuth_retro': frame["L7_reconstructed_azimuth"].value,
                'time_retro': frame["L7_reconstructed_time"].value,
                'energy_retro': frame["L7_reconstructed_total_energy"].value,
                'position_x_retro': frame["L7_reconstructed_vertex_x"].value,
                'position_y_retro': frame["L7_reconstructed_vertex_y"].value,
                'position_z_retro': frame["L7_reconstructed_vertex_z"].value,
                'interaction_time_retro': frame["L7_reconstructed_time"].value,
                'zenith_retro': frame["L7_reconstructed_zenith"].value,
                'azimuth_sigma': frame["L7_retro_crs_prefit__azimuth_sigma_tot"].value,
                'position_x_sigma': frame["L7_retro_crs_prefit__x_sigma_tot"].value,
                'position_y_sigma': frame["L7_retro_crs_prefit__y_sigma_tot"].value,
                'position_z_sigma': frame["L7_retro_crs_prefit__z_sigma_tot"].value,
                'time_sigma': frame["L7_retro_crs_prefit__time_sigma_tot"].value,
                'zenith_sigma': frame["L7_retro_crs_prefit__zenith_sigma_tot"].value,
                'energy_sigma': frame["L7_retro_crs_prefit__energy_sigma_tot"].value,
                'cascade_energy_retro': frame["L7_reconstructed_cascade_energy"].value,
                'track_energy_retro': frame["L7_reconstructed_track_energy"].value,
                'track_length_retro': frame["L7_reconstructed_track_length"].value,
            })

        if frame_contains_classifiers(frame):
            classifiers = ['L7_MuonClassifier_FullSky_ProbNu','L4_MuonClassifier_Data_ProbNu','L4_NoiseClassifier_ProbNu','L7_PIDClassifier_FullSky_ProbTrack']
            for classifier in classifiers:
                if frame_has_key(frame, classifier):
                    output.update({classifier : frame[classifier].value})
            #output.update({
            #    'L7_MuonClassifier_FullSky_ProbNu': frame["L7_MuonClassifier_FullSky_ProbNu"].value,
            #    'L4_MuonClassifier_Data_ProbNu': frame["L4_MuonClassifier_Data_ProbNu"].value,
            #    'L4_NoiseClassifier_ProbNu': frame["L4_NoiseClassifier_ProbNu"].value,
            #    'L7_PIDClassifier_FullSky_ProbTrack': frame["L7_PIDClassifier_FullSky_ProbTrack"].value,
            #})

        if frame_is_montecarlo(frame):
            if frame_contains_retro(frame):
                output.update({
                    'osc_weight': frame["I3MCWeightDict"]["weight"],
                })
            else:
                output.update({
                    'osc_weight': -1.,
                })

        return output


# Utilty methods
def frame_contains_retro(frame):
    return frame_has_key(frame, "L7_reconstructed_zenith")

def frame_contains_classifiers(frame):
    return frame_has_key(frame, "L4_MuonClassifier_Data_ProbNu")

def frame_is_montecarlo(frame):
    return (
        frame_has_key(frame, "MCInIcePrimary") or
        frame_has_key(frame, "I3MCTree")
    )
def frame_is_noise(frame):
    if frame_has_key(frame, "MCInIcePrimary"):
        return False
    else:
        return True

def frame_is_lvl7(frame):
    return frame_has_key(frame, "L7_reconstructed_zenith")



def find_data_type(mc, input_file):
    """Determines the data type

    Args:
        mc (boolean): is this montecarlo?
        input_file (str): path to i3 file

    Returns:
        str: the simulation/data type
    """
    # @TODO: Rewrite to make automaticallu infer `mc` from `input_file`?
    if mc == False:
        sim_type = 'data'
    else:
        sim_type = 'NuGen'
    if 'muon' in input_file:
        sim_type = 'muongun'
    if 'corsika' in input_file:
        sim_type = 'corsika'
    if 'genie' in input_file:
        sim_type = 'genie'
    if 'noise' in input_file:
        sim_type = 'noise'
    if sim_type == 'lol':
        print('SIM TYPE NOT FOUND!')
    return sim_type

def get_primary_particle_interaction_type_and_elasticity(frame, sim_type, padding_value=-1):
    """"Returns primary particle, interaction type, and elasticity.

    A case handler that does two things
        1) Catches issues related to determining the primary MC particle.
        2) Error handles cases where interaction type and elasticity doesnt exist

    Args:
        frame (i3 physics frame): ...
        sim_type (string): Simulation type
        padding_value (int | float): The value used for padding.

    Returns
        McInIcePrimary (?): The primary particle
        interaction_type (int): Either 1 (charged current), 2 (neutral current), 0 (neither)
        elasticity (float): In ]0,1[
    """
    if sim_type != 'noise':
        try:
            MCInIcePrimary = frame['MCInIcePrimary']
        except:
            MCInIcePrimary = frame['I3MCTree'][0]
    else:
        MCInIcePrimary = None

    try:
        interaction_type = frame["I3MCWeightDict"]["InteractionType"]
    except:
        interaction_type = padding_value

    try:
        elasticity = frame['I3GENIEResultDict']['y']
    except:
        elasticity = padding_value

    return MCInIcePrimary, interaction_type, elasticity