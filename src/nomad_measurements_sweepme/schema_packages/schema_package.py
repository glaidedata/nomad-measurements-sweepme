from baseclasses.solar_energy.jvmeasurement import JVMeasurement
from nomad.datamodel.data import EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Quantity, SchemaPackage

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


m_package.__init_metainfo__()
