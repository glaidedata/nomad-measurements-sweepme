import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nomad.datamodel.metainfo.eln import ElnParserRawFile
from nomad.parsing.parser import ElnMatchingParser

from nomad_measurements_sweepme.schema_packages.schema_package import (
    SweepMeJVMeasurement,
)

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger


class SweepMeParser(ElnMatchingParser):
    """Create editable SweepMe measurement archives from SweepMe JSON exports."""

    _required_top_level_keys = {
        'Conditions',
        'Dark Curve',
        'Illuminated Curve',
        'Calculated Values',
    }
    _required_condition_keys = {
        'Sample ID',
        'Measurement ID',
        'Illumination in W/m²',
        'Illuminated Area in cm²',
    }
    _required_curve_keys = {'index', 'voltage', 'current'}

    def __init__(self, **kwargs):
        super().__init__(
            eln_m_def=SweepMeJVMeasurement.m_def.qualified_name(),
            raw_file_m_def=ElnParserRawFile.m_def.qualified_name(),
            update=True,
            data_type='SweepMe JSON',
            mainfile_name_re=r'.*\.json',
            **kwargs,
        )

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @classmethod
    def _is_curve(cls, value: Any) -> bool:
        return (
            isinstance(value, list)
            and bool(value)
            and all(
                isinstance(point, dict)
                and cls._required_curve_keys.issubset(point)
                and isinstance(point['index'], int)
                and not isinstance(point['index'], bool)
                and cls._is_number(point['voltage'])
                and cls._is_number(point['current'])
                for point in value
            )
        )

    @classmethod
    def _is_sweepme_document(cls, document: Any) -> bool:
        if not isinstance(document, dict) or not cls._required_top_level_keys.issubset(
            document
        ):
            return False

        conditions = document['Conditions']
        calculated_values = document['Calculated Values']
        return (
            isinstance(conditions, dict)
            and cls._required_condition_keys.issubset(conditions)
            and cls._is_curve(document['Dark Curve'])
            and cls._is_curve(document['Illuminated Curve'])
            and isinstance(calculated_values, list)
            and bool(calculated_values)
            and isinstance(calculated_values[0], dict)
            and 'ISC' in calculated_values[0]
            and 'JSC' not in calculated_values[0]
        )

    def is_mainfile(
        self,
        filename: str,
        mime: str,
        buffer: bytes,
        decoded_buffer: str,
        compression: str | None = None,
    ) -> bool:
        del mime, buffer, decoded_buffer, compression
        path = Path(filename)
        if path.suffix != '.json' or path.name.endswith('.archive.json'):
            return False

        try:
            with path.open(encoding='utf-8') as file:
                document = json.load(file)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False

        return self._is_sweepme_document(document)

    def _is_own_editable_archive(
        self, content: dict[str, Any], mainfile: str, archive: 'EntryArchive'
    ) -> bool:
        data = content.get('data')
        return (
            isinstance(data, dict)
            and data.get('m_def') == self.eln_m_def
            and data.get('data_file') == archive.m_context.get_relative_path(mainfile)
        )

    def parse(
        self,
        mainfile: str,
        archive: 'EntryArchive',
        logger: 'BoundLogger',
        child_archives: dict[str, 'EntryArchive'] | None = None,
    ) -> None:
        del logger, child_archives
        context = archive.m_context
        editable_archive = self.eln_name(mainfile, archive)

        if context.raw_path_exists(editable_archive):
            with context.update_entry(editable_archive) as content:
                if not self._is_own_editable_archive(content, mainfile, archive):
                    raise ValueError(
                        f'Refusing to reuse {editable_archive}: it is not the '
                        'SweepMe editable archive for this raw file.'
                    )

        super().parse(mainfile, archive, logger=None)
