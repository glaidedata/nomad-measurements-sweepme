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


def sweepme_source(temperature=24.5, light_level=680) -> dict:
    return {
        'Conditions': {
            'Sample ID': '0008-SYN',
            'Measurement ID': 'measurement_beta',
            'Experiment Time': '2032-02-03T04:05:06.789',
            'Comment': 'Synthetic source comment',
            'Temperature': temperature,
            'Light level': light_level,
        },
        'Calculated Values': [
            {'SAT': INITIAL_SATURATION, 'P_MPP': INITIAL_POWER_AT_MPP}
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


def test_normalize_populates_parser_owned_source_metadata(tmp_path):
    measurement, _ = normalize_from_source(tmp_path, sweepme_source())

    assert measurement.sample_id == '0008-SYN'
    assert measurement.measurement_id == 'measurement_beta'
    assert measurement.source_experiment_time == '2032-02-03T04:05:06.789'
    assert measurement.source_comment == 'Synthetic source comment'
    assert measurement.temperature_source == '24.5'
    assert measurement.light_level == '680'
    assert measurement.saturation == INITIAL_SATURATION
    assert measurement.power_at_mpp.magnitude == INITIAL_POWER_AT_MPP
    assert measurement.active_area is None
    assert measurement.intensity is None
    assert measurement.jv_curve == []


def test_normalize_preserves_numeric_string_temperature_and_light_level(tmp_path):
    measurement, _ = normalize_from_source(
        tmp_path, sweepme_source(temperature='24.50', light_level='00680.0')
    )

    assert measurement.temperature_source == '24.50'
    assert measurement.light_level == '00680.0'


def test_normalize_refreshes_parser_owned_fields_and_preserves_user_fields(tmp_path):
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

    updated = sweepme_source(temperature=31, light_level='701.25')
    updated['Conditions']['Sample ID'] = '0012-UPDATED'
    updated['Conditions']['Measurement ID'] = 'measurement_gamma'
    updated['Conditions']['Experiment Time'] = '2033-03-04T05:06:07.890'
    updated['Conditions']['Comment'] = 'Updated synthetic source comment'
    updated['Calculated Values'] = [
        {'SAT': UPDATED_SATURATION, 'P_MPP': UPDATED_POWER_AT_MPP}
    ]
    write_source(tmp_path, updated)
    measurement.normalize(archive, logger)
    serialized_after_refresh = measurement.m_to_dict()
    measurement.normalize(archive, logger)

    assert measurement.sample_id == '0012-UPDATED'
    assert measurement.measurement_id == 'measurement_gamma'
    assert measurement.source_experiment_time == '2033-03-04T05:06:07.890'
    assert measurement.source_comment == 'Updated synthetic source comment'
    assert measurement.temperature_source == '31'
    assert measurement.light_level == '701.25'
    assert measurement.saturation == UPDATED_SATURATION
    assert measurement.power_at_mpp.magnitude == UPDATED_POWER_AT_MPP
    assert measurement.name == 'User-provided title'
    assert measurement.description == 'User-provided description'
    assert measurement.samples is initial_samples
    assert measurement.samples[0].name == 'User-provided sample'
    assert measurement.m_to_dict() == serialized_after_refresh


def test_normalize_logs_and_raises_for_malformed_changed_source(tmp_path):
    measurement, archive = normalize_from_source(tmp_path, sweepme_source())
    logger = CapturingLogger()
    (tmp_path / 'source.json').write_text('{malformed source')

    with pytest.raises(ValueError, match='Could not read SweepMe source file'):
        measurement.normalize(archive, logger)

    assert measurement.sample_id == '0008-SYN'
    assert logger.errors == [
        (
            'Could not refresh SweepMe source metadata',
            {
                'data_file': 'source.json',
                'error': "Could not read SweepMe source file 'source.json'.",
            },
        )
    ]


def test_normalize_logs_and_raises_for_invalid_source_structure(tmp_path):
    measurement, archive = normalize_from_source(tmp_path, sweepme_source())
    logger = CapturingLogger()
    write_source(tmp_path, {'Conditions': {}, 'Calculated Values': []})

    with pytest.raises(ValueError, match='Conditions are incomplete'):
        measurement.normalize(archive, logger)

    assert measurement.measurement_id == 'measurement_beta'
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
