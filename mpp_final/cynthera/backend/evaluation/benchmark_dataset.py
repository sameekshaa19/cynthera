"""Benchmark dataset collection for Phase 4E evaluation.

Dataset Construction Principles
--------------------------------
1. POSITIVE cases: Approved repurposing indications with documented molecular mechanism
   mapped to canonical targets with Open Targets / DATTs directional annotations.
2. NEGATIVE cases: Pharmacological counterfactuals where the drug's action on the target
   is directionally OPPOSITE to what disease-direction evidence requires. A genuine negative
   is not simply "no evidence" — it is evidence that the direction is wrong.
3. UNCERTAIN cases: Cases with genuine directional ambiguity — where either the drug action
   or the target-disease direction is uncharacterized, or conflicting signals exist.

Label Provenance
----------------
Every case carries:
  label_source: Primary authority for the expected class assignment.
  label_reference: Specific citation, ID, or URL.
  label_rationale: Scientific explanation of the directional reasoning.

Quality Flags
-------------
  unsuitable_for_directional_negative: If True, this case cannot produce OPPOSES from
    the live pipeline because directional annotations for the target-disease pair are
    absent in configured data sources (Open Targets DoE / DATTs). The case is kept
    for documentation completeness but excluded from directional specificity metrics.

Dataset Splits
--------------
  split = TEST  : Cases used for final evaluation (do not tune weights against TEST).
  split = DEV   : Cases intended for development-time inspection of system behavior.
"""
from __future__ import annotations

from backend.evaluation.benchmark_models import BenchmarkCase, BenchmarkClass, BenchmarkSplit


# ══════════════════════════════════════════════════════════════════════════════
# BENCHMARK_DATASET_V1  —  Full dataset (all splits combined)
# ══════════════════════════════════════════════════════════════════════════════
BENCHMARK_DATASET_V1: list[BenchmarkCase] = [

    # ── Canonical Positives (ground-truth POSITIVE) ───────────────────────────

    BenchmarkCase(
        case_id="BENCH-POS-01",
        drug="Furosemide",
        disease="Edema",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="SLC12A1",
        rationale="Loop diuretic inhibiting NKCC2 (SLC12A1) to reduce volume overload in edema.",
        evidence_reference="FDA Approved Indication; Open Targets LoF-protect; DATTs Curated Inhibition",
        source="ChEMBL / Open Targets / DATTs",
        notes="Primary benchmark positive control.",
        label_source="FDA Approved Drug Label",
        label_reference="FDA NDA 016273",
        label_rationale=(
            "Furosemide is an FDA-approved loop diuretic. Its mechanism of action is inhibition of "
            "NKCC2 (SLC12A1), which reduces renal sodium reabsorption and fluid retention. "
            "Open Targets records LoF-protect direction for SLC12A1 in edematous conditions, "
            "confirming that inhibiting this transporter is the desired therapeutic direction."
        ),
        split=BenchmarkSplit.TEST,
    ),

    BenchmarkCase(
        case_id="BENCH-POS-02",
        drug="Propranolol",
        disease="Infantile Hemangioma",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="ADRB1",
        rationale=(
            "Non-selective beta-blocker inhibiting ADRB1/ADRB2 causing vasoconstriction "
            "and apoptosis in proliferating hemangiomas."
        ),
        evidence_reference="FDA/EMA Approved Repurposing Indication; DrugMechDB DB00571",
        source="ChEMBL / DrugMechDB / Open Targets",
        notes="Established pediatric drug repurposing breakthrough.",
        label_source="FDA Approval (Hemangeol)",
        label_reference="FDA NDA 205410",
        label_rationale=(
            "Propranolol received FDA approval for infantile hemangioma in 2014. "
            "Its therapeutic effect requires beta-antagonism (INHIBITION) of ADRB1/ADRB2, "
            "which reduces cAMP-driven vasodilation and induces apoptosis in proliferating "
            "endothelial cells. DrugMechDB records the full curated mechanistic path."
        ),
        split=BenchmarkSplit.TEST,
    ),

    BenchmarkCase(
        case_id="BENCH-POS-03",
        drug="Dapagliflozin",
        disease="Heart Failure",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="SLC5A2",
        rationale="SGLT2 inhibitor (SLC5A2) reducing cardiovascular death and hospitalizations in HFrEF/HFpEF.",
        evidence_reference="DAPA-HF Clinical Trial (NEJM 2019); Open Targets Clinical Precedence",
        source="ChEMBL / Open Targets / DATTs",
        notes="Landmark metabolic to cardiovascular repurposing indication.",
        label_source="Pivotal Clinical Trial",
        label_reference="PMID:31535829",
        label_rationale=(
            "The DAPA-HF trial (McMurray et al., NEJM 2019) demonstrated that dapagliflozin, "
            "an SGLT2 (SLC5A2) inhibitor, significantly reduced the composite of worsening "
            "heart failure or cardiovascular death in patients with HFrEF. "
            "Subsequent EMPEROR-Reduced and EMPEROR-Preserved trials extended this to HFpEF. "
            "FDA approved the HF indication in 2020."
        ),
        split=BenchmarkSplit.TEST,
    ),

    BenchmarkCase(
        case_id="BENCH-POS-04",
        drug="Thalidomide",
        disease="Multiple Myeloma",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="CRBN",
        rationale=(
            "Immunomodulatory drug binding cereblon (CRBN) to recruit and degrade "
            "transcription factors IKZF1/3 in myeloma."
        ),
        evidence_reference="FDA Approved; DATTs CRBN targeting; DrugMechDB DB01041",
        source="ChEMBL / DATTs / Open Targets / DrugMechDB",
        notes="Classic phenotypic to targeted molecular mechanism repurposing case.",
        label_source="FDA Approval + DrugMechDB Curated Path",
        label_reference="FDA NDA 021430; DrugMechDB DB01041",
        label_rationale=(
            "Thalidomide received FDA approval for multiple myeloma in 2006. "
            "Its primary mechanism involves binding cereblon (CRBN), the substrate receptor "
            "of a CRL4 ubiquitin ligase complex, redirecting it to degrade IKZF1 and IKZF3 "
            "transcription factors critical for myeloma cell survival. "
            "DrugMechDB records the full curated mechanistic path."
        ),
        split=BenchmarkSplit.TEST,
    ),

    BenchmarkCase(
        case_id="BENCH-POS-05",
        drug="Aspirin",
        disease="Colorectal Cancer",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="PTGS2",
        rationale="COX-2 (PTGS2) inhibitor reducing prostaglandin synthesis, inflammation, and adenoma recurrence in CRC.",
        evidence_reference="USPSTF Chemoprevention Guideline; Open Targets Clinical Precedence",
        source="ChEMBL / Open Targets",
        notes="Chemoprevention repurposing paradigm.",
        label_source="USPSTF Clinical Guideline + Meta-analysis",
        label_reference="PMID:25834009",
        label_rationale=(
            "The USPSTF (2016) issued a B-grade recommendation for aspirin use for primary "
            "prevention including colorectal cancer in adults aged 50-59. "
            "Meta-analyses demonstrate that aspirin's inhibition of COX-2 (PTGS2) reduces "
            "prostaglandin E2 production, suppressing tumor-promoting inflammation and "
            "adenoma recurrence. Open Targets records clinical evidence for PTGS2 in CRC."
        ),
        split=BenchmarkSplit.TEST,
    ),

    # ── Directional Negative Controls (ground-truth NEGATIVE) ─────────────────

    BenchmarkCase(
        case_id="BENCH-NEG-01",
        drug="Isoproterenol",
        disease="Infantile Hemangioma",
        expected_class=BenchmarkClass.NEGATIVE,
        expected_target="ADRB1",
        rationale=(
            "Beta-adrenergic agonist (ACTIVATION) on ADRB1/ADRB2. "
            "Propranolol's therapeutic efficacy requires beta-antagonism (INHIBITION); "
            "beta-receptor agonism causes vasodilation and opposes therapeutic requirements."
        ),
        evidence_reference="ChEMBL Mechanism AGONIST vs ADRB1 LoF-protect requirement",
        source="Pharmacological Counterfactual Control",
        notes=(
            "Directional antagonist control paired with Propranolol (BENCH-POS-02). "
            "IMPORTANT: This case is flagged unsuitable_for_directional_negative=True because "
            "Open Targets DoE and DATTs currently carry no directional annotations for ADRB1 "
            "in Infantile Hemangioma specifically. The pharmacological reasoning is correct "
            "and well-documented, but the live pipeline cannot produce OPPOSES for this pair "
            "due to absent target-disease direction data in configured sources. "
            "This case is retained for documentation; exclude from directional specificity metrics."
        ),
        label_source="Pharmacological First Principles + ChEMBL Mechanism",
        label_reference="ChEMBL CHEMBL1431 (Isoproterenol); PMID:9488601",
        label_rationale=(
            "Isoproterenol is a non-selective beta-adrenergic full agonist (ChEMBL AGONIST). "
            "Propranolol's efficacy in infantile hemangioma requires ADRB1/ADRB2 antagonism. "
            "Therefore, an agonist on the same target should oppose the therapeutic direction. "
            "However, Open Targets does not record ADRB1 LoF/GoF direction-of-effect data "
            "specifically for infantile hemangioma — the disease is too rare for GWAS. "
            "The expected NEGATIVE label is scientifically justified but cannot be verified "
            "by the current pipeline's directional evidence sources."
        ),
        split=BenchmarkSplit.TEST,
        unsuitable_for_directional_negative=True,
    ),

    BenchmarkCase(
        case_id="BENCH-NEG-02",
        drug="Norepinephrine",
        disease="Heart Failure",
        expected_class=BenchmarkClass.NEGATIVE,
        expected_target="ADRB1",
        rationale=(
            "Norepinephrine is a catecholamine that activates ADRB1, causing increased "
            "chronotropy, inotropy and cardiac stress. In chronic heart failure, sustained "
            "ADRB1 activation is pathological — the established therapeutic strategy is "
            "ADRB1 INHIBITION (beta-blockers), not activation. This is the canonical "
            "pharmacological counterfactual to carvedilol/metoprolol repurposing."
        ),
        evidence_reference="MERIT-HF, CIBIS-II, COPERNICUS trials; HF clinical guidelines; Open Targets ADRB1 GoF-risk / LoF-protect",
        source="ChEMBL / Open Targets",
        notes=(
            "Grounded hard negative: Open Targets records directional data for ADRB1 in Heart Failure "
            "(cardiac function phenotypes). ADRB1 GoF (sympathetic overdrive) is risk-associated; "
            "LoF/pharmacological inhibition is protective. Norepinephrine ChEMBL mechanism = AGONIST. "
            "This case should produce OPPOSES from the live pipeline."
        ),
        label_source="Clinical Guidelines + Landmark Clinical Trials",
        label_reference="PMID:10764374; PMID:10376614; PMID:11519503",
        label_rationale=(
            "Multiple landmark RCTs (MERIT-HF, CIBIS-II, COPERNICUS) establish that beta-blockade "
            "(ADRB1 inhibition) reduces mortality in chronic heart failure. "
            "Conversely, sustained norepinephrine-driven ADRB1 activation (as occurs in sympathetic "
            "overdrive) is a core pathophysiological driver of HF progression. "
            "ESC/ACC heart failure guidelines contra-indicate sustained beta-agonist use. "
            "Norepinephrine's ChEMBL mechanism is AGONIST on ADRB1. "
            "This directional opposition should be detectable via Open Targets ADRB1 HF direction data."
        ),
        split=BenchmarkSplit.TEST,
        unsuitable_for_directional_negative=False,
    ),

    BenchmarkCase(
        case_id="BENCH-NEG-03",
        drug="Testosterone",
        disease="Prostate Cancer",
        expected_class=BenchmarkClass.NEGATIVE,
        expected_target="AR",
        rationale=(
            "Testosterone is an androgen receptor (AR) AGONIST/ACTIVATOR. "
            "Prostate cancer is AR-driven; established therapy requires AR antagonism "
            "(antiandrogens: enzalutamide, abiraterone) or androgen deprivation. "
            "Testosterone directly activates the target whose inhibition is required."
        ),
        evidence_reference="Huggins & Hodges 1941 Nobel-cited work; EAU Guidelines; Open Targets AR GoF-risk in prostate cancer",
        source="ChEMBL / Open Targets / DATTs",
        notes=(
            "Classic hard negative: AR activation by testosterone drives PCa proliferation. "
            "Open Targets records GoF-risk direction for AR in prostate cancer. "
            "ChEMBL records testosterone as AR AGONIST. "
            "DATTs records INHIBITION as the required therapeutic action for AR in PCa. "
            "This case is expected to produce OPPOSES from the live pipeline."
        ),
        label_source="Nobel Prize Work + Established Clinical Guidelines",
        label_reference="PMID:14350438; PMID:2082610",
        label_rationale=(
            "Huggins and Hodges (1941) established that androgen deprivation causes regression of "
            "prostate cancer metastases (Nobel Prize 1966). This foundational observation underpins "
            "all current androgen deprivation therapy (ADT) for prostate cancer. "
            "AR is both the primary driver of PCa growth and the primary therapeutic target. "
            "Required therapeutic action = AR INHIBITION. "
            "Testosterone is an AR AGONIST — directly opposite to the required therapeutic direction. "
            "This is the strongest possible directional negative for which all three data sources "
            "(ChEMBL mechanism, Open Targets direction, DATTs required action) agree."
        ),
        split=BenchmarkSplit.TEST,
        unsuitable_for_directional_negative=False,
    ),

    # ── Mechanistically Uncertain Controls (ground-truth UNCERTAIN) ────────────

    BenchmarkCase(
        case_id="BENCH-UNC-01",
        drug="Thalidomide",
        disease="Hypertension",
        expected_class=BenchmarkClass.UNCERTAIN,
        expected_target="TNF",
        rationale=(
            "Thalidomide exhibits binding to TNF/PTGS1 with uncharacterized functional polarity "
            "and no established directional disease-target effect in essential hypertension."
        ),
        evidence_reference="ChEMBL Binding Data lacking functional polarity",
        source="Directional Ambiguity Control",
        notes="Tests system ability to withhold premature positive classification when directional evidence is insufficient.",
        label_source="Absence of directional annotations in configured sources",
        label_reference="ChEMBL CHEMBL267 (Thalidomide); Open Targets TNF-Hypertension associations",
        label_rationale=(
            "Thalidomide has binding activity against TNF/TNFA but its functional relationship "
            "to essential hypertension is not directionally characterized in any configured source. "
            "There is no established mechanistic pathway connecting thalidomide CRBN/TNF activity "
            "to blood pressure regulation with sufficient directional specificity. "
            "This case tests that the system correctly emits INSUFFICIENT when evidence is absent, "
            "rather than defaulting to POSITIVE based on target connectivity alone."
        ),
        split=BenchmarkSplit.TEST,
    ),

    BenchmarkCase(
        case_id="BENCH-UNC-02",
        drug="Methotrexate",
        disease="Rheumatoid Arthritis",
        expected_class=BenchmarkClass.UNCERTAIN,
        expected_target="DHFR",
        rationale=(
            "Methotrexate inhibits DHFR, reducing folate metabolism and proliferation. "
            "While clinically used for RA, its exact mechanism in RA is pleiotropic (adenosine "
            "pathway, T-cell suppression, anti-inflammatory effects beyond DHFR) and the "
            "DHFR-specific directional path for RA is not well-characterized in DoE databases. "
            "This tests whether the system can handle a clinically approved drug where the "
            "target-disease direction data is incomplete despite clinical use."
        ),
        evidence_reference="Cronstein 2005 Arthritis Research; Open Targets DHFR RA annotations",
        source="Directional Complexity Control",
        notes=(
            "Important: The expected label UNCERTAIN does NOT mean methotrexate doesn't work for RA "
            "(it does, FDA approved). It means the DHFR-specific directional evidence in configured "
            "sources may not be sufficient to produce a confident SUPPORTS verdict. "
            "This control tests the system's calibration against over-confident positive predictions."
        ),
        label_source="Mechanistic Complexity — Pleiotropic Drug with Incomplete DoE Annotations",
        label_reference="PMID:16093240",
        label_rationale=(
            "Methotrexate is FDA-approved for RA. However, its mechanism in RA is multifactorial: "
            "(1) DHFR inhibition → reduced folate → reduced proliferation, "
            "(2) adenosine-mediated anti-inflammatory effects independent of DHFR, "
            "(3) T-cell immunosuppression through multiple pathways. "
            "The specific DHFR → RA directional pathway is not clearly annotated in Open Targets "
            "DoE data for RA (rheumatoid arthritis is an immune-mediated disease, not primarily "
            "a proliferative disease like cancer). "
            "This case is UNCERTAIN from the perspective of the configured directional sources."
        ),
        split=BenchmarkSplit.TEST,
    ),
]


# ── Convenience accessors by split ──────────────────────────────────────────

def get_cases_by_split(split: BenchmarkSplit) -> list[BenchmarkCase]:
    """Return benchmark cases belonging to a specific split."""
    return [c for c in BENCHMARK_DATASET_V1 if c.split == split]


def get_directionally_suitable_negatives() -> list[BenchmarkCase]:
    """Return NEGATIVE benchmark cases that are expected to produce OPPOSES from live pipeline.

    Excludes cases flagged unsuitable_for_directional_negative=True.
    """
    return [
        c for c in BENCHMARK_DATASET_V1
        if c.expected_class == BenchmarkClass.NEGATIVE
        and not c.unsuitable_for_directional_negative
    ]


def get_unsuitable_negatives() -> list[BenchmarkCase]:
    """Return NEGATIVE cases flagged as unsuitable for directional pipeline evaluation."""
    return [
        c for c in BENCHMARK_DATASET_V1
        if c.expected_class == BenchmarkClass.NEGATIVE
        and c.unsuitable_for_directional_negative
    ]


# ── Named split constants ────────────────────────────────────────────────────
BENCHMARK_TEST_SET: list[BenchmarkCase] = get_cases_by_split(BenchmarkSplit.TEST)
BENCHMARK_DEV_SET: list[BenchmarkCase] = get_cases_by_split(BenchmarkSplit.DEVELOPMENT)
BENCHMARK_VAL_SET: list[BenchmarkCase] = get_cases_by_split(BenchmarkSplit.VALIDATION)
