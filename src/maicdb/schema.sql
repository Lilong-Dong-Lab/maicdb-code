CREATE TABLE db_meta (
	"key" VARCHAR(64) NOT NULL, 
	value TEXT NOT NULL, 
	PRIMARY KEY ("key")
)

CREATE TABLE external_reference (
	id INTEGER NOT NULL, 
	entity_type VARCHAR(21) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	source_db VARCHAR(15) NOT NULL, 
	external_id TEXT NOT NULL, 
	url TEXT, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_xref_entity_source_id UNIQUE (entity_type, entity_id, source_db, external_id), 
	CONSTRAINT entitytype CHECK (entity_type IN ('CHANNEL', 'STRUCTURE', 'COMPOUND', 'VARIANT', 'BIOPHYSICS_EXPERIMENT')), 
	CONSTRAINT sourcedb CHECK (source_db IN ('UNIPROT', 'PDB', 'ALPHAFOLD', 'HGNC', 'NCBI_GENE', 'CHEMBL_TARGET', 'CHEMBL_MOLECULE', 'PUBCHEM', 'BINDINGDB', 'IUPHAR', 'CLINVAR', 'OMIM', 'MECHANOBASE', 'MECHANOPRODB', 'ICG', 'CHANNELPEDIA', 'TRIP', 'GO', 'DOI', 'LITERATURE'))
)

CREATE INDEX ix_external_reference_entity_id ON external_reference (entity_id)

CREATE INDEX ix_external_reference_entity_type ON external_reference (entity_type)

CREATE INDEX ix_external_reference_source_db ON external_reference (source_db)

CREATE INDEX ix_xref_entity ON external_reference (entity_type, entity_id)

CREATE INDEX ix_xref_reverse ON external_reference (source_db, external_id)

CREATE TABLE publication (
	id INTEGER NOT NULL, 
	doi TEXT, 
	title TEXT, 
	journal TEXT, 
	year INTEGER, 
	authors JSON, 
	pmid INTEGER, 
	citation_text TEXT, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id)
)

CREATE UNIQUE INDEX ix_publication_doi ON publication (doi)

CREATE INDEX ix_publication_pmid ON publication (pmid)

CREATE TABLE channel (
	id INTEGER NOT NULL, 
	maicdb_id VARCHAR(24) NOT NULL, 
	gene_symbol VARCHAR(64) NOT NULL, 
	gene_aliases JSON, 
	uniprot_accession VARCHAR(16), 
	protein_name TEXT, 
	organism TEXT NOT NULL, 
	organism_taxid INTEGER, 
	ncbi_gene_id INTEGER, 
	hgnc_id VARCHAR(32), 
	sequence_length INTEGER, 
	family VARCHAR(13) NOT NULL, 
	activation_mechanism VARCHAR(19), 
	go_terms JSON, 
	ortholog_group VARCHAR(64), 
	summary TEXT, 
	source_db VARCHAR(15), 
	collected_date DATE, 
	publication_id INTEGER, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_channel_gene_organism UNIQUE (gene_symbol, organism_taxid), 
	UNIQUE (maicdb_id), 
	CONSTRAINT family CHECK (family IN ('PIEZO', 'TRP', 'K2P', 'OSCA_TMEM63', 'MSCL_MSCS', 'TMC', 'DEG_ENaC_ASIC', 'OTHER')), 
	CONSTRAINT activationmechanism CHECK (activation_mechanism IN ('FORCE_FROM_LIPIDS', 'FORCE_FROM_FILAMENT', 'HYBRID', 'UNKNOWN', 'DISPUTED')), 
	CONSTRAINT sourcedb CHECK (source_db IN ('UNIPROT', 'PDB', 'ALPHAFOLD', 'HGNC', 'NCBI_GENE', 'CHEMBL_TARGET', 'CHEMBL_MOLECULE', 'PUBCHEM', 'BINDINGDB', 'IUPHAR', 'CLINVAR', 'OMIM', 'MECHANOBASE', 'MECHANOPRODB', 'ICG', 'CHANNELPEDIA', 'TRIP', 'GO', 'DOI', 'LITERATURE')), 
	FOREIGN KEY(publication_id) REFERENCES publication (id) ON DELETE SET NULL
)

CREATE INDEX ix_channel_activation_mechanism ON channel (activation_mechanism)

CREATE INDEX ix_channel_family ON channel (family)

CREATE INDEX ix_channel_gene_symbol ON channel (gene_symbol)

CREATE INDEX ix_channel_ncbi_gene_id ON channel (ncbi_gene_id)

CREATE INDEX ix_channel_organism_taxid ON channel (organism_taxid)

CREATE INDEX ix_channel_ortholog_group ON channel (ortholog_group)

CREATE INDEX ix_channel_source_db ON channel (source_db)

CREATE UNIQUE INDEX ix_channel_uniprot_accession ON channel (uniprot_accession)

CREATE TABLE compound (
	id INTEGER NOT NULL, 
	maicdb_id VARCHAR(24) NOT NULL, 
	name TEXT NOT NULL, 
	chembl_id VARCHAR(32), 
	pubchem_cid INTEGER, 
	bindingdb_id VARCHAR(32), 
	smiles TEXT, 
	inchikey VARCHAR(27), 
	inchi TEXT, 
	molecular_weight FLOAT, 
	clogp FLOAT, 
	tpsa FLOAT, 
	hbd INTEGER, 
	hba INTEGER, 
	rotatable_bonds INTEGER, 
	aromatic_rings INTEGER, 
	heavy_atoms INTEGER, 
	compound_type VARCHAR(17), 
	source TEXT, 
	lipinski_pass BOOLEAN, 
	veber_pass BOOLEAN, 
	is_duplicate BOOLEAN, 
	natural_source TEXT, 
	peptide_sequence TEXT, 
	source_db VARCHAR(15), 
	collected_date DATE, 
	publication_id INTEGER, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (maicdb_id), 
	CONSTRAINT compoundtype CHECK (compound_type IN ('ACTIVATOR', 'INHIBITOR_BLOCKER', 'INHIBITOR', 'ANTAGONIST', 'POTENTIATOR', 'UNKNOWN', 'UNCLASSIFIED')), 
	CONSTRAINT sourcedb CHECK (source_db IN ('UNIPROT', 'PDB', 'ALPHAFOLD', 'HGNC', 'NCBI_GENE', 'CHEMBL_TARGET', 'CHEMBL_MOLECULE', 'PUBCHEM', 'BINDINGDB', 'IUPHAR', 'CLINVAR', 'OMIM', 'MECHANOBASE', 'MECHANOPRODB', 'ICG', 'CHANNELPEDIA', 'TRIP', 'GO', 'DOI', 'LITERATURE')), 
	FOREIGN KEY(publication_id) REFERENCES publication (id) ON DELETE SET NULL
)

CREATE INDEX ix_compound_chembl_id ON compound (chembl_id)

CREATE INDEX ix_compound_compound_type ON compound (compound_type)

CREATE UNIQUE INDEX ix_compound_inchikey ON compound (inchikey)

CREATE INDEX ix_compound_name ON compound (name)

CREATE INDEX ix_compound_pubchem_cid ON compound (pubchem_cid)

CREATE INDEX ix_compound_source_db ON compound (source_db)

CREATE TABLE bioactivity (
	id INTEGER NOT NULL, 
	maicdb_id VARCHAR(24) NOT NULL, 
	compound_id INTEGER NOT NULL, 
	channel_id INTEGER NOT NULL, 
	target_chembl_id VARCHAR(32), 
	activity_type VARCHAR(16), 
	activity_value FLOAT, 
	activity_units TEXT, 
	pchembl FLOAT, 
	relation VARCHAR(4), 
	assay_description TEXT, 
	assay_format VARCHAR(19), 
	cell_line TEXT, 
	target_species TEXT, 
	source_db VARCHAR(15), 
	collected_date DATE, 
	publication_id INTEGER, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME, 
	measurement_id TEXT, 
	evidence_quote TEXT, 
	evidence_location TEXT, 
	confidence TEXT, 
	extractor_note TEXT, 
	condition_key TEXT, 
	n TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_bioactivity_dedup UNIQUE (compound_id, channel_id, activity_type, activity_value, assay_description), 
	UNIQUE (maicdb_id), 
	FOREIGN KEY(compound_id) REFERENCES compound (id) ON DELETE CASCADE, 
	FOREIGN KEY(channel_id) REFERENCES channel (id) ON DELETE CASCADE, 
	CONSTRAINT activitytype CHECK (activity_type IN ('EC50', 'IC50', 'KD', 'KI', 'KB', 'PEC50', 'POTENCY', 'ACTIVITY', 'INHIBITION', 'AGONIST_ACTIVITY', 'BINDING_AFFINITY', 'GI50', 'OTHER')), 
	CONSTRAINT assayformat CHECK (assay_format IN ('FLIPR', 'SPR', 'PATCH_CLAMP', 'CALCIUM_IMAGING', 'TEVC', 'ELECTROPHYSIOLOGY', 'RADIOLIGAND_BINDING', 'FLUORESCENCE', 'UNKNOWN')), 
	CONSTRAINT sourcedb CHECK (source_db IN ('UNIPROT', 'PDB', 'ALPHAFOLD', 'HGNC', 'NCBI_GENE', 'CHEMBL_TARGET', 'CHEMBL_MOLECULE', 'PUBCHEM', 'BINDINGDB', 'IUPHAR', 'CLINVAR', 'OMIM', 'MECHANOBASE', 'MECHANOPRODB', 'ICG', 'CHANNELPEDIA', 'TRIP', 'GO', 'DOI', 'LITERATURE')), 
	FOREIGN KEY(publication_id) REFERENCES publication (id) ON DELETE SET NULL
)

CREATE INDEX ix_bioactivity_activity_type ON bioactivity (activity_type)

CREATE INDEX ix_bioactivity_assay_format ON bioactivity (assay_format)

CREATE INDEX ix_bioactivity_channel_id ON bioactivity (channel_id)

CREATE INDEX ix_bioactivity_compound_id ON bioactivity (compound_id)

CREATE INDEX ix_bioactivity_condition_key ON bioactivity (condition_key)

CREATE UNIQUE INDEX ix_bioactivity_measurement_id ON bioactivity (measurement_id)

CREATE INDEX ix_bioactivity_source_db ON bioactivity (source_db)

CREATE TABLE structure (
	id INTEGER NOT NULL, 
	maicdb_id VARCHAR(24) NOT NULL, 
	channel_id INTEGER NOT NULL, 
	pdb_id VARCHAR(8), 
	structure_source VARCHAR(11) NOT NULL, 
	alphafold_model_id VARCHAR(64), 
	alphafold_plddt_mean FLOAT, 
	title TEXT, 
	method TEXT, 
	resolution_a FLOAT, 
	organism TEXT, 
	residues_covered TEXT, 
	coverage_pct FLOAT, 
	num_chains INTEGER, 
	ligands TEXT, 
	has_inhibitor BOOLEAN NOT NULL, 
	auxiliary_subunits JSON, 
	mutation TEXT, 
	conformational_state TEXT, 
	deposition_date DATE, 
	release_date DATE, 
	doi TEXT, 
	source_db VARCHAR(15), 
	collected_date DATE, 
	publication_id INTEGER, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (maicdb_id), 
	FOREIGN KEY(channel_id) REFERENCES channel (id) ON DELETE CASCADE, 
	CONSTRAINT structuresource CHECK (structure_source IN ('PDB', 'ALPHAFOLD', 'SWISS_MODEL', 'OTHER')), 
	CONSTRAINT sourcedb CHECK (source_db IN ('UNIPROT', 'PDB', 'ALPHAFOLD', 'HGNC', 'NCBI_GENE', 'CHEMBL_TARGET', 'CHEMBL_MOLECULE', 'PUBCHEM', 'BINDINGDB', 'IUPHAR', 'CLINVAR', 'OMIM', 'MECHANOBASE', 'MECHANOPRODB', 'ICG', 'CHANNELPEDIA', 'TRIP', 'GO', 'DOI', 'LITERATURE')), 
	FOREIGN KEY(publication_id) REFERENCES publication (id) ON DELETE SET NULL
)

CREATE INDEX ix_structure_channel_id ON structure (channel_id)

CREATE INDEX ix_structure_conformational_state ON structure (conformational_state)

CREATE INDEX ix_structure_doi ON structure (doi)

CREATE UNIQUE INDEX ix_structure_pdb_id ON structure (pdb_id)

CREATE INDEX ix_structure_source_db ON structure (source_db)

CREATE INDEX ix_structure_structure_source ON structure (structure_source)

CREATE TABLE unmapped_measurement (
	id INTEGER NOT NULL, 
	maicdb_id VARCHAR(24) NOT NULL, 
	channel_id INTEGER NOT NULL, 
	parameter_kind TEXT NOT NULL, 
	value FLOAT, 
	unit TEXT, 
	adjudication TEXT, 
	measurement_id TEXT, 
	evidence_quote TEXT, 
	evidence_location TEXT, 
	confidence TEXT, 
	extractor_note TEXT, 
	condition_key TEXT, 
	n TEXT, 
	source_db VARCHAR(15), 
	collected_date DATE, 
	publication_id INTEGER, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (maicdb_id), 
	FOREIGN KEY(channel_id) REFERENCES channel (id) ON DELETE CASCADE, 
	CONSTRAINT sourcedb CHECK (source_db IN ('UNIPROT', 'PDB', 'ALPHAFOLD', 'HGNC', 'NCBI_GENE', 'CHEMBL_TARGET', 'CHEMBL_MOLECULE', 'PUBCHEM', 'BINDINGDB', 'IUPHAR', 'CLINVAR', 'OMIM', 'MECHANOBASE', 'MECHANOPRODB', 'ICG', 'CHANNELPEDIA', 'TRIP', 'GO', 'DOI', 'LITERATURE')), 
	FOREIGN KEY(publication_id) REFERENCES publication (id) ON DELETE SET NULL
)

CREATE INDEX ix_unmapped_measurement_channel_id ON unmapped_measurement (channel_id)

CREATE INDEX ix_unmapped_measurement_condition_key ON unmapped_measurement (condition_key)

CREATE UNIQUE INDEX ix_unmapped_measurement_measurement_id ON unmapped_measurement (measurement_id)

CREATE INDEX ix_unmapped_measurement_source_db ON unmapped_measurement (source_db)

CREATE TABLE variant (
	id INTEGER NOT NULL, 
	maicdb_id VARCHAR(24) NOT NULL, 
	channel_id INTEGER NOT NULL, 
	hgvs_protein TEXT, 
	hgvs_coding TEXT, 
	mutation_short VARCHAR(32), 
	position INTEGER, 
	ref_aa VARCHAR(8), 
	alt_aa VARCHAR(8), 
	variant_type VARCHAR(17), 
	organism TEXT, 
	organism_taxid INTEGER, 
	clinvar_accession VARCHAR(32), 
	clinvar_significance VARCHAR(22), 
	omim_id VARCHAR(16), 
	dbsnp_rs VARCHAR(16), 
	phenotype TEXT, 
	phenotype_mim VARCHAR(16), 
	functional_effect VARCHAR(26), 
	delta_p50_value FLOAT, 
	delta_p50_unit VARCHAR(5), 
	notes TEXT, 
	source_db VARCHAR(15), 
	collected_date DATE, 
	publication_id INTEGER, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (maicdb_id), 
	FOREIGN KEY(channel_id) REFERENCES channel (id) ON DELETE CASCADE, 
	CONSTRAINT varianttype CHECK (variant_type IN ('MISSENSE', 'NONSENSE', 'FRAMESHIFT', 'INFRAME_DELETION', 'INFRAME_INSERTION', 'SPLICE_DONOR', 'SPLICE_ACCEPTOR', 'SYNONYMOUS', 'STOP_GAIN', 'STOP_LOSS', 'START_LOSS', 'DUPLICATION', 'DELETION', 'INDEL', 'UTR')), 
	CONSTRAINT clinvarsignificance CHECK (clinvar_significance IN ('PATHOGENIC', 'LIKELY_PATHOGENIC', 'UNCERTAIN_SIGNIFICANCE', 'LIKELY_BENIGN', 'BENIGN', 'CONFLICTING', 'RISK_FACTOR', 'ASSOCIATION', 'NOT_PROVIDED', 'OTHER')), 
	CONSTRAINT functionaleffect CHECK (functional_effect IN ('GAIN_OF_FUNCTION', 'LOSS_OF_FUNCTION', 'MIXED_GOF_LOF', 'NO_EFFECT', 'GAIN_OF_MECHANOSENSITIVITY', 'LOSS_OF_MECHANOSENSITIVITY', 'UNKNOWN')), 
	CONSTRAINT pressureunit CHECK (delta_p50_unit IN ('mmHg', 'kPa', 'Pa', 'mbar', 'cmH2O', 'psi')), 
	CONSTRAINT sourcedb CHECK (source_db IN ('UNIPROT', 'PDB', 'ALPHAFOLD', 'HGNC', 'NCBI_GENE', 'CHEMBL_TARGET', 'CHEMBL_MOLECULE', 'PUBCHEM', 'BINDINGDB', 'IUPHAR', 'CLINVAR', 'OMIM', 'MECHANOBASE', 'MECHANOPRODB', 'ICG', 'CHANNELPEDIA', 'TRIP', 'GO', 'DOI', 'LITERATURE')), 
	FOREIGN KEY(publication_id) REFERENCES publication (id) ON DELETE SET NULL
)

CREATE INDEX ix_variant_channel_id ON variant (channel_id)

CREATE INDEX ix_variant_clinvar_accession ON variant (clinvar_accession)

CREATE INDEX ix_variant_clinvar_significance ON variant (clinvar_significance)

CREATE INDEX ix_variant_dbsnp_rs ON variant (dbsnp_rs)

CREATE INDEX ix_variant_functional_effect ON variant (functional_effect)

CREATE INDEX ix_variant_mutation_short ON variant (mutation_short)

CREATE INDEX ix_variant_organism_taxid ON variant (organism_taxid)

CREATE INDEX ix_variant_source_db ON variant (source_db)

CREATE INDEX ix_variant_variant_type ON variant (variant_type)

CREATE TABLE biophysics_experiment (
	id INTEGER NOT NULL, 
	maicdb_id VARCHAR(24) NOT NULL, 
	channel_id INTEGER NOT NULL, 
	structure_id INTEGER, 
	compound_id INTEGER, 
	variant_id INTEGER, 
	experiment_label TEXT, 
	parameter_set VARCHAR(16), 
	p50_value FLOAT, 
	p50_unit VARCHAR(5), 
	t50_value FLOAT, 
	t50_unit VARCHAR(6), 
	x50_value FLOAT, 
	x50_unit VARCHAR(2), 
	slope FLOAT, 
	slope_unit TEXT, 
	tau_act_ms FLOAT, 
	tau_inact_ms FLOAT, 
	tau_deact_ms FLOAT, 
	conductance_ps FLOAT, 
	reversal_potential_mv FLOAT, 
	iv_relation VARCHAR(18), 
	delta_p50_value FLOAT, 
	delta_p50_unit VARCHAR(5), 
	ion_selectivity_ratio FLOAT, 
	ratio_direction TEXT, 
	ca_permeability FLOAT, 
	threshold_fold_shift_value FLOAT, 
	threshold_fold_shift_unit TEXT, 
	macroscopic_rise_time_ms FLOAT, 
	thermal_threshold_c FLOAT, 
	osmotic_threshold_value FLOAT, 
	osmotic_threshold_unit TEXT, 
	value_as_reported TEXT, 
	unit_as_reported TEXT, 
	stimulus_type VARCHAR(17), 
	stimulus_waveform TEXT, 
	stimulus_velocity FLOAT, 
	stimulus_velocity_unit TEXT, 
	stimulus_duration_ms FLOAT, 
	probe_geometry TEXT, 
	probe_diameter_um FLOAT, 
	recording_mode VARCHAR(28), 
	expression_system TEXT, 
	cell_type TEXT, 
	temperature_c FLOAT, 
	ph FLOAT, 
	bath_solution TEXT, 
	pipette_solution TEXT, 
	holding_potential_mv FLOAT, 
	sampling_rate_khz FLOAT, 
	filter_khz FLOAT, 
	n_cells INTEGER, 
	analysis_method TEXT, 
	protocol_ref TEXT, 
	measurement_id TEXT, 
	evidence_quote TEXT, 
	evidence_location TEXT, 
	confidence TEXT, 
	extractor_note TEXT, 
	condition_key TEXT, 
	n TEXT, 
	source_db VARCHAR(15), 
	collected_date DATE, 
	publication_id INTEGER, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (maicdb_id), 
	FOREIGN KEY(channel_id) REFERENCES channel (id) ON DELETE CASCADE, 
	FOREIGN KEY(structure_id) REFERENCES structure (id) ON DELETE SET NULL, 
	FOREIGN KEY(compound_id) REFERENCES compound (id) ON DELETE SET NULL, 
	FOREIGN KEY(variant_id) REFERENCES variant (id) ON DELETE SET NULL, 
	CONSTRAINT parameterset CHECK (parameter_set IN ('P50', 'T50', 'X50', 'CONDUCTANCE_ONLY', 'KINETICS_ONLY', 'FULL_CARD')), 
	CONSTRAINT pressureunit CHECK (p50_unit IN ('mmHg', 'kPa', 'Pa', 'mbar', 'cmH2O', 'psi')), 
	CONSTRAINT tensionunit CHECK (t50_unit IN ('mN/m', 'dyn/cm', 'pN/um', 'N/m')), 
	CONSTRAINT indentationunit CHECK (x50_unit IN ('um', 'mm', 'nm')), 
	CONSTRAINT ivrelation CHECK (iv_relation IN ('LINEAR', 'OUTWARD_RECTIFYING', 'INWARD_RECTIFYING')), 
	CONSTRAINT pressureunit CHECK (delta_p50_unit IN ('mmHg', 'kPa', 'Pa', 'mbar', 'cmH2O', 'psi')), 
	CONSTRAINT stimulustype CHECK (stimulus_type IN ('PRESSURE_CLAMP', 'SUCTION', 'POSITIVE_PRESSURE', 'INDENTATION', 'MEMBRANE_STRETCH', 'SHEAR_STRESS', 'OSMOTIC', 'HYPOTONIC', 'TOUCH', 'OTHER')), 
	CONSTRAINT recordingmode CHECK (recording_mode IN ('CELL_ATTACHED', 'INSIDE_OUT', 'OUTSIDE_OUT', 'WHOLE_CELL', 'PERFORATED_PATCH', 'TEVC', 'RECONSTITUTED_PROTEOLIPOSOME', 'PLANAR_PATCH', 'OTHER')), 
	CONSTRAINT sourcedb CHECK (source_db IN ('UNIPROT', 'PDB', 'ALPHAFOLD', 'HGNC', 'NCBI_GENE', 'CHEMBL_TARGET', 'CHEMBL_MOLECULE', 'PUBCHEM', 'BINDINGDB', 'IUPHAR', 'CLINVAR', 'OMIM', 'MECHANOBASE', 'MECHANOPRODB', 'ICG', 'CHANNELPEDIA', 'TRIP', 'GO', 'DOI', 'LITERATURE')), 
	FOREIGN KEY(publication_id) REFERENCES publication (id) ON DELETE SET NULL
)

CREATE INDEX ix_biophysics_experiment_channel_id ON biophysics_experiment (channel_id)

CREATE INDEX ix_biophysics_experiment_compound_id ON biophysics_experiment (compound_id)

CREATE INDEX ix_biophysics_experiment_condition_key ON biophysics_experiment (condition_key)

CREATE INDEX ix_biophysics_experiment_iv_relation ON biophysics_experiment (iv_relation)

CREATE UNIQUE INDEX ix_biophysics_experiment_measurement_id ON biophysics_experiment (measurement_id)

CREATE INDEX ix_biophysics_experiment_parameter_set ON biophysics_experiment (parameter_set)

CREATE INDEX ix_biophysics_experiment_recording_mode ON biophysics_experiment (recording_mode)

CREATE INDEX ix_biophysics_experiment_source_db ON biophysics_experiment (source_db)

CREATE INDEX ix_biophysics_experiment_stimulus_type ON biophysics_experiment (stimulus_type)

CREATE INDEX ix_biophysics_experiment_structure_id ON biophysics_experiment (structure_id)

CREATE INDEX ix_biophysics_experiment_variant_id ON biophysics_experiment (variant_id)
