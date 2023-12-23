"""Base `Dataloader` class(es) used in `graphnet`."""
from typing import Dict, Any, Optional, List, Tuple, Union
import pytorch_lightning as pl
from torch.utils.data import DataLoader
from copy import deepcopy
from sklearn.model_selection import train_test_split
import pandas as pd
import random

from graphnet.data.dataset import (
    Dataset,
    EnsembleDataset,
    SQLiteDataset,
    ParquetDataset,
)
from graphnet.utilities.logging import Logger
from graphnet.training.utils import save_selection


class GraphNeTDataModule(pl.LightningDataModule, Logger):
    """General Class for DataLoader Construction."""

    def __init__(
        self,
        dataset_reference: Union[SQLiteDataset, ParquetDataset, Dataset],
        selection: Optional[Union[List[int], List[List[int]]]],
        test_selection: Optional[Union[List[int], List[List[int]]]],
        dataset_args: Dict[str, Any],
        train_dataloader_kwargs: Optional[Dict[str, Any]] = None,
        validation_dataloader_kwargs: Optional[Dict[str, Any]] = None,
        test_dataloader_kwargs: Optional[Dict[str, Any]] = None,
        train_val_split: Optional[List[float]] = [0.9, 0.10],
        split_seed: int = 42,
    ) -> None:
        """Create dataloaders from dataset.

        Args:
            dataset_reference: A non-instantiated reference to the dataset class.
            selection: (Optional) a list of event id's used for training and validation.
            test_selection: (Optional) a list of event id's used for testing.
            dataset_args: Arguments to instantiate graphnet.data.dataset.Dataset with.
            train_dataloader_kwargs: Arguments for the training DataLoader.
            validation_dataloader_kwargs: Arguments for the validation DataLoader.
            test_dataloader_kwargs: Arguments for the test DataLoader.
            train_val_split (Optional): Split ratio for training and validation sets. Default is [0.9, 0.10].
            split_seed: seed used for shuffling and splitting selections into train/validation.
        """
        self._dataset = dataset_reference
        self._selection = selection or [0]
        self._train_val_split = train_val_split or [0.0]
        self._test_selection = test_selection or [0.0]
        self._dataset_args = dataset_args
        self._rng = split_seed

        self._train_dataloader_kwargs = train_dataloader_kwargs or {}
        self._validation_dataloader_kwargs = validation_dataloader_kwargs or {}
        self._test_dataloader_kwargs = test_dataloader_kwargs or {}

        # If multiple dataset paths are given, we should use EnsembleDataset
        self._use_ensemble_dataset = isinstance(
            self._dataset_args["path"], list
        )

    def prepare_data(self) -> None:
        """Prepare the dataset for training."""
        # Download method for curated datasets. Method for download is
        # likely dataset-specific, so we can leave it as-is
        pass

    def setup(self, stage: str) -> None:
        """Prepare Datasets for DataLoaders.

        Args:
            stage: lightning stage. Either "fit, validate, test, predict"
        """
        # Sanity Checks
        self._validate_dataset_class()
        self._validate_dataset_args()
        self._validate_dataloader_args()

        # Case-handling of selection arguments
        self._resolve_selections()

        # Creation of Datasets
        self._train_dataset = self._create_dataset(self._train_selection)
        self._val_dataset = self._create_dataset(self._val_selection)
        self._test_dataset = self._create_dataset(self._test_selection)

        return

    def train_dataloader(self) -> DataLoader:
        """Prepare and return the training DataLoader.

        Returns:
            DataLoader: The DataLoader configured for training.
        """
        return self._create_dataloader(self._train_dataset)

    def val_dataloader(self) -> DataLoader:
        """Prepare and return the validation DataLoader.

        Returns:
            DataLoader: The DataLoader configured for validation.
        """
        return self._create_dataloader(self._val_dataset)

    def test_dataloader(self) -> DataLoader:
        """Prepare and return the test DataLoader.

        Returns:
            DataLoader: The DataLoader configured for testing.
        """
        return self._create_dataloader(self._test_dataset)

    def teardown(self) -> None:  # type: ignore[override]
        """Perform any necessary cleanup or shutdown procedures.

        This method can be used for tasks such as closing SQLite connections
        after training. Override this method as needed.

        Returns:
            None
        """
        if hasattr(self, "_train_dataset") and isinstance(
            self._train_dataset, SQLiteDataset
        ):
            self._train_dataset._close_connection()

        if hasattr(self, "_val_dataset") and isinstance(
            self._val_dataset, SQLiteDataset
        ):
            self._val_dataset._close_connection()

        if hasattr(self, "_test_dataset") and isinstance(
            self._test_dataset, SQLiteDataset
        ):
            self._test_dataset._close_connection()

        return

    def _create_dataloader(
        self, dataset: Union[Dataset, EnsembleDataset]
    ) -> DataLoader:
        """Create a DataLoader for the given dataset.

        Args:
            dataset (Union[Dataset, EnsembleDataset]): The dataset to create a DataLoader for.

        Returns:
            DataLoader: The DataLoader configured for the given dataset.
        """
        if dataset == self._train_dataset:
            dataloader_args = self._train_dataloader_kwargs
        elif dataset == self._val_dataset:
            dataloader_args = self._validation_dataloader_kwargs
        elif dataset == self._test_dataset:
            dataloader_args = self._test_dataloader_kwargs
        else:
            raise ValueError(
                "Unknown dataset encountered during dataloader creation."
            )

        return DataLoader(dataset=dataset, **dataloader_args)

    def _validate_dataset_class(self) -> None:
        """Sanity checks on the dataset reference (self._dataset).

        Checks whether the dataset is an instance of SQLiteDataset,
        ParquetDataset, or Dataset. Raises a TypeError if an invalid dataset
        type is detected, or if an EnsembleDataset is used.
        """
        if not isinstance(
            self._dataset, (SQLiteDataset, ParquetDataset, Dataset)
        ):
            raise TypeError(
                "dataset_reference must be an instance of SQLiteDataset, ParquetDataset, or Dataset."
            )
        if isinstance(self._dataset, EnsembleDataset):
            raise TypeError(
                "EnsembleDataset is not allowed as dataset_reference."
            )

    def _validate_dataset_args(self) -> None:
        """Sanity checks on the arguments for the dataset reference."""
        if isinstance(self._dataset_args["path"], list):
            if self._selection is not None:
                try:
                    # Check that the number of dataset paths is equal to the
                    # number of selections given as arg.
                    assert len(self._dataset_args["path"]) == len(
                        self._selection
                    )
                except AssertionError:
                    raise ValueError(
                        f"The number of dataset paths ({len(self._dataset_args['path'])}) does not match the number of selections ({len(self._selection)})."
                    )

            if self._test_selection is not None:
                try:
                    # Check that the number of dataset paths is equal to the
                    # number of test selections.
                    assert len(self._dataset_args["path"]) == len(
                        self._test_selection
                    )
                except AssertionError:
                    raise ValueError(
                        f"The number of dataset paths ({len(self._dataset_args['path'])}) does not match the number of test selections ({len(self._test_selection)}). If you'd like to test on only a subset of the {len(self._dataset_args['path'])} datasets, please provide empty test selections for the others."
                    )

    def _validate_dataloader_args(self) -> None:
        """Sanity check on `dataloader_args`."""
        if "dataset" in self._train_dataloader_kwargs:
            raise ValueError(
                "`train_dataloader_kwargs` must not contain `dataset`"
            )
        if "dataset" in self._validation_dataloader_kwargs:
            raise ValueError(
                "`validation_dataloader_kwargs` must not contain `dataset`"
            )
        if "dataset" in self._test_dataloader_kwargs:
            raise ValueError(
                "`test_dataloader_kwargs` must not contain `dataset`"
            )

    def _resolve_selections(self) -> None:
        if self._test_selection is None:
            self.warning_once(
                f"{self.__class__.__name__} did not receive an argument for `test_selection` and will therefore not have a prediction dataloader available."
            )
        if self._selection is not None:
            # Split the selection into train/validation
            if self._use_ensemble_dataset:
                # Split every selection
                self._train_selection = []
                self._val_selection = []
                for selection in self._selection:
                    train_selection, val_selection = self._split_selection(
                        selection
                    )
                    self._train_selection.append(train_selection)
                    self._val_selection.append(val_selection)

            else:
                # Split the only selection we got
                assert isinstance(self._selection, list)
                (
                    self._train_selection,
                    self._val_selection,
                ) = self._split_selection(  # type: ignore
                    self._selection
                )

        if self._selection is None:
            # If not provided, we infer it by grabbing all event ids in the dataset.
            self.info(
                f"{self.__class__.__name__} did not receive an argument for `selection`. Selection will automatically be created with a split of train: {self._train_val_split[0]} and validation: {self._train_val_split[1]}"
            )
            (
                self._train_selection,
                self._val_selection,
            ) = self._infer_selections()

    def _split_selection(
        self, selection: Union[int, List[int], List[List[int]]]
    ) -> Tuple[List[int], List[int]]:
        """Split train selection into train/validation.

        Args:
            selection: Training selection to be split

        Returns:
            Training selection, Validation selection.
        """
        assert isinstance(selection, (int, list))
        if isinstance(selection, int):
            flat_selection = [selection]
        elif isinstance(selection[0], list):
            flat_selection = [
                item for sublist in selection for item in sublist  # type: ignore
            ]
        else:
            flat_selection = selection  # type: ignore
        assert isinstance(flat_selection, list)

        train_selection, val_selection = train_test_split(
            flat_selection,
            train_size=self._train_val_split[0],
            test_size=self._train_val_split[1],
            random_state=self._rng,
        )
        return train_selection, val_selection

    def _infer_selections(self) -> Tuple[List[int], List[int]]:
        """Automatically infer training and validation selections.

        Returns:
            Training selection, Validation selection
        """
        if self._use_ensemble_dataset:
            # We must iterate through the dataset paths and infer a train/val
            # selection for each.
            self._train_selection = []
            self._val_selection = []
            for dataset_path in self._dataset_args["path"]:
                (
                    train_selection,
                    val_selection,
                ) = self._infer_selections_on_single_dataset(dataset_path)
                self._train_selection.extend(train_selection)  # type: ignore
                self._val_selection.extend(val_selection)  # type: ignore
        else:
            # Infer selection on a single dataset
            (
                self._train_selection,
                self._val_selection,
            ) = self._infer_selections_on_single_dataset(  # type: ignore
                self._dataset_args["path"]
            )

        return (self._train_selection, self._val_selection)  # type: ignore

    def _infer_selections_on_single_dataset(
        self, dataset_path: str
    ) -> Tuple[List[int], List[int]]:
        """Automatically infers dataset train/val selections.

        Args:
            dataset_path (str): The path to the dataset.

        Returns:
            Tuple[List[int], List[int]]: Training and validation selections.
        """
        tmp_args = deepcopy(self._dataset_args)
        tmp_args["path"] = dataset_path
        tmp_dataset = self._construct_dataset(tmp_args)

        all_events = (
            tmp_dataset._get_all_indices()
        )  # unshuffled list, # sequential index

        # Multiple lines to avoid one large
        all_events = pd.DataFrame(all_events).sample(
            frac=1, replace=False, random_state=self._rng
        )

        all_events = random.sample(
            all_events, len(all_events)
        )  # shuffled list
        return self._split_selection(all_events)

    def _get_all_indices(self) -> List[int]:
        """Get all indices.

        Return:
            List of indices in an unshuffled order.
        """
        if self._use_ensemble_dataset:
            all_indices = []
            for dataset_path in self._dataset_args["path"]:
                tmp_args = deepcopy(self._dataset_args)
                tmp_args["path"] = dataset_path
                tmp_dataset = self._construct_dataset(tmp_args)
                all_indices.extend(tmp_dataset._get_all_indices())
        else:
            all_indices = self._dataset._get_all_indices()

        return all_indices

    def _construct_dataset(self, tmp_args: Dict[str, Any]) -> Dataset:
        """Construct dataset.

        Return:
            Dataset object constructed from input arguments.
        """
        dataset = self._dataset(**tmp_args)
        return dataset

    def _create_dataset(
        self, selection: Union[List[int], List[List[int]], List[float]]
    ) -> Union[EnsembleDataset, Dataset]:
        """Instantiate `dataset_reference`.

        Args:
            selection: The selected event id's.

        Returns:
            A dataset, either an instance of `EnsembleDataset` or `Dataset`.
        """
        if self._use_ensemble_dataset:
            # Construct multiple datasets and pass to EnsembleDataset
            # At this point, we have checked that len(selection) == len(dataset_args['path'])
            datasets = []
            for dataset_idx in range(len(selection)):
                datasets.append(
                    self._create_single_dataset(
                        selection=selection[dataset_idx],  # type: ignore
                        path=self._dataset_args["path"][dataset_idx],
                    )
                )

            dataset = EnsembleDataset(datasets)

        else:
            # Construct single dataset
            dataset = self._create_single_dataset(
                selection=selection, path=self._dataset_args["path"]  # type: ignore
            )
        return dataset

    def _create_single_dataset(
        self,
        selection: Union[List[int], List[List[int]], List[float]],
        path: str,
    ) -> Dataset:
        """Instantiate a single `Dataset`.

        Args:
            selection: A selection for a single dataset.
            path: Path to a single dataset

        Returns:
            An instance of `Dataset`.
        """
        tmp_args = deepcopy(self._dataset_args)
        tmp_args["path"] = path
        tmp_args["selection"] = selection
        return self._construct_dataset(tmp_args)
