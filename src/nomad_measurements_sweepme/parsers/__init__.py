from nomad.config.models.plugins import ParserEntryPoint


class SweepMeParserEntryPoint(ParserEntryPoint):
    def load(self):
        from nomad_measurements_sweepme.parsers.parser import SweepMeParser

        return SweepMeParser()


parser_entry_point = SweepMeParserEntryPoint(
    name='SweepMe JSON parser',
    description='Creates editable SweepMe JV archives from SweepMe JSON exports.',
    mainfile_name_re=r'.*\.json',
)
