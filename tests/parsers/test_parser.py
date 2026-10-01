import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.context import Context
from nomad.datamodel.metainfo.eln import ElnParserRawFile

from nomad_measurements_sweepme.parsers.parser import SweepMeParser
from nomad_measurements_sweepme.schema_packages.schema_package import (
    SweepMeJVMeasurement,
)


class LocalRawContext(Context):
    def __init__(self, raw_directory: Path):
        super().__init__()
        self.raw_directory = raw_directory

    def get_relative_path(self, path: str) -> str:
        return str(Path(path).relative_to(self.raw_directory))

    def get_reference(self, path: str) -> str:
        return f'../uploads/synthetic/archive/{path}'

    def raw_path_exists(self, path: str) -> bool:
        return (self.raw_directory / path).exists()

    @contextmanager
    def update_entry(self, path: str, write: bool = False, process: bool = False):
        del process
        archive_path = self.raw_directory / path
        content = json.loads(archive_path.read_text()) if archive_path.exists() else {}
        yield content
        if write:
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text(json.dumps(content, indent=2))


def sweepme_document() -> dict:
    return {
        'Conditions': {
            'Sample ID': '0009-Z',
            'Measurement ID': 'synthetic_measurement',
            'Illumination in W/m²': 730.0,
            'Illuminated Area in cm²': 0.42,
        },
        'Dark Curve': [
            {'index': 0, 'voltage': -0.2, 'current': -0.001},
            {'index': 1, 'voltage': 0.0, 'current': 0.0},
        ],
        'Illuminated Curve': [
            {'index': 0, 'voltage': -0.2, 'current': -0.0008},
            {'index': 1, 'voltage': 0.0, 'current': -0.0002},
            {'index': 2, 'voltage': 0.3, 'current': 0.0},
        ],
        'Calculated Values': [{'ISC': 2.4}],
    }


def write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))


def parser_matches(parser: SweepMeParser, path: Path) -> bool:
    content = path.read_bytes()
    return parser.is_mainfile(
        str(path), 'application/json', content, content.decode('utf-8')
    )


def archive_for(raw_directory: Path) -> EntryArchive:
    return EntryArchive(
        m_context=LocalRawContext(raw_directory),
        metadata=EntryMetadata(upload_id='synthetic-upload', entry_id='raw-entry'),
    )


@pytest.mark.parametrize('relative_path', ['measurement.json', 'nested/run-004.json'])
def test_matches_valid_sweepme_json_by_content(tmp_path, relative_path):
    path = tmp_path / relative_path
    write_json(path, sweepme_document())

    assert parser_matches(SweepMeParser(), path)


@pytest.mark.parametrize(
    'document',
    [
        {'kind': 'unrelated'},
        {
            'Conditions': {},
            'Dark Curve': [],
            'Illuminated Curve': [],
            'Calculated Values': [],
        },
        {
            **sweepme_document(),
            'Calculated Values': [{'JSC': 2.4}],
        },
    ],
    ids=['unrelated', 'missing-required-structure', 'legacy-jsc-only'],
)
def test_rejects_non_matching_json(tmp_path, document):
    path = tmp_path / 'candidate.json'
    write_json(path, document)

    assert not parser_matches(SweepMeParser(), path)


@pytest.mark.parametrize(
    ('curve_name', 'field', 'value'),
    [
        ('Dark Curve', 'index', 'not-an-index'),
        ('Illuminated Curve', 'voltage', 'not-a-voltage'),
        ('Dark Curve', 'current', 'not-a-current'),
    ],
    ids=['string-index', 'non-numeric-voltage', 'non-numeric-current'],
)
def test_rejects_invalid_curve_point_types(tmp_path, curve_name, field, value):
    document = sweepme_document()
    document[curve_name][0][field] = value
    path = tmp_path / 'invalid-point.json'
    write_json(path, document)

    assert not parser_matches(SweepMeParser(), path)


def test_rejects_malformed_json_and_generated_archives(tmp_path):
    malformed = tmp_path / 'malformed.json'
    malformed.write_text('{not valid json')
    generated_archive = tmp_path / 'measurement.archive.json'
    write_json(generated_archive, sweepme_document())
    parser = SweepMeParser()

    assert not parser_matches(parser, malformed)
    assert not parser_matches(parser, generated_archive)


def test_parse_creates_editable_archive_and_raw_pointer(tmp_path):
    raw_file = tmp_path / 'nested' / 'measurement.json'
    write_json(raw_file, sweepme_document())
    raw_bytes = raw_file.read_bytes()
    archive = archive_for(tmp_path)

    SweepMeParser().parse(str(raw_file), archive, logger=None)

    editable_archive = tmp_path / 'nested' / 'measurement.archive.json'
    editable_content = json.loads(editable_archive.read_text())
    assert raw_file.read_bytes() == raw_bytes
    assert editable_content['data'] == {
        'm_def': SweepMeJVMeasurement.m_def.qualified_name(),
        'data_file': 'nested/measurement.json',
    }
    assert isinstance(archive.data, ElnParserRawFile)
    assert archive.data.eln.m_serialize_proxy_value() == (
        '../uploads/synthetic/archive/nested/measurement.archive.json#/data'
    )


def test_repeated_parsing_reuses_the_same_editable_archive(tmp_path):
    raw_file = tmp_path / 'measurement.json'
    write_json(raw_file, sweepme_document())
    parser = SweepMeParser()

    parser.parse(str(raw_file), archive_for(tmp_path), logger=None)
    parser.parse(str(raw_file), archive_for(tmp_path), logger=None)

    assert list(tmp_path.glob('measurement.archive.json')) == [
        tmp_path / 'measurement.archive.json'
    ]


def test_rejects_unrelated_existing_editable_archive(tmp_path):
    raw_file = tmp_path / 'measurement.json'
    write_json(raw_file, sweepme_document())
    editable_archive = tmp_path / 'measurement.archive.json'
    unrelated_content = {
        'data': {'m_def': 'nomad.datamodel.data.EntryData', 'note': 'keep'}
    }
    write_json(editable_archive, unrelated_content)
    archive = archive_for(tmp_path)

    with pytest.raises(ValueError, match='Refusing to reuse'):
        SweepMeParser().parse(str(raw_file), archive, logger=None)

    assert json.loads(editable_archive.read_text()) == unrelated_content
    assert archive.data is None
