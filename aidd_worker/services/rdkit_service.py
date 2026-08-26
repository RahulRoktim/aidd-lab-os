"""
AIDD Worker - RDKit Scientific Service & Comprehensive 50+ Molecule Benchmark
"""

import math
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone

from aidd_worker.models import MoleculeInput, FailureRecord
from aidd_worker.services.capability_service import detect_rdkit

# 50+ Diverse Chemical Structures spanning 14 chemistry classes
DIVERSE_50_MOLECULES = [
    # 1. Simple Organics & Alkanes/Alcohols
    {"id": "CHEM-01", "name": "Ethanol", "smiles": "CCO", "class": "Simple Alcohol"},
    {"id": "CHEM-02", "name": "Isopropanol", "smiles": "CC(C)O", "class": "Secondary Alcohol"},
    {"id": "CHEM-03", "name": "Diethyl Ether", "smiles": "CCOCC", "class": "Ether"},
    {"id": "CHEM-04", "name": "Acetone", "smiles": "CC(=O)C", "class": "Ketone"},
    {"id": "CHEM-05", "name": "Acetic Acid", "smiles": "CC(=O)O", "class": "Carboxylic Acid"},
    {"id": "CHEM-06", "name": "Ethyl Acetate", "smiles": "CCOC(=O)C", "class": "Ester"},
    
    # 2. Aromatics
    {"id": "CHEM-07", "name": "Benzene", "smiles": "c1ccccc1", "class": "Aromatic Hydrocarbon"},
    {"id": "CHEM-08", "name": "Toluene", "smiles": "Cc1ccccc1", "class": "Substituted Aromatic"},
    {"id": "CHEM-09", "name": "Phenol", "smiles": "Oc1ccccc1", "class": "Phenol"},
    {"id": "CHEM-10", "name": "Aniline", "smiles": "Nc1ccccc1", "class": "Aromatic Amine"},
    {"id": "CHEM-11", "name": "Salicylic Acid", "smiles": "O=C(O)c1ccccc1O", "class": "Aromatic Acid/Phenol"},
    
    # 3. Heteroaromatics (6-membered & 5-membered)
    {"id": "CHEM-12", "name": "Pyridine", "smiles": "c1ccncc1", "class": "Heteroaromatic"},
    {"id": "CHEM-13", "name": "Pyrimidine", "smiles": "c1cncnc1", "class": "Heteroaromatic"},
    {"id": "CHEM-14", "name": "Pyrazine", "smiles": "c1cnccn1", "class": "Heteroaromatic"},
    {"id": "CHEM-15", "name": "Thiophene", "smiles": "c1ccsc1", "class": "Thiophene"},
    {"id": "CHEM-16", "name": "Furan", "smiles": "c1ccoc1", "class": "Furan"},
    {"id": "CHEM-17", "name": "Pyrrole", "smiles": "c1cc[nH]c1", "class": "Pyrrole"},
    {"id": "CHEM-18", "name": "Imidazole", "smiles": "c1c[nH]cn1", "class": "Imidazole"},
    {"id": "CHEM-19", "name": "Thiazole", "smiles": "c1cscn1", "class": "Thiazole"},
    {"id": "CHEM-20", "name": "Oxazole", "smiles": "c1cocn1", "class": "Oxazole"},
    
    # 4. Fused Heterocycles
    {"id": "CHEM-21", "name": "Indole", "smiles": "c1ccc2[nH]ccc2c1", "class": "Fused Indole"},
    {"id": "CHEM-22", "name": "Benzofuran", "smiles": "c1ccc2occc2c1", "class": "Fused Benzofuran"},
    {"id": "CHEM-23", "name": "Quinoline", "smiles": "c1ccc2ncccc2c1", "class": "Fused Quinoline"},
    {"id": "CHEM-24", "name": "Isoquinoline", "smiles": "c1ccc2cnccc2c1", "class": "Fused Isoquinoline"},
    {"id": "CHEM-25", "name": "Purine Core", "smiles": "c1ncnc2[nH]cnc12", "class": "Fused Purine"},
    
    # 5. Amines (Aliphatic 1°, 2°, 3°, Cyclic)
    {"id": "CHEM-26", "name": "Methylamine", "smiles": "CN", "class": "Primary Amine"},
    {"id": "CHEM-27", "name": "Dimethylamine", "smiles": "CNC", "class": "Secondary Amine"},
    {"id": "CHEM-28", "name": "Triethylamine", "smiles": "CCN(CC)CC", "class": "Tertiary Amine"},
    {"id": "CHEM-29", "name": "Piperidine", "smiles": "C1CCNCC1", "class": "Cyclic Amine"},
    {"id": "CHEM-30", "name": "Piperazine", "smiles": "C1CNCCN1", "class": "Diamine"},
    {"id": "CHEM-31", "name": "Morpholine", "smiles": "C1COCCN1", "class": "Morpholine"},
    
    # 6. Amides & Lactams
    {"id": "CHEM-32", "name": "Acetamide", "smiles": "CC(=O)N", "class": "Primary Amide"},
    {"id": "CHEM-33", "name": "N-Methylacetamide", "smiles": "CNC(=O)C", "class": "Secondary Amide"},
    {"id": "CHEM-34", "name": "Benzamide", "smiles": "O=C(N)c1ccccc1", "class": "Aromatic Amide"},
    {"id": "CHEM-35", "name": "2-Pyrrolidone", "smiles": "O=C1CCCN1", "class": "Lactam"},
    
    # 7. Halogenated Compounds
    {"id": "CHEM-36", "name": "Fluorobenzene", "smiles": "Fc1ccccc1", "class": "Fluorinated"},
    {"id": "CHEM-37", "name": "Chlorobenzene", "smiles": "Clc1ccccc1", "class": "Chlorinated"},
    {"id": "CHEM-38", "name": "Bromobenzene", "smiles": "Brc1ccccc1", "class": "Brominated"},
    {"id": "CHEM-39", "name": "Iodobenzene", "smiles": "Ic1ccccc1", "class": "Iodinated"},
    {"id": "CHEM-40", "name": "Trifluoroacetic Acid", "smiles": "O=C(O)C(F)(F)F", "class": "Perfluorinated"},
    
    # 8. Fused Polycyclics & Bridged Systems
    {"id": "CHEM-41", "name": "Naphthalene", "smiles": "c1ccc2ccccc2c1", "class": "Bicyclic Aromatic"},
    {"id": "CHEM-42", "name": "Anthracene", "smiles": "c1ccc2cc3ccccc3cc2c1", "class": "Tricyclic Aromatic"},
    {"id": "CHEM-43", "name": "Adamantane", "smiles": "C1C2CC3CC1CC(C2)C3", "class": "Bridged Hydrocarbon"},
    
    # 9. Stereochemistry & Chiral Molecules
    {"id": "CHEM-44", "name": "L-Alanine", "smiles": "C[C@@H](N)C(=O)O", "class": "Amino Acid"},
    {"id": "CHEM-45", "name": "Ibuprofen Chiral", "smiles": "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O", "class": "Chiral NSAID"},
    
    # 10. Multi-Fragment Salts & Complexes
    {"id": "CHEM-46", "name": "Sodium Acetate Mixture", "smiles": "CC(=O)O.[Na]", "class": "Salt Mixture"},
    {"id": "CHEM-47", "name": "Anilinium Chloride", "smiles": "Nc1ccccc1.Cl", "class": "Amine Salt"},
    
    # 11. Clinical FDA Pharmaceuticals & Kinase Inhibitors
    {"id": "CHEM-48", "name": "Aspirin", "smiles": "CC(=O)Oc1ccccc1C(=O)O", "class": "NSAID"},
    {"id": "CHEM-49", "name": "Paracetamol", "smiles": "CC(=O)Nc1ccc(O)cc1", "class": "Analgesic"},
    {"id": "CHEM-50", "name": "Caffeine", "smiles": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C", "class": "Xanthine"},
    {"id": "CHEM-51", "name": "Gefitinib", "smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1", "class": "EGFR Kinase Inhibitor"},
    {"id": "CHEM-52", "name": "Erlotinib", "smiles": "COCCOC1=C(C=C2C(=C1)C(=NC=N2)NC3=CC=CC(=C3)C#C)OCCOC", "class": "EGFR Kinase Inhibitor"},
    {"id": "CHEM-53", "name": "Osimertinib", "smiles": "C=CC(=O)Nc1cc(Nc2nccc(n2)c3cn(C)c4ccccc34)c(OC)cc1N(C)CCN(C)C", "class": "3rd Gen EGFR Inhibitor"},
    {"id": "CHEM-54", "name": "Imatinib", "smiles": "Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(C)CC5", "class": "BCR-ABL Inhibitor"},
    {"id": "CHEM-55", "name": "Sorafenib", "smiles": "CNC(=O)c1cc(ccn1)Oc2ccc(cc2)NC(=O)Nc3ccc(c(c3)C(F)(F)F)Cl", "class": "Multi-Kinase Inhibitor"}
]

def calculate_descriptors_batch(molecules: List[MoleculeInput]) -> Tuple[List[dict], List[FailureRecord], dict]:
    """
    Executes batch descriptor calculation using native RDKit if available,
    or the calibrated pure-Python reference fallback.
    """
    rdkit_info = detect_rdkit()
    has_rdkit = bool(rdkit_info.get("installed") and rdkit_info.get("production_ready"))

    successful = []
    failures = []

    for m in molecules:
        smiles = (m.smiles or "").strip()
        if not smiles:
            failures.append(FailureRecord(
                molecule_id=m.id,
                molecule_name=m.name,
                smiles="",
                error_type="EmptySMILES",
                error_message="Molecule entry has empty SMILES"
            ))
            continue

        if has_rdkit:
            try:
                from rdkit import Chem
                from rdkit.Chem import Descriptors, Lipinski, QED, rdMolDescriptors, AllChem
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    failures.append(FailureRecord(
                        molecule_id=m.id,
                        molecule_name=m.name,
                        smiles=smiles,
                        error_type="RDKitSanitizationError",
                        error_message="RDKit MolFromSmiles failed: invalid chemical valence or structure"
                    ))
                    continue

                mw = round(Descriptors.MolWt(mol), 2)
                exact_mw = round(Descriptors.ExactMolWt(mol), 4)
                logp = round(Descriptors.MolLogP(mol), 2)
                tpsa = round(Descriptors.TPSA(mol), 2)
                hbd = Lipinski.NumHDonors(mol)
                hba = Lipinski.NumHAcceptors(mol)
                rotb = Lipinski.NumRotatableBonds(mol)
                heavy_atoms = mol.GetNumHeavyAtoms()
                num_rings = Lipinski.RingCount(mol)
                formula = rdMolDescriptors.CalcMolFormula(mol)
                qed_val = round(QED.qed(mol), 3)

                fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=1024)
                on_bits = list(fp.GetOnBits())
                canonical_smi = Chem.MolToSmiles(mol, canonical=True)

                violations = 0
                violation_reasons = []
                if mw > 500.0: violations += 1; violation_reasons.append(f"MW ({mw} > 500)")
                if logp > 5.0: violations += 1; violation_reasons.append(f"LogP ({logp} > 5.0)")
                if hbd > 5: violations += 1; violation_reasons.append(f"HBD ({hbd} > 5)")
                if hba > 10: violations += 1; violation_reasons.append(f"HBA ({hba} > 10)")

                successful.append({
                    "id": m.id,
                    "name": m.name or m.id,
                    "smiles": canonical_smi,
                    "original_smiles": smiles,
                    "canonical_smiles": canonical_smi,
                    "formula": formula,
                    "molecular_weight": mw,
                    "exact_molecular_weight": exact_mw,
                    "logp": logp,
                    "tpsa": tpsa,
                    "hbd": hbd,
                    "hba": hba,
                    "rotatable_bonds": rotb,
                    "heavy_atoms": heavy_atoms,
                    "num_rings": num_rings,
                    "lipinski_violations": violations,
                    "lipinski_pass": violations <= 1,
                    "veber_pass": (rotb <= 10 and tpsa <= 140.0),
                    "qed": qed_val,
                    "fingerprint": {
                        "type": "Morgan2_1024",
                        "on_bits_count": len(on_bits),
                        "density": round(len(on_bits) / 1024, 4),
                        "bits": on_bits
                    },
                    "engine": f"RDKit v{rdkit_info['version']}",
                    "production_ready": True,
                    "result_origin": "COMPUTED"
                })
            except Exception as e:
                failures.append(FailureRecord(
                    molecule_id=m.id,
                    molecule_name=m.name,
                    smiles=smiles,
                    error_type="RDKitExecutionException",
                    error_message=str(e)
                ))
        else:
            # Fallback execution
            from app.scientific_engine import ScientificEngine
            desc = ScientificEngine.calculate_descriptors(smiles)
            if not desc["valid"]:
                failures.append(FailureRecord(
                    molecule_id=m.id,
                    molecule_name=m.name,
                    smiles=smiles,
                    error_type="ValenceOrParsingError",
                    error_message=desc.get("error", "Parsing failed")
                ))
                continue

            fp = ScientificEngine.generate_fingerprint(smiles)
            successful.append({
                "id": m.id,
                "name": m.name or m.id,
                "smiles": desc["smiles"],
                "original_smiles": smiles,
                "canonical_smiles": desc["smiles"],
                "formula": desc["formula"],
                "molecular_weight": desc["molecular_weight"],
                "exact_molecular_weight": desc.get("exact_molecular_weight", desc["molecular_weight"]),
                "logp": desc["logp"],
                "tpsa": desc["tpsa"],
                "hbd": desc["hbd"],
                "hba": desc["hba"],
                "rotatable_bonds": desc["rotatable_bonds"],
                "heavy_atoms": desc["heavy_atoms"],
                "num_rings": desc["num_rings"],
                "lipinski_violations": desc["lipinski_violations"],
                "lipinski_pass": desc["lipinski_pass"],
                "veber_pass": desc["veber_pass"],
                "qed": desc["qed"],
                "fingerprint": fp,
                "engine": "AIDD Python Reference Engine (Non-Production Fallback)",
                "production_ready": False,
                "result_origin": "SIMULATED"
            })

    meta = {
        "engine": f"RDKit v{rdkit_info['version']}" if has_rdkit else "AIDD Python Reference Engine (Non-Production Fallback)",
        "production_ready": has_rdkit,
        "rdkit_attestation": {
            "version": rdkit_info.get("version"),
            "module_path": rdkit_info.get("module_path"),
            "module_origin_verified": rdkit_info.get("module_origin_verified", False),
            "native_components_verified": rdkit_info.get("native_components_verified", False),
            "package_metadata_verified": rdkit_info.get("package_metadata_verified", False),
            "known_answer_verified": rdkit_info.get("known_answer_verified", False),
            "known_answer_results": rdkit_info.get("known_answer_results", []),
        },
        "total_molecules": len(molecules),
        "successful_count": len(successful),
        "failed_count": len(failures)
    }

    return successful, failures, meta

def standardize_molecules_batch(molecules: List[MoleculeInput], remove_salts: bool = True, neutralize: bool = True) -> Tuple[List[dict], List[FailureRecord], dict]:
    rdkit_info = detect_rdkit()
    has_rdkit = bool(rdkit_info.get("installed") and rdkit_info.get("production_ready"))

    successful = []
    failures = []

    for m in molecules:
        smiles = (m.smiles or "").strip()
        if not smiles:
            failures.append(FailureRecord(molecule_id=m.id, molecule_name=m.name, smiles="", error_type="EmptySMILES", error_message="Empty SMILES string"))
            continue

        clean_smi = smiles
        warnings = []

        if remove_salts and '.' in smiles:
            frags = smiles.split('.')
            clean_smi = max(frags, key=lambda f: len(f))
            if clean_smi != smiles:
                warnings.append(f"Stripped inorganic counterions: {smiles} -> {clean_smi}")

        if has_rdkit:
            try:
                from rdkit import Chem
                mol = Chem.MolFromSmiles(clean_smi)
                if mol is None:
                    failures.append(FailureRecord(molecule_id=m.id, molecule_name=m.name, smiles=smiles, error_type="RDKitStandardizationFailed", error_message="Invalid chemical structure in RDKit"))
                    continue
                canonical_smi = Chem.MolToSmiles(mol, canonical=True)
                successful.append({
                    "id": m.id,
                    "name": m.name or m.id,
                    "original_smiles": smiles,
                    "standardized_smiles": canonical_smi,
                    "was_modified": smiles != canonical_smi,
                    "warnings": warnings,
                    "engine": f"RDKit v{rdkit_info['version']}",
                    "production_ready": True,
                    "result_origin": "COMPUTED"
                })
            except Exception as e:
                failures.append(FailureRecord(molecule_id=m.id, molecule_name=m.name, smiles=smiles, error_type="RDKitStandardizationException", error_message=str(e)))
        else:
            from app.scientific_engine import ScientificEngine
            std_res = ScientificEngine.standardize_molecule(smiles, remove_salts=remove_salts, neutralize=neutralize)
            if not std_res["success"]:
                failures.append(FailureRecord(molecule_id=m.id, molecule_name=m.name, smiles=smiles, error_type="StandardizationFailed", error_message=std_res.get("error", "Failed")))
                continue

            successful.append({
                "id": m.id,
                "name": m.name or m.id,
                "original_smiles": smiles,
                "standardized_smiles": std_res["standardized_smiles"],
                "was_modified": std_res["was_modified"],
                "warnings": std_res["warnings"],
                "engine": "AIDD Python Reference Engine (Non-Production Fallback)",
                "production_ready": False,
                "result_origin": "SIMULATED"
            })

    meta = {
        "engine": f"RDKit v{rdkit_info['version']}" if has_rdkit else "AIDD Python Reference Engine (Non-Production Fallback)",
        "production_ready": has_rdkit,
        "total_molecules": len(molecules),
        "successful_count": len(successful),
        "failed_count": len(failures)
    }

    return successful, failures, meta

def run_50_molecule_validation_suite() -> dict:
    """
    Executes all 55 diverse chemical structures through the worker pipeline and evaluates consistency.
    """
    molecules = [MoleculeInput(id=m["id"], name=m["name"], smiles=m["smiles"]) for m in DIVERSE_50_MOLECULES]
    successful, failures, meta = calculate_descriptors_batch(molecules)

    categories_tested = len(set(m["class"] for m in DIVERSE_50_MOLECULES))
    
    return {
        "total_compounds_tested": len(DIVERSE_50_MOLECULES),
        "categories_tested": categories_tested,
        "successful_count": len(successful),
        "failed_count": len(failures),
        "engine": meta["engine"],
        "production_ready": meta["production_ready"],
        "sample_results": successful[:5],
        "rdkit_attestation": meta.get("rdkit_attestation", {}),
        "validation_passed": bool(meta["production_ready"] and len(failures) == 0)
    }
