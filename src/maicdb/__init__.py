"""MAIC-DB: Mechanically Activated Ion Channel Database.

Schema and tooling for the MAIC-DB project. This package currently provides
the relational schema (SQLAlchemy 2.0 ORM targeting SQLite) that anchors the
database on the four documented modules — Identity, Biophysics, Pharmacology,
and Disease — with the Mechano-Gating Card (P50/T50/X50, tau, conductance) and
the MIMIC stimulus-metadata standard as the core value-add.

Data loading is a separate (future) concern; this package defines the schema
and validates it against the real Piezo1 reference dataset.
"""

__version__ = "0.1.0"
