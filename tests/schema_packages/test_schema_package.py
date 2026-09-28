from baseclasses.solar_energy.jvmeasurement import JVMeasurement
from nomad.datamodel.data import EntryData

from nomad_measurements_sweepme.schema_packages import schema_package_entry_point
from nomad_measurements_sweepme.schema_packages.schema_package import (
    SweepMeJVMeasurement,
    m_package,
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
        saturation=1.125,
        power_at_mpp=6.75,
    )

    serialized = measurement.m_to_dict()

    assert serialized['sample_id'] == '0017-XY'
    assert serialized['measurement_id'] == 'run_alpha_07'
    assert serialized['source_experiment_time'] == '2031-04-15T08:09:10.123456'
    assert serialized['source_comment'] == 'Synthetic schema test comment'
    assert serialized['temperature_source'] == '42'
    assert serialized['light_level'] == '987'
    assert serialized['saturation'] == 1.125
    assert serialized['power_at_mpp'] == 6.75
