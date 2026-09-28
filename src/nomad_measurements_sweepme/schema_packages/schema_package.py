import json
import math
from typing import TYPE_CHECKING, Any

from baseclasses.solar_energy.jvmeasurement import (
    JVMeasurement,
    SolarCellJVCurveCustom,
    SolarCellJVCurveDarkCustom,
)
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
        'Illuminated Area in cm²',
        'Illumination in W/m²',
        'Operator',
    }
    _required_calculated_value_keys = {
        'SAT',
        'P_MPP',
        'PCE',
        'VOC',
        'ISC',
        'FF',
        'V_MPP',
        'I_MPP',
    }

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @classmethod
    def _finite_number(cls, value: Any, key: str) -> float:
        if not cls._is_number(value) or not math.isfinite(value):
            raise ValueError(f'SweepMe {key} must be a finite number.')
        return float(value)

    @classmethod
    def _source_string(cls, value: Any, key: str) -> str:
        if isinstance(value, str) or cls._is_number(value):
            return str(value)
        raise ValueError(f'SweepMe {key} must be a string or number.')

    @classmethod
    def _curve_from_source(
        cls,
        source_curve: Any,
        curve_name: str,
        active_area: float,
    ) -> tuple[list[float], list[float]]:
        if not isinstance(source_curve, list) or not source_curve:
            raise ValueError(f'SweepMe {curve_name} must be a non-empty list.')

        voltage = []
        current_density = []
        for point in source_curve:
            if not isinstance(point, dict) or not {
                'index',
                'voltage',
                'current',
            }.issubset(point):
                raise ValueError(f'SweepMe {curve_name} contains an incomplete point.')
            if not isinstance(point['index'], int) or isinstance(point['index'], bool):
                raise ValueError(
                    f'SweepMe {curve_name} point index must be an integer.'
                )

            voltage.append(
                cls._finite_number(point['voltage'], f'{curve_name} voltage')
            )
            current_density.append(
                1000
                * cls._finite_number(point['current'], f'{curve_name} current')
                / active_area
            )

        return voltage, current_density

    @classmethod
    def _source_snapshot(cls, source: Any) -> dict[str, Any]:
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

        for key in (
            'Sample ID',
            'Measurement ID',
            'Experiment Time',
            'Comment',
            'Operator',
        ):
            if not isinstance(conditions[key], str):
                raise ValueError(f'SweepMe {key} must be a string.')

        active_area = cls._finite_number(
            conditions['Illuminated Area in cm²'], 'Illuminated Area in cm²'
        )
        if active_area <= 0:
            raise ValueError(
                'SweepMe Illuminated Area in cm² must be greater than zero.'
            )
        intensity = (
            cls._finite_number(
                conditions['Illumination in W/m²'], 'Illumination in W/m²'
            )
            / 10
        )

        calculated = calculated_values[0]
        calculated_numbers = {
            key: cls._finite_number(calculated[key], key)
            for key in cls._required_calculated_value_keys
        }
        dark_voltage, dark_current_density = cls._curve_from_source(
            source.get('Dark Curve'), 'Dark Curve', active_area
        )
        illuminated_voltage, illuminated_current_density = cls._curve_from_source(
            source.get('Illuminated Curve'), 'Illuminated Curve', active_area
        )

        dark_curve = SolarCellJVCurveDarkCustom(
            cell_name='Dark',
            dark=True,
            voltage=dark_voltage,
            current_density=dark_current_density,
        )
        illuminated_curve = SolarCellJVCurveCustom(
            cell_name='Illuminated',
            dark=False,
            voltage=illuminated_voltage,
            current_density=illuminated_current_density,
            light_intensity=intensity,
            open_circuit_voltage=calculated_numbers['VOC'],
            short_circuit_current_density=abs(calculated_numbers['ISC']) / active_area,
            fill_factor=calculated_numbers['FF'] / 100,
            efficiency=calculated_numbers['PCE'],
            potential_at_maximum_power_point=calculated_numbers['V_MPP'],
            current_density_at_maximun_power_point=(
                abs(calculated_numbers['I_MPP']) / active_area
            ),
        )

        return {
            'sample_id': conditions['Sample ID'],
            'measurement_id': conditions['Measurement ID'],
            'source_experiment_time': conditions['Experiment Time'],
            'source_comment': conditions['Comment'],
            'temperature_source': cls._source_string(
                conditions['Temperature'], 'Temperature'
            ),
            'light_level': cls._source_string(conditions['Light level'], 'Light level'),
            'saturation': calculated_numbers['SAT'],
            'power_at_mpp': calculated_numbers['P_MPP'],
            'operator': conditions['Operator'],
            'active_area': active_area,
            'intensity': intensity,
            'jv_curve': [dark_curve, illuminated_curve],
        }

    def _refresh_source(self, archive: 'EntryArchive') -> None:
        try:
            with archive.m_context.raw_file(self.data_file, 'rt') as file:
                source = json.load(file)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f'Could not read SweepMe source file {self.data_file!r}.'
            ) from error

        snapshot = self._source_snapshot(source)
        for key, value in snapshot.items():
            setattr(self, key, value)

    def normalize(self, archive: 'EntryArchive', logger: 'BoundLogger') -> None:
        if not self.data_file:
            super().normalize(archive, logger)
            return

        try:
            self._refresh_source(archive)
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
