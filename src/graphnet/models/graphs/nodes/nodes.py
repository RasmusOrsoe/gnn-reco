"""Class(es) for building/connecting graphs."""

from typing import List, Tuple, Optional
from abc import abstractmethod

import torch
from torch_geometric.data import Data

from graphnet.utilities.decorators import final
from graphnet.models import Model
from graphnet.models.graphs.utils import (
    cluster_summarize_with_percentiles,
    identify_indices,
    ice_transparency,
)
from copy import deepcopy


class NodeDefinition(Model):  # pylint: disable=too-few-public-methods
    """Base class for graph building."""

    def __init__(
        self, input_feature_names: Optional[List[str]] = None
    ) -> None:
        """Construct `Detector`."""
        # Base class constructor
        super().__init__(name=__name__, class_name=self.__class__.__name__)
        if input_feature_names is not None:
            self.set_output_feature_names(
                input_feature_names=input_feature_names
            )

    @final
    def forward(self, x: torch.tensor) -> Tuple[Data, List[str]]:
        """Construct nodes from raw node features.

        Args:
            x: standardized node features with shape ´[num_pulses, d]´,
            where ´d´ is the number of node features.
            node_feature_names: list of names for each column in ´x´.

        Returns:
            graph: a graph without edges
            new_features_name: List of new feature names.
        """
        graph = self._construct_nodes(x=x)
        try:
            self._output_feature_names
        except AttributeError as e:
            self.error(
                f"""{self.__class__.__name__} was instantiated without
                       `input_feature_names` and it was not set prior to this
                       forward call. If you are using this class outside a
                       `GraphDefinition`, please instatiate
                       with `input_feature_names`."""
            )  # noqa
            raise e
        return graph, self._output_feature_names

    @property
    def nb_outputs(self) -> int:
        """Return number of output features.

        This the default, but may be overridden by specific inheriting classes.
        """
        return len(self._output_feature_names)

    @final
    def set_number_of_inputs(self, input_feature_names: List[str]) -> None:
        """Return number of inputs expected by node definition.

        Args:
            input_feature_names: name of each input feature column.
        """
        assert isinstance(input_feature_names, list)
        self.nb_inputs = len(input_feature_names)

    @final
    def set_output_feature_names(self, input_feature_names: List[str]) -> None:
        """Set output features names as a member variable.

        Args:
            input_feature_names: List of column names of the input to the
            node definition.
        """
        self._output_feature_names = self._define_output_feature_names(
            input_feature_names
        )

    @abstractmethod
    def _define_output_feature_names(
        self, input_feature_names: List[str]
    ) -> List[str]:
        """Construct names of output columns.

        Args:
            input_feature_names: List of column names for the input data.

        Returns:
            A list of column names for each column in
            the node definition output.
        """

    @abstractmethod
    def _construct_nodes(self, x: torch.tensor) -> Tuple[Data, List[str]]:
        """Construct nodes from raw node features ´x´.

        Args:
            x: standardized node features with shape ´[num_pulses, d]´,
            where ´d´ is the number of node features.
            feature_names: List of names for reach column in `x`. Identical
            order of appearance. Length `d`.

        Returns:
            graph: graph without edges.
            new_node_features: A list of node features names.
        """


class NodesAsPulses(NodeDefinition):
    """Represent each measured pulse of Cherenkov Radiation as a node."""

    def _define_output_feature_names(
        self, input_feature_names: List[str]
    ) -> List[str]:
        return input_feature_names

    def _construct_nodes(self, x: torch.Tensor) -> Tuple[Data, List[str]]:
        return Data(x=x)


class PercentileClusters(NodeDefinition):
    """Represent nodes as clusters with percentile summary node features.

    If `cluster_on` is set to the xyz coordinates of DOMs
    e.g. `cluster_on = ['dom_x', 'dom_y', 'dom_z']`, each node will be a
    unique DOM and the pulse information (charge, time) is summarized using
    percentiles.
    """

    def __init__(
        self,
        cluster_on: List[str],
        percentiles: List[int],
        add_counts: bool = True,
        input_feature_names: Optional[List[str]] = None,
    ) -> None:
        """Construct `PercentileClusters`.

        Args:
            cluster_on: Names of features to create clusters from.
            percentiles: List of percentiles. E.g. `[10, 50, 90]`.
            add_counts: If True, number of duplicates is added to output array.
            input_feature_names: (Optional) column names for input features.
        """
        self._cluster_on = cluster_on
        self._percentiles = percentiles
        self._add_counts = add_counts
        # Base class constructor
        super().__init__(input_feature_names=input_feature_names)

    def _define_output_feature_names(
        self, input_feature_names: List[str]
    ) -> List[str]:
        (
            cluster_idx,
            summ_idx,
            new_feature_names,
        ) = self._get_indices_and_feature_names(
            input_feature_names, self._add_counts
        )
        self._cluster_indices = cluster_idx
        self._summarization_indices = summ_idx
        return new_feature_names

    def _get_indices_and_feature_names(
        self,
        feature_names: List[str],
        add_counts: bool,
    ) -> Tuple[List[int], List[int], List[str]]:
        cluster_idx, summ_idx, summ_names = identify_indices(
            feature_names, self._cluster_on
        )
        new_feature_names = deepcopy(self._cluster_on)
        for feature in summ_names:
            for pct in self._percentiles:
                new_feature_names.append(f"{feature}_pct{pct}")
        if add_counts:
            # add "counts" as the last feature
            new_feature_names.append("counts")
        return cluster_idx, summ_idx, new_feature_names

    def _construct_nodes(self, x: torch.Tensor) -> Data:
        # Cast to Numpy
        x = x.numpy()
        # Construct clusters with percentile-summarized features
        if hasattr(self, "_summarization_indices"):
            array = cluster_summarize_with_percentiles(
                x=x,
                summarization_indices=self._summarization_indices,
                cluster_indices=self._cluster_indices,
                percentiles=self._percentiles,
                add_counts=self._add_counts,
            )
        else:
            self.error(
                f"""{self.__class__.__name__} was not instatiated with
                `input_feature_names` and has not been set later.
                Please instantiate this class with `input_feature_names`
                if you're using it outside `GraphDefinition`."""
            )  # noqa
            raise AttributeError

        return Data(x=torch.tensor(array))

class IceMixNodes(NodeDefinition):
    
    def __init__(
        self, 
        input_feature_names: Optional[List[str]] = None,
        max_pulses: int = 384,
    ) -> None:
        
        super().__init__(input_feature_names=input_feature_names)
        
        if input_feature_names is None:
            input_feature_names = ["dom_x", 
                                   "dom_y",
                                   "dom_z", 
                                   "dom_time", 
                                   "charge",
                                   "hlc", 
                                   "rde"]        
        
        self.all_features = ["dom_x", 
                             "dom_y",
                             "dom_z", 
                             "dom_time", 
                             "charge",
                             "hlc", 
                             "rde", 
                             "scatt_lenght",
                             "abs_lenght"]
        
        missing_features = set(self.all_features) - set(input_feature_names)
        if any(feat in missing_features for feat in self.all_features[:7]):
            raise ValueError(f"Features dom_x, dom_y, dom_z, dom_time, charge, hlc, rde"
                             f" are required for IceMixNodes")
        
        self.feature_indexes = {feat: self.all_features.index(feat) for feat in input_feature_names}
        self.input_feature_names  = input_feature_names   
        self.max_length = max_pulses

    def _define_output_feature_names(
        self, 
        input_feature_names: List[str]
    ) -> List[str]:
        return self.all_features
    
    def _add_ice_properties(self,
                            graph: torch.Tensor,
                            x: torch.Tensor,
                            ids: List[int]) -> torch.Tensor:

        f_scattering, f_absoprtion = ice_transparency()
        graph[:len(ids),7] = torch.tensor(f_scattering(x[ids, self.feature_indexes["dom_z"]]))
        graph[:len(ids),8] = torch.tensor(f_absoprtion(x[ids, self.feature_indexes["dom_z"]]))
        return graph

    def _construct_nodes(self, x: torch.Tensor) -> Tuple[Data, List[str]]:
        
        n_pulses = x.shape[0]
        graph = torch.zeros([n_pulses, len(self.all_features)])
        
        event_length = n_pulses
        x[:, self.feature_indexes["hlc"]] = torch.logical_not(x[:, self.feature_indexes["hlc"]])

        if event_length < self.max_length:
            ids = torch.arange(event_length)
        else:
            ids = torch.randperm(event_length)
            auxiliary_n = torch.nonzero(x[:, self.feature_indexes["hlc"]] == 0).squeeze(1)
            auxiliary_p = torch.nonzero(x[:, self.feature_indexes["hlc"]] == 1).squeeze(1)
            ids_n = ids[auxiliary_n][: min(self.max_length, len(auxiliary_n))]
            ids_p = ids[auxiliary_p][: min(self.max_length - len(ids_n), len(auxiliary_p))]
            ids = torch.cat([ids_n, ids_p]).sort().values
            event_length = len(ids)
            
        for idx, feature in enumerate(self.all_features[:7]):
            graph[:event_length, idx] = x[ids, self.feature_indexes[feature]]

        graph = self._add_ice_properties(graph, x, ids) #ice properties  
        return Data(x=graph)