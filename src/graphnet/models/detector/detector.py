"""Base detector-specific `Model` class(es)."""

from abc import abstractmethod
from typing import Dict, Callable, List

from torch_geometric.data import Data
import torch
import pandas as pd

from graphnet.models import Model
from graphnet.utilities.decorators import final


class Detector(Model):
    """Base class for all detector-specific read-ins in graphnet."""

    def __init__(self) -> None:
        """Construct `Detector`."""
        # Base class constructor
        super().__init__(name=__name__, class_name=self.__class__.__name__)

    @property
    def geometry_table(self) -> pd.DataFrame:
        """Public get method for retrieving a `Detector`s geometry table."""
        if ~hasattr(self, "_geometry_table"):
            try:
                assert hasattr(self, "geometry_table_path")
            except AssertionError as e:
                self.error(
                    f"""{self.__class__.__name__} does not have class
                           variable `geometry_table_path` set."""
                )
                raise e
            self._geometry_table = pd.read_parquet(self.geometry_table_path)
        return self._geometry_table

    @abstractmethod
    def feature_map(self) -> Dict[str, Callable]:
        """List of features used/assumed by inheriting `Detector` objects."""

    @final
    def forward(  # type: ignore
        self, node_features: torch.tensor, node_feature_names: List[str]
    ) -> Data:
        """Pre-process graph `Data` features and build graph adjacency."""
        return self._standardize(node_features, node_feature_names)

    @final
    def _standardize(
        self, node_features: torch.tensor, node_feature_names: List[str]
    ) -> Data:
        for idx, feature in enumerate(node_feature_names):
            try:
                node_features[:, idx] = self.feature_map()[feature](  # type: ignore
                    node_features[:, idx]
                )
            except KeyError as e:
                self.warning(
                    f"""No Standardization function found for '{feature}'"""
                )
                raise e
        return node_features

    def _identity(self, x: torch.tensor) -> torch.tensor:
        """Apply no standardization to input."""
        return x
