"""BLE notify parsers split from coffee/__init__.py.

Each parser pulls a frame from a notify char's raw bytes via
`coffee.bookoo.parse_*` and writes derived state to
`coffee.state.State`.  Parsers run in IRQ context — keep allocation
to a minimum and never block.

Re-exported by name so the IRQ char_specs in coffee/__init__.py
continue to resolve as `_parse_scale`, `_parse_em_extraction`,
`_parse_em_status`.
"""
from .scale import parse_scale as _parse_scale
from .pressure import (
    parse_em_extraction as _parse_em_extraction,
    parse_em_status as _parse_em_status,
)
