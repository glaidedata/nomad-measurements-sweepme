import json
from typing import TYPE_CHECKING, Any

from baseclasses.solar_energy.jvmeasurement import JVMeasurement
from nomad.datamodel.data import EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Quantity, SchemaPackage

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

m_package = SchemaPackage()


class SweepMeJVMeasurement(JVMeasurement, EntryData):
    """Editable SweepMe entry using the HZB JV scientific model."""

    sample_id = Quantity(
        type=str,
        description='SweepMe source Sample ID. This is not a NOMAD sample reference.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    measurement_id = Quantity(
        type=str,
        description=(
            'SweepMe source Measurement ID. It is not assigned to NOMAD lab_id '
            'because its confirmed scope is within a sample.'
        ),
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    source_experiment_time = Quantity(
        type=str,
        description=(
            'Local measurement-PC time from SweepMe. The source JSON does not '
            'include a timezone offset.'
        ),
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    source_comment = Quantity(
        type=str,
        description='Comment preserved from the SweepMe source export.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    temperature_source = Quantity(
        type=str,
        description=(
            'Temperature literal from the SweepMe source export. Its unit is '
            'not confirmed and is therefore intentionally not declared.'
        ),
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    light_level = Quantity(
        type=str,
        description=(
            'Uncalibrated SweepMe demo-box light-sensor reading in arbitrary '
            'units. It is not irradiance.'
        ),
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    saturation = Quantity(
        type=float,
        description=(
            'SweepMe SAT ratio: current at minimum voltage divided by current '
            'at short circuit.'
        ),
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    power_at_mpp = Quantity(
        type=float,
        unit='mW',
        description='SweepMe P_MPP, the power at maximum power point.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )

    _required_condition_keys = {
        'Sample ID',
        'Measurement ID',
        'Experiment Time',
        'Comment',
        'Temperature',
        'Light level',
    }
    _required_calculated_value_keys = {'SAT', 'P_MPP'}

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @classmethod
    def _source_string(cls, value: Any, key: str) -> str:
        if isinstance(value, str) or cls._is_number(value):
            return str(value)
        raise ValueError(f'SweepMe {key} must be a string or number.')

    @classmethod
    def _metadata_from_source(cls, source: Any) -> dict[str, Any]:
        if not isinstance(source, dict):
            raise ValueError('SweepMe source must contain a top-level object.')

        conditions = source.get('Conditions')
        calculated_values = source.get('Calculated Values')
        if not isinstance(
            conditions, dict
        ) or not cls._required_condition_keys.issubset(conditions):
            raise ValueError('SweepMe source Conditions are incomplete.')
        if (
            not isinstance(calculated_values, list)
            or not calculated_values
            or not isinstance(calculated_values[0], dict)
            or not cls._required_calculated_value_keys.issubset(calculated_values[0])
        ):
            raise ValueError('SweepMe source Calculated Values are incomplete.')

        calculated = calculated_values[0]
        source_fields = {
            'sample_id': conditions['Sample ID'],
            'measurement_id': conditions['Measurement ID'],
            'source_experiment_time': conditions['Experiment Time'],
            'source_comment': conditions['Comment'],
            'temperature_source': cls._source_string(
                conditions['Temperature'], 'Temperature'
            ),
            'light_level': cls._source_string(conditions['Light level'], 'Light level'),
            'saturation': calculated['SAT'],
            'power_at_mpp': calculated['P_MPP'],
        }
        for key in (
            'sample_id',
            'measurement_id',
            'source_experiment_time',
            'source_comment',
        ):
            if not isinstance(source_fields[key], str):
                raise ValueError(f'SweepMe {key} must be a string.')
        for key in ('saturation', 'power_at_mpp'):
            if not cls._is_number(source_fields[key]):
                raise ValueError(f'SweepMe {key} must be numeric.')

        return source_fields

    def _refresh_source_metadata(self, archive: 'EntryArchive') -> None:
        if not self.data_file:
            raise ValueError('SweepMe data_file is unavailable.')

        try:
            with archive.m_context.raw_file(self.data_file, 'rt') as file:
                source = json.load(file)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f'Could not read SweepMe source file {self.data_file!r}.'
            ) from error

        source_fields = self._metadata_from_source(source)
        for key, value in source_fields.items():
            setattr(self, key, value)

    def normalize(self, archive: 'EntryArchive', logger: 'BoundLogger') -> None:
        if not self.data_file:
            super().normalize(archive, logger)
            return

        try:
            self._refresh_source_metadata(archive)
        except ValueError as error:
            if logger:
                logger.error(
                    'Could not refresh SweepMe source metadata',
                    data_file=self.data_file,
                    error=str(error),
                )
            raise

        super().normalize(archive, logger)


m_package.__init_metainfo__()
