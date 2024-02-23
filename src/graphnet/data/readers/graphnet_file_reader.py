"""Module containing different FileReader classes in GraphNeT.

These methods are used to open and apply `Extractors` to experiment-specific
file formats.
"""

from typing import List, Union, OrderedDict, Any
from abc import abstractmethod, ABC
import glob
import os

from graphnet.utilities.decorators import final
from graphnet.utilities.logging import Logger
from graphnet.data.dataclasses import I3FileSet
from graphnet.data.extractors.extractor import Extractor
from graphnet.data.extractors.icecube import I3Extractor


class GraphNeTFileReader(Logger, ABC):
    """A generic base class for FileReaders in GraphNeT.

    Classes inheriting from `GraphNeTFileReader` must implement a
    `__call__` method that opens a file, applies `Extractor`(s) and returns
    a list of ordered dictionaries.

    In addition, Classes inheriting from `GraphNeTFileReader` must set
    class properties `accepted_file_extensions` and `accepted_extractors`.
    """

    _accepted_file_extensions: List[str] = []
    _accepted_extractors: List[Any] = []

    @abstractmethod
    def __call__(self, file_path: Union[str, I3FileSet]) -> List[OrderedDict]:
        """Open and apply extractors to a single file.

        The `output` must be a list of dictionaries, where the number of events
        in the file `n_events` satisfies `len(output) = n_events`. I.e each
        element in the list is a dictionary, and each field in the dictionary
        is the output of a single extractor.
        """

    @property
    def accepted_file_extensions(self) -> List[str]:
        """Return list of accepted file extensions."""
        return self._accepted_file_extensions

    @property
    def accepted_extractors(self) -> List[Extractor]:
        """Return list of compatible `Extractor`(s)."""
        return self._accepted_extractors

    @property
    def extracor_names(self) -> List[str]:
        """Return list of table names produced by extractors."""
        return [extractor.name for extractor in self._extractors]

    def find_files(
        self, path: Union[str, List[str]]
    ) -> Union[List[str], List[I3FileSet]]:
        """Search directory for input files recursively.

        This method may be overwritten by custom implementations.

        Args:
            path: path to directory.

        Returns:
            List of files matching accepted file extensions.
        """
        if isinstance(path, str):
            path = [path]
        files = []
        for dir in path:
            for accepted_file_extension in self.accepted_file_extensions:
                files.extend(glob.glob(dir + f"/*{accepted_file_extension}"))

        # Check that files are OK.
        self.validate_files(files)
        return files

    @final
    def set_extractors(
        self, extractors: Union[List[Extractor], List[I3Extractor]]
    ) -> None:
        """Set `Extractor`(s) as member variable.

        Args:
            extractors: A list of `Extractor`(s) to set as member variable.
        """
        if not isinstance(extractors, list):
            extractors = [extractors]
        self._validate_extractors(extractors)
        self._extractors = extractors

    @final
    def _validate_extractors(
        self, extractors: Union[List[Extractor], List[I3Extractor]]
    ) -> None:
        for extractor in extractors:
            try:
                assert isinstance(extractor, tuple(self.accepted_extractors))  # type: ignore
            except AssertionError as e:
                self.error(
                    f"{extractor.__class__.__name__}"
                    f" is not supported by {self.__class__.__name__}"
                )
                raise e

    @final
    def validate_files(
        self, input_files: Union[List[str], List[I3FileSet]]
    ) -> None:
        """Check that the input files are accepted by the reader.

        Args:
            input_files: Path(s) to input file(s).
        """
        for input_file in input_files:
            # Handle filepath vs. FileSet cases
            if isinstance(input_file, I3FileSet):
                self._validate_file(input_file.i3_file)
                self._validate_file(input_file.gcd_file)
            else:
                self._validate_file(input_file)

    @final
    def _validate_file(self, file: str) -> None:
        """Validate a single file path.

        Args:
            file: path to file.

        Returns:
            None
        """
        try:
            assert file.lower().endswith(tuple(self.accepted_file_extensions))
        except AssertionError:
            self.error(
                f'{self.__class__.__name__} accepts {self.accepted_file_extensions} but {file.split("/")[-1]} has extension {os.path.splitext(file)[1]}.'
            )
