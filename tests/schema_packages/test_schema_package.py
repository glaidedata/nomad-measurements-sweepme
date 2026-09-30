import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from baseclasses.solar_energy.jvmeasurement import JVMeasurement
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.context import Context
from nomad.datamodel.data import EntryData
from nomad.datamodel.metainfo.basesections import CompositeSystemReference

from nomad_measurements_sweepme.schema_packages import schema_package_entry_point
from nomad_measurements_sweepme.schema_packages.schema_package import (
    SweepMeJVMeasurement,
    m_package,
)

SYNTHETIC_SATURATION = 1.125
SYNTHETIC_POWER_AT_MPP = 6.75
INITIAL_SATURATION = 1.07
INITIAL_POWER_AT_MPP = 5.4
UPDATED_SATURATION = 1.12
UPDATED_POWER_AT_MPP = 6.8
INITIAL_ACTIVE_AREA = 0.4
INITIAL_ILLUMINATION = 830.0
INITIAL_INTENSITY = INITIAL_ILLUMINATION / 10
UPDATED_ACTIVE_AREA = 0.5
UPDATED_ILLUMINATION = 640.0
UPDATED_INTENSITY = UPDATED_ILLUMINATION / 10
EXPECTED_CURVE_COUNT = 2
INITIAL_PCE = 7.2
INITIAL_VOC = 0.78
INITIAL_ISC = -1.2
INITIAL_FILL_FACTOR_PERCENT = 61.0
INITIAL_V_MPP = 0.55
INITIAL_I_MPP = -0.95
UPDATED_PCE = 9.1
UPDATED_VOC = 0.74
UPDATED_ISC = -1.5
UPDATED_FILL_FACTOR_PERCENT = 66.0
UPDATED_V_MPP = 0.52
UPDATED_I_MPP = -1.1
EXPECTED_FALLBACK_EFFICIENCY = 0.5625


class RawFileContext(Context):
    def __init__(self, raw_directory: Path):
        super().__init__()
        self.raw_directory = raw_directory

    @contextmanager
    def raw_file(self, path: str, mode: str = 'r'):
        with (self.raw_directory / path).open(mode) as file:
            yield file


class CapturingLogger:
    def __init__(self):
        self.errors = []

    def error(self, event, **kwargs):
        self.errors.append((event, kwargs))


def sweepme_source(
    temperature=24.5,
    light_level=680,
    active_area=INITIAL_ACTIVE_AREA,
    illumination=INITIAL_ILLUMINATION,
) -> dict:
    return {
        'Conditions': {
            'Sample ID': '0008-SYN',
            'Measurement ID': 'measurement_beta',
            'Experiment Time': '2032-02-03T04:05:06.789',
            'Comment': 'Synthetic source comment',
            'Temperature': temperature,
            'Light level': light_level,
            'Illuminated Area in cm²': active_area,
            'Illumination in W/m²': illumination,
            'Operator': 'Synthetic Operator',
        },
        'Dark Curve': [
            {'index': 0, 'voltage': -0.2, 'current': -0.0006},
            {'index': 1, 'voltage': 0.1, 'current': 0.0002},
        ],
        'Illuminated Curve': [
            {'index': 0, 'voltage': 0.0, 'current': -0.0012},
            {'index': 1, 'voltage': 0.45, 'current': -0.0005},
            {'index': 2, 'voltage': 0.8, 'current': 0.0001},
        ],
        'Calculated Values': [
            {
                'SAT': INITIAL_SATURATION,
                'P_MPP': INITIAL_POWER_AT_MPP,
                'PCE': INITIAL_PCE,
                'VOC': INITIAL_VOC,
                'ISC': INITIAL_ISC,
                'FF': INITIAL_FILL_FACTOR_PERCENT,
                'V_MPP': INITIAL_V_MPP,
                'I_MPP': INITIAL_I_MPP,
            }
        ],
    }


def write_source(raw_directory: Path, source: object, filename='source.json') -> None:
    (raw_directory / filename).write_text(json.dumps(source))


def archive_for(raw_directory: Path, measurement: SweepMeJVMeasurement) -> EntryArchive:
    return EntryArchive(
        data=measurement,
        m_context=RawFileContext(raw_directory),
        metadata=EntryMetadata(
            upload_id='synthetic-upload',
            entry_id='editable-entry',
            entry_name='source.archive.json',
        ),
    )


def normalize_from_source(raw_directory: Path, source: object, measurement=None):
    write_source(raw_directory, source)
    measurement = measurement or SweepMeJVMeasurement(data_file='source.json')
    archive = archive_for(raw_directory, measurement)
    measurement.normalize(archive, CapturingLogger())
    return measurement, archive


def magnitudes(quantity) -> list[float]:
    return quantity.magnitude.tolist()


def magnitude_in(quantity, unit: str) -> float:
    return quantity.to(unit).magnitude


def assert_jv_figure(figure, label: str, traces) -> None:
    assert figure.label == label
    assert figure.figure['layout'] == {
        'xaxis': {'title': {'text': 'Voltage (V)'}},
        'yaxis': {'title': {'text': 'Current density (mA/cm²)'}},
    }
    assert len(figure.figure['data']) == len(traces)
    for trace, (name, voltage, current_density) in zip(
        figure.figure['data'], traces, strict=True
    ):
        assert trace['type'] == 'scatter'
        assert trace['mode'] == 'lines'
        assert trace['name'] == name
        assert trace['x'] == voltage
        assert trace['y'] == pytest.approx(current_density)


def assert_jv_figures(measurement, dark_traces, illuminated_traces) -> None:
    dark_curve, illuminated_curve = measurement.jv_curve
    assert len(dark_curve.figures) == 1
    assert len(illuminated_curve.figures) == 1
    assert len(measurement.figures) == 1
    assert_jv_figure(dark_curve.figures[0], 'Dark JV', dark_traces)
    assert_jv_figure(illuminated_curve.figures[0], 'Illuminated JV', illuminated_traces)
    assert_jv_figure(
        measurement.figures[0],
        'SweepMe JV',
        [*dark_traces, *illuminated_traces],
    )


def test_schema_package_loads():
    assert schema_package_entry_point.load() is m_package


def test_sweepme_jv_measurement_inherits_hzb_jv_model():
    assert issubclass(SweepMeJVMeasurement, JVMeasurement)
    assert issubclass(SweepMeJVMeasurement, EntryData)

    measurement = SweepMeJVMeasurement()

    assert hasattr(measurement, 'active_area')
    assert hasattr(measurement, 'intensity')
    assert hasattr(measurement, 'jv_curve')


def test_sweepme_source_metadata_serializes_without_scientific_mapping():
    measurement = SweepMeJVMeasurement(
        sample_id='0017-XY',
        measurement_id='run_alpha_07',
        source_experiment_time='2031-04-15T08:09:10.123456',
        source_comment='Synthetic schema test comment',
        temperature_source='42',
        light_level='987',
        saturation=SYNTHETIC_SATURATION,
        power_at_mpp=SYNTHETIC_POWER_AT_MPP,
    )

    serialized = measurement.m_to_dict()

    assert serialized['sample_id'] == '0017-XY'
    assert serialized['measurement_id'] == 'run_alpha_07'
    assert serialized['source_experiment_time'] == '2031-04-15T08:09:10.123456'
    assert serialized['source_comment'] == 'Synthetic schema test comment'
    assert serialized['temperature_source'] == '42'
    assert serialized['light_level'] == '987'
    assert serialized['saturation'] == SYNTHETIC_SATURATION
    assert serialized['power_at_mpp'] == SYNTHETIC_POWER_AT_MPP


def test_normalize_populates_hzb_jv_model_from_sweepme_source(tmp_path):
    measurement, _ = normalize_from_source(tmp_path, sweepme_source())
    dark_curve, illuminated_curve = measurement.jv_curve

    assert measurement.sample_id == '0008-SYN'
    assert measurement.measurement_id == 'measurement_beta'
    assert measurement.source_experiment_time == '2032-02-03T04:05:06.789'
    assert measurement.source_comment == 'Synthetic source comment'
    assert measurement.temperature_source == '24.5'
    assert measurement.light_level == '680'
    assert measurement.saturation == INITIAL_SATURATION
    assert measurement.power_at_mpp.magnitude == INITIAL_POWER_AT_MPP
    assert measurement.operator == 'Synthetic Operator'
    assert measurement.active_area.magnitude == INITIAL_ACTIVE_AREA
    assert measurement.intensity.magnitude == INITIAL_INTENSITY
    assert len(measurement.jv_curve) == EXPECTED_CURVE_COUNT

    assert dark_curve.dark is True
    assert magnitudes(dark_curve.voltage) == [-0.2, 0.1]
    assert magnitudes(dark_curve.current_density) == pytest.approx([-1.5, 0.5])
    assert dark_curve.open_circuit_voltage is None
    assert dark_curve.short_circuit_current_density is None
    assert dark_curve.fill_factor is None
    assert dark_curve.efficiency is None
    assert dark_curve.potential_at_maximum_power_point is None
    assert dark_curve.current_density_at_maximun_power_point is None

    assert illuminated_curve.dark is False
    assert magnitudes(illuminated_curve.voltage) == [0.0, 0.45, 0.8]
    assert magnitudes(illuminated_curve.current_density) == pytest.approx(
        [-3.0, -1.25, 0.25]
    )
    assert illuminated_curve.light_intensity.magnitude == INITIAL_INTENSITY
    assert illuminated_curve.open_circuit_voltage.magnitude == INITIAL_VOC
    assert illuminated_curve.short_circuit_current_density.magnitude == pytest.approx(
        abs(INITIAL_ISC) / INITIAL_ACTIVE_AREA
    )
    assert illuminated_curve.fill_factor == INITIAL_FILL_FACTOR_PERCENT / 100
    assert illuminated_curve.efficiency == INITIAL_PCE
    assert illuminated_curve.potential_at_maximum_power_point.magnitude == INITIAL_V_MPP
    assert (
        illuminated_curve.current_density_at_maximun_power_point.magnitude
        == pytest.approx(abs(INITIAL_I_MPP) / INITIAL_ACTIVE_AREA)
    )


def test_normalization_publishes_hzb_solar_cell_results(tmp_path):
    measurement, archive = normalize_from_source(tmp_path, sweepme_source())
    dark_curve, illuminated_curve = measurement.jv_curve
    solar_cell = archive.results.properties.optoelectronic.solar_cell
    with pytest.warns(Warning):
        _, _, _, fallback_efficiency = illuminated_curve.cell_params()

    assert archive.results is not None
    assert solar_cell is not None
    assert magnitude_in(solar_cell.open_circuit_voltage, 'V') == INITIAL_VOC
    assert magnitude_in(
        solar_cell.short_circuit_current_density, 'mA / cm^2'
    ) == pytest.approx(abs(INITIAL_ISC) / INITIAL_ACTIVE_AREA)
    assert solar_cell.fill_factor == INITIAL_FILL_FACTOR_PERCENT / 100
    assert solar_cell.efficiency == INITIAL_PCE
    assert magnitude_in(solar_cell.illumination_intensity, 'mW / cm^2') == (
        INITIAL_INTENSITY
    )
    assert fallback_efficiency == pytest.approx(EXPECTED_FALLBACK_EFFICIENCY)
    assert fallback_efficiency != illuminated_curve.efficiency
    assert dark_curve.efficiency is None
    assert solar_cell.efficiency == illuminated_curve.efficiency

    measurement.normalize(archive, CapturingLogger())

    assert len(measurement.jv_curve) == EXPECTED_CURVE_COUNT
    assert archive.results.properties.optoelectronic.solar_cell is solar_cell
    assert solar_cell.efficiency == INITIAL_PCE
    assert magnitude_in(solar_cell.illumination_intensity, 'mW / cm^2') == (
        INITIAL_INTENSITY
    )


def test_normalization_materializes_hzb_style_and_sweepme_jv_figures(tmp_path):
    measurement, _ = normalize_from_source(tmp_path, sweepme_source())
    dark_curve, illuminated_curve = measurement.jv_curve

    assert_jv_figures(
        measurement,
        [('Dark', [-0.2, 0.1], [-1.5, 0.5])],
        [('Illuminated', [0.0, 0.45, 0.8], [-3.0, -1.25, 0.25])],
    )


def test_normalize_preserves_numeric_string_temperature_and_light_level(tmp_path):
    measurement, _ = normalize_from_source(
        tmp_path, sweepme_source(temperature='24.50', light_level='00680.0')
    )

    assert measurement.temperature_source == '24.50'
    assert measurement.light_level == '00680.0'


def test_normalize_replaces_science_and_preserves_user_fields(tmp_path):
    measurement = SweepMeJVMeasurement(
        data_file='source.json',
        name='User-provided title',
        description='User-provided description',
        samples=[CompositeSystemReference(name='User-provided sample')],
    )
    write_source(tmp_path, sweepme_source())
    archive = archive_for(tmp_path, measurement)
    logger = CapturingLogger()
    measurement.normalize(archive, logger)
    initial_samples = measurement.samples

    updated = sweepme_source(
        temperature=31,
        light_level='701.25',
        active_area=UPDATED_ACTIVE_AREA,
        illumination=UPDATED_ILLUMINATION,
    )
    updated['Conditions'].update(
        {
            'Sample ID': '0012-UPDATED',
            'Measurement ID': 'measurement_gamma',
            'Experiment Time': '2033-03-04T05:06:07.890',
            'Comment': 'Updated synthetic source comment',
            'Operator': 'Updated Operator',
        }
    )
    updated['Dark Curve'] = [
        {'index': 0, 'voltage': -0.1, 'current': -0.0005},
    ]
    updated['Illuminated Curve'] = [
        {'index': 0, 'voltage': 0.2, 'current': -0.001},
        {'index': 1, 'voltage': 0.7, 'current': 0.0002},
    ]
    updated['Calculated Values'] = [
        {
            'SAT': UPDATED_SATURATION,
            'P_MPP': UPDATED_POWER_AT_MPP,
            'PCE': UPDATED_PCE,
            'VOC': UPDATED_VOC,
            'ISC': UPDATED_ISC,
            'FF': UPDATED_FILL_FACTOR_PERCENT,
            'V_MPP': UPDATED_V_MPP,
            'I_MPP': UPDATED_I_MPP,
        }
    ]
    write_source(tmp_path, updated)
    measurement.normalize(archive, logger)
    serialized_after_refresh = measurement.m_to_dict()
    measurement.normalize(archive, logger)

    dark_curve, illuminated_curve = measurement.jv_curve
    assert measurement.sample_id == '0012-UPDATED'
    assert measurement.measurement_id == 'measurement_gamma'
    assert measurement.source_experiment_time == '2033-03-04T05:06:07.890'
    assert measurement.source_comment == 'Updated synthetic source comment'
    assert measurement.temperature_source == '31'
    assert measurement.light_level == '701.25'
    assert measurement.saturation == UPDATED_SATURATION
    assert measurement.power_at_mpp.magnitude == UPDATED_POWER_AT_MPP
    assert measurement.operator == 'Updated Operator'
    assert measurement.active_area.magnitude == UPDATED_ACTIVE_AREA
    assert measurement.intensity.magnitude == UPDATED_INTENSITY
    assert len(measurement.jv_curve) == EXPECTED_CURVE_COUNT
    assert magnitudes(dark_curve.current_density) == pytest.approx([-1.0])
    assert magnitudes(illuminated_curve.current_density) == pytest.approx([-2.0, 0.4])
    assert illuminated_curve.open_circuit_voltage.magnitude == UPDATED_VOC
    assert illuminated_curve.short_circuit_current_density.magnitude == pytest.approx(
        abs(UPDATED_ISC) / UPDATED_ACTIVE_AREA
    )
    assert illuminated_curve.fill_factor == UPDATED_FILL_FACTOR_PERCENT / 100
    assert illuminated_curve.efficiency == UPDATED_PCE
    assert illuminated_curve.potential_at_maximum_power_point.magnitude == UPDATED_V_MPP
    assert (
        illuminated_curve.current_density_at_maximun_power_point.magnitude
        == pytest.approx(abs(UPDATED_I_MPP) / UPDATED_ACTIVE_AREA)
    )
    assert illuminated_curve.light_intensity.magnitude == UPDATED_INTENSITY
    assert_jv_figures(
        measurement,
        [('Dark', [-0.1], [-1.0])],
        [('Illuminated', [0.2, 0.7], [-2.0, 0.4])],
    )
    solar_cell = archive.results.properties.optoelectronic.solar_cell
    assert magnitude_in(solar_cell.open_circuit_voltage, 'V') == UPDATED_VOC
    assert magnitude_in(
        solar_cell.short_circuit_current_density, 'mA / cm^2'
    ) == pytest.approx(abs(UPDATED_ISC) / UPDATED_ACTIVE_AREA)
    assert solar_cell.fill_factor == UPDATED_FILL_FACTOR_PERCENT / 100
    assert solar_cell.efficiency == UPDATED_PCE
    assert magnitude_in(solar_cell.illumination_intensity, 'mW / cm^2') == (
        UPDATED_INTENSITY
    )
    assert measurement.name == 'User-provided title'
    assert measurement.description == 'User-provided description'
    assert measurement.samples is initial_samples
    assert measurement.samples[0].name == 'User-provided sample'
    assert measurement.m_to_dict() == serialized_after_refresh


def test_normalize_logs_and_raises_for_malformed_changed_source(tmp_path):
    measurement, archive = normalize_from_source(tmp_path, sweepme_source())
    logger = CapturingLogger()
    snapshot = measurement.m_to_dict()
    dark_figure = measurement.jv_curve[0].figures[0].m_to_dict()
    illuminated_figure = measurement.jv_curve[1].figures[0].m_to_dict()
    combined_figure = measurement.figures[0].m_to_dict()
    (tmp_path / 'source.json').write_text('{malformed source')

    with pytest.raises(ValueError, match='Could not read SweepMe source file'):
        measurement.normalize(archive, logger)

    assert measurement.m_to_dict() == snapshot
    assert measurement.jv_curve[0].figures[0].m_to_dict() == dark_figure
    assert measurement.jv_curve[1].figures[0].m_to_dict() == illuminated_figure
    assert measurement.figures[0].m_to_dict() == combined_figure
    assert logger.errors[0][0] == 'Could not refresh SweepMe source metadata'


@pytest.mark.parametrize('active_area', [0, -INITIAL_ACTIVE_AREA])
def test_normalize_rejects_nonpositive_illuminated_area_before_mutation(
    tmp_path, active_area
):
    measurement, archive = normalize_from_source(tmp_path, sweepme_source())
    logger = CapturingLogger()
    snapshot = measurement.m_to_dict()
    write_source(tmp_path, sweepme_source(active_area=active_area))

    with pytest.raises(ValueError, match='Illuminated Area.*greater than zero'):
        measurement.normalize(archive, logger)

    assert measurement.m_to_dict() == snapshot
    assert logger.errors[0][0] == 'Could not refresh SweepMe source metadata'


@pytest.mark.parametrize(
    ('location', 'key', 'value'),
    [
        ('Conditions', 'Illuminated Area in cm²', float('nan')),
        ('Conditions', 'Illumination in W/m²', float('inf')),
        ('Calculated Values', 'PCE', float('nan')),
        ('Illuminated Curve', 'current', float('inf')),
    ],
    ids=[
        'non-finite-area',
        'non-finite-illumination',
        'non-finite-pce',
        'non-finite-current',
    ],
)
def test_normalize_rejects_nonfinite_scientific_values_before_mutation(
    tmp_path, location, key, value
):
    measurement, archive = normalize_from_source(tmp_path, sweepme_source())
    logger = CapturingLogger()
    snapshot = measurement.m_to_dict()
    invalid = sweepme_source()
    if location == 'Calculated Values':
        invalid[location][0][key] = value
    elif location in {'Dark Curve', 'Illuminated Curve'}:
        invalid[location][0][key] = value
    else:
        invalid[location][key] = value
    write_source(tmp_path, invalid)

    with pytest.raises(ValueError, match='finite number'):
        measurement.normalize(archive, logger)

    assert measurement.m_to_dict() == snapshot
    assert logger.errors[0][0] == 'Could not refresh SweepMe source metadata'


def test_normalize_rejects_missing_calculated_value_before_mutation(tmp_path):
    measurement, archive = normalize_from_source(tmp_path, sweepme_source())
    logger = CapturingLogger()
    snapshot = measurement.m_to_dict()
    incomplete = sweepme_source()
    del incomplete['Calculated Values'][0]['I_MPP']
    write_source(tmp_path, incomplete)

    with pytest.raises(ValueError, match='Calculated Values are incomplete'):
        measurement.normalize(archive, logger)

    assert measurement.m_to_dict() == snapshot
    assert logger.errors[0][0] == 'Could not refresh SweepMe source metadata'


def test_normalize_logs_and_raises_for_invalid_source_structure(tmp_path):
    measurement, archive = normalize_from_source(tmp_path, sweepme_source())
    logger = CapturingLogger()
    snapshot = measurement.m_to_dict()
    write_source(tmp_path, {'Conditions': {}, 'Calculated Values': []})

    with pytest.raises(ValueError, match='Conditions are incomplete'):
        measurement.normalize(archive, logger)

    assert measurement.m_to_dict() == snapshot
    assert logger.errors[0][0] == 'Could not refresh SweepMe source metadata'


def test_normalize_without_data_file_delegates_to_the_parent_normalizer(tmp_path):
    measurement = SweepMeJVMeasurement()
    archive = archive_for(tmp_path, measurement)
    logger = CapturingLogger()

    measurement.normalize(archive, logger)

    assert logger.errors == []
    assert measurement.sample_id is None
    assert measurement.measurement_id is None


def test_normalize_logs_and_raises_for_missing_source_file(tmp_path):
    measurement = SweepMeJVMeasurement(data_file='missing.json')
    archive = archive_for(tmp_path, measurement)
    logger = CapturingLogger()

    with pytest.raises(ValueError, match='Could not read SweepMe source file'):
        measurement.normalize(archive, logger)

    assert logger.errors[0][0] == 'Could not refresh SweepMe source metadata'
