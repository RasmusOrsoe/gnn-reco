from graphnet.data.extractors.i3extractor import I3Extractor
from graphnet.utilities.imports import has_icecube_package

if has_icecube_package():
    from icecube import dataclasses  # pyright: reportMissingImports=false


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
        try:
            data = frame[self._pulsemap]
        except KeyError:
            self.logger.error(
                f"Pulsemap {self._pulsemap} does not exist in `frame`"
            )
            raise

        try:
            om_keys = data.keys()
        except:  # noqa: E722
            try:
                if "I3Calibration" in frame.keys():
                    data = frame[self._pulsemap].apply(frame)
                    om_keys = data.keys()
                else:
                    frame["I3Calibration"] = self._calibration
                    data = frame[self._pulsemap].apply(frame)
                    om_keys = data.keys()
                    del frame[
                        "I3Calibration"
                    ]  # Avoid adding unneccesary data to frame
            except:  # noqa: E722
                data = dataclasses.I3RecoPulseSeriesMap.from_frame(
                    frame, self._pulsemap
                )
                om_keys = data.keys()
        return om_keys, data


class I3FeatureExtractorIceCube86(I3FeatureExtractor):
    def __call__(self, frame) -> dict:
        """Extract features to be used as inputs to GNN models."""
        output = {
            "charge": [],
            "dom_time": [],
            "dom_x": [],
            "dom_y": [],
            "dom_z": [],
            "width": [],
            "pmt_area": [],
            "rde": [],
            "is_bright_dom": [],
            "is_bad_dom": [],
            "is_saturated_dom": [],
            "is_errata_dom": [],
        }

        om_keys, data = self._get_om_keys_and_pulseseries(frame)

        # Added these:
        bright_doms = None
        bad_doms = None
        saturation_windows = None
        calibration_errata = None
        if "BrightDOMs" in frame:
            bright_doms = frame.Get("BrightDOMs")

        if "BadDomsList" in frame:
            bad_doms = frame.Get("BadDomsList")

        if "SaturationWindows" in frame:
            saturation_windows = frame.Get("SaturationWindows")

        if "CalibrationErrata" in frame:
            calibration_errata = frame.Get("CalibrationErrata")

        for om_key in om_keys:
            # Common values for each OM
            x = self._gcd_dict[om_key].position.x
            y = self._gcd_dict[om_key].position.y
            z = self._gcd_dict[om_key].position.z
            area = self._gcd_dict[om_key].area
            rde = self._get_relative_dom_efficiency(frame, om_key)

            if bright_doms:
                if om_key in bright_doms:
                    is_bright_dom = 1
                else:
                    is_bright_dom = 0
            else:
                is_bright_dom = -1
            if bad_doms:
                if om_key in bad_doms:
                    is_bad_dom = 1
                else:
                    is_bad_dom = 0
            else:
                is_bad_dom = -1
            if saturation_windows:
                if om_key in saturation_windows:
                    is_saturated_dom = 1
                else:
                    is_saturated_dom = 0
            else:
                is_saturated_dom = -1

            if calibration_errata:
                if om_key in calibration_errata:
                    is_errata_dom = 1
                else:
                    is_errata_dom = 0
            else:
                is_errata_dom = -1

            # Loop over pulses for each OM
            pulses = data[om_key]
            for pulse in pulses:
                output["charge"].append(pulse.charge)
                output["dom_time"].append(pulse.time)
                output["width"].append(pulse.width)
                output["pmt_area"].append(area)
                output["rde"].append(rde)
                output["dom_x"].append(x)
                output["dom_y"].append(y)
                output["dom_z"].append(z)
                # New
                output["is_bright_dom"].append(
                    is_bright_dom
                )  # 0 or 1 or padding_value if list is not in file
                output["is_bad_dom"].append(
                    is_bad_dom
                )  # 0 or 1 or padding_value if list is not in file
                output["is_saturated_dom"].append(
                    is_saturated_dom
                )  # 0 or 1 or padding_value if list is not in file
                output["is_errata_dom"].append(
                    is_errata_dom
                )  # 0 or 1 or padding_value if list is not in file
        return output

    def _get_relative_dom_efficiency(self, frame, om_key):
        if (
            "I3Calibration" in frame
        ):  # Not available for e.g. mDOMs in IceCube Upgrade
            rde = frame["I3Calibration"].dom_cal[om_key].relative_dom_eff
        else:
            try:
                rde = self._calibration.dom_cal[om_key].relative_dom_eff
            except:  # noqa: E722
                rde = -1
        return rde


class I3FeatureExtractorIceCubeDeepCore(I3FeatureExtractorIceCube86):
    """..."""


class I3FeatureExtractorIceCubeUpgrade(I3FeatureExtractorIceCube86):
    def __call__(self, frame) -> dict:
        """Extract features to be used as inputs to GNN models."""

        output = {
            "string": [],
            "pmt_number": [],
            "dom_number": [],
            "pmt_dir_x": [],
            "pmt_dir_y": [],
            "pmt_dir_z": [],
            "dom_type": [],
        }

        # Add features from IceCube86
        output_icecube86 = super().__call__(frame)
        output.update(output_icecube86)

        # Get OM data
        om_keys, data = self._get_om_keys_and_pulseseries(frame)

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
                output["string"].append(string)
                output["pmt_number"].append(pmt_number)
                output["dom_number"].append(dom_number)
                output["pmt_dir_x"].append(pmt_dir_x)
                output["pmt_dir_y"].append(pmt_dir_y)
                output["pmt_dir_z"].append(pmt_dir_z)
                output["dom_type"].append(dom_type)

        return output


class I3PulseNoiseTruthFlagIceCubeUpgrade(I3FeatureExtractorIceCube86):
    def __call__(self, frame) -> dict:
        """Extract features to be used as inputs to GNN models."""

        output = {
            "string": [],
            "pmt_number": [],
            "dom_number": [],
            "pmt_dir_x": [],
            "pmt_dir_y": [],
            "pmt_dir_z": [],
            "dom_type": [],
            "truth_flag": [],
        }

        # Add features from IceCube86
        output_icecube86 = super().__call__(frame)
        output.update(output_icecube86)

        # Get OM data
        om_keys, data = self._get_om_keys_and_pulseseries(frame)

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
            for truth_flag in pulses:
                output["string"].append(string)
                output["pmt_number"].append(pmt_number)
                output["dom_number"].append(dom_number)
                output["pmt_dir_x"].append(pmt_dir_x)
                output["pmt_dir_y"].append(pmt_dir_y)
                output["pmt_dir_z"].append(pmt_dir_z)
                output["dom_type"].append(dom_type)
                output["truth_flag"].append(truth_flag)

        return output