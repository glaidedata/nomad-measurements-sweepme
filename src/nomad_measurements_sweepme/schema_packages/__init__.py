from nomad.config.models.plugins import SchemaPackageEntryPoint


class SweepMeSchemaPackageEntryPoint(SchemaPackageEntryPoint):
    def load(self):
        from nomad_measurements_sweepme.schema_packages.schema_package import m_package

        return m_package


schema_package_entry_point = SweepMeSchemaPackageEntryPoint(
    name='SweepMe schema package',
    description='Schema package for SweepMe measurements.',
)
