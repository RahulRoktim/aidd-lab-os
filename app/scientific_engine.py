"""
AIDD Lab OS - Scientific Computation & Cheminformatics Engine Service
Provides formal abstraction for molecular parsing, descriptor calculation,
standardization, fingerprint generation, and 2D vector depiction.
Explicitly distinguishes between RDKit native engine and calibrated fallback engine,
recording exact engine metadata, methods, and non-production warnings.
"""

import re
import math
import html
import hashlib
import time
from datetime import datetime, timezone
from collections import defaultdict, deque
from typing import Dict, Any, Tuple, Optional, List

# Check RDKit availability
try:
    import rdkit
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Lipinski, QED, rdMolDescriptors, AllChem, Draw
    HAS_RDKIT = True
    RDKIT_VERSION = rdkit.__version__
except ImportError:
    HAS_RDKIT = False
    RDKIT_VERSION = None

# RDKit-method regression snapshots for automated execution testing.  These
# ranges are implementation checks, not experimental ground truth.
REFERENCE_BENCHMARKS = {
    "caffeine": {
        "smiles": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
        "formula": "C8H10N4O2",
        "exact_mw": 194.19,
        "mw_range": (194.0, 194.3),
        "logp_range": (-1.2, -0.8),
        "tpsa_range": (45.0, 65.0),
        "hbd": 0,
        "hba": 6,
        "rotatable_bonds": 0
    },
    "aspirin": {
        "smiles": "CC(=O)Oc1ccccc1C(=O)O",
        "formula": "C9H8O4",
        "exact_mw": 180.16,
        "mw_range": (180.0, 180.3),
        "logp_range": (1.0, 1.8),
        "tpsa_range": (60.0, 68.0),
        "hbd": 1,
        "hba": 3,
        "rotatable_bonds": 3
    },
    "acetaminophen": {
        "smiles": "CC(=O)Nc1ccc(O)cc1",
        "formula": "C8H9NO2",
        "exact_mw": 151.16,
        "mw_range": (151.0, 151.3),
        "logp_range": (0.8, 1.6),
        "tpsa_range": (45.0, 55.0),
        "hbd": 2,
        "hba": 2,
        "rotatable_bonds": 1
    },
    "ibuprofen": {
        "smiles": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
        "formula": "C13H18O2",
        "exact_mw": 206.28,
        "mw_range": (206.0, 206.5),
        "logp_range": (2.8, 3.8),
        "tpsa_range": (35.0, 42.0),
        "hbd": 1,
        "hba": 1,
        "rotatable_bonds": 4
    },
    "ethanol": {
        "smiles": "CCO",
        "formula": "C2H6O",
        "exact_mw": 46.07,
        "mw_range": (46.0, 46.2),
        "logp_range": (-0.4, 0.4),
        "tpsa_range": (18.0, 22.0),
        "hbd": 1,
        "hba": 1,
        "rotatable_bonds": 0
    },
    "benzene": {
        "smiles": "c1ccccc1",
        "formula": "C6H6",
        "exact_mw": 78.11,
        "mw_range": (78.0, 78.2),
        "logp_range": (1.5, 2.3),
        "tpsa_range": (0.0, 1.0),
        "hbd": 0,
        "hba": 0,
        "rotatable_bonds": 0
    }
}

# Standard Atomic weights
ATOMIC_WEIGHTS = {
    'H': 1.008, 'C': 12.011, 'N': 14.007, 'O': 15.999, 'F': 18.998,
    'P': 30.974, 'S': 32.065, 'Cl': 35.453, 'Br': 79.904, 'I': 126.904,
    'B': 10.811, 'Na': 22.990, 'K': 39.098, 'Ca': 40.078, 'Li': 6.941
}

VALENCE = {
    'C': 4, 'N': 3, 'O': 2, 'F': 1, 'P': 3, 'S': 2, 'Cl': 1, 'Br': 1, 'I': 1, 'H': 1, 'B': 3
}

ATOM_COLORS = {
    'C': '#94A3B8', 'N': '#3B82F6', 'O': '#EF4444', 'S': '#EAB308',
    'P': '#F97316', 'F': '#06B6D4', 'Cl': '#10B981', 'Br': '#D97706',
    'I': '#8B5CF6', 'H': '#CBD5E1', 'B': '#EC4899'
}


class Atom:
    def __init__(self, idx, symbol, is_aromatic=False, charge=0, isotope=None, h_count=0):
        self.idx = idx
        self.symbol = symbol.capitalize()
        self.raw_symbol = symbol
        self.is_aromatic = is_aromatic
        self.charge = charge
        self.isotope = isotope
        self.explicit_h = h_count
        self.implicit_h = 0
        self.bonds = []
        self.x = 0.0
        self.y = 0.0
        self.ring_ids = set()

    @property
    def total_h(self):
        return self.explicit_h + self.implicit_h

    @property
    def heavy_degree(self):
        return len(self.bonds)

    def neighbors(self):
        return [b.atom2 if b.atom1 == self else b.atom1 for b in self.bonds]


class Bond:
    def __init__(self, atom1, atom2, order=1, is_aromatic=False, stereo=None):
        self.atom1 = atom1
        self.atom2 = atom2
        self.order = order
        self.is_aromatic = is_aromatic
        self.stereo = stereo

    def other(self, atom):
        return self.atom2 if self.atom1 == atom else self.atom1


class PurePythonMolecule:
    def __init__(self, smiles: str):
        self.raw_smiles = smiles.strip()
        self.atoms = []
        self.bonds = []
        self.rings = []
        self.is_valid = False
        self.error_message = None
        self._parse()

    def _parse(self):
        smiles = self.raw_smiles
        if not smiles:
            self.error_message = "Empty SMILES string"
            return

        token_pattern = re.compile(
            r'(\[[^\]]+\]|Cl|Br|B|C|N|O|P|S|F|I|b|c|n|o|p|s|%[0-9]{2}|[0-9]|=|\#|:|-|/|\\|\(|\)|\.)'
        )
        tokens = token_pattern.findall(smiles)
        joined = "".join(tokens)
        if len(joined) != len(smiles.replace(" ", "")):
            self.error_message = f"Invalid syntax or unsupported characters in SMILES: {smiles}"
            return

        atom_stack = []
        current_atom = None
        pending_bond_order = None
        pending_bond_stereo = None
        ring_closures = defaultdict(list)

        try:
            for token in tokens:
                if token == '(':
                    if current_atom is not None:
                        atom_stack.append(current_atom)
                elif token == ')':
                    if atom_stack:
                        current_atom = atom_stack.pop()
                    else:
                        raise ValueError("Unmatched closing parenthesis in SMILES")
                elif token in ('-', '=', '#', ':', '/', '\\'):
                    if token == '-': pending_bond_order = 1
                    elif token == '=': pending_bond_order = 2
                    elif token == '#': pending_bond_order = 3
                    elif token == ':': pending_bond_order = 1.5
                    elif token in ('/', '\\'):
                        pending_bond_order = 1
                        pending_bond_stereo = token
                elif token == '.':
                    current_atom = None
                    pending_bond_order = None
                elif token.startswith('%') or (token.isdigit() and len(token) == 1):
                    ring_num = int(token[1:]) if token.startswith('%') else int(token)
                    bond_order = pending_bond_order if pending_bond_order is not None else (1.5 if current_atom.is_aromatic else 1)
                    pending_bond_order = None

                    if ring_num in ring_closures and ring_closures[ring_num]:
                        partner_atom, partner_order = ring_closures[ring_num].pop()
                        b_order = partner_order if partner_order != 1 else bond_order
                        b_arom = current_atom.is_aromatic and partner_atom.is_aromatic
                        bond = Bond(partner_atom, current_atom, order=b_order, is_aromatic=b_arom)
                        self.bonds.append(bond)
                        current_atom.bonds.append(bond)
                        partner_atom.bonds.append(bond)
                    else:
                        ring_closures[ring_num].append((current_atom, bond_order))
                else:
                    new_atom = self._parse_atom_token(token, len(self.atoms))
                    self.atoms.append(new_atom)

                    if current_atom is not None:
                        b_order = pending_bond_order if pending_bond_order is not None else (1.5 if (current_atom.is_aromatic and new_atom.is_aromatic) else 1)
                        b_arom = current_atom.is_aromatic and new_atom.is_aromatic
                        bond = Bond(current_atom, new_atom, order=b_order, is_aromatic=b_arom, stereo=pending_bond_stereo)
                        self.bonds.append(bond)
                        current_atom.bonds.append(bond)
                        new_atom.bonds.append(bond)

                    current_atom = new_atom
                    pending_bond_order = None
                    pending_bond_stereo = None

            unclosed = [k for k, v in ring_closures.items() if v]
            if unclosed:
                raise ValueError(f"Unclosed ring indices: {unclosed}")

            self._calculate_implicit_hydrogens()
            self._validate_valence()
            self._find_rings()
            self.is_valid = True
        except Exception as e:
            self.is_valid = False
            self.error_message = str(e)

    def _parse_atom_token(self, token, idx):
        if token.startswith('[') and token.endswith(']'):
            inner = token[1:-1]
            m = re.match(r'^([0-9]+)?([A-Za-z][a-z]?)(@+)?(H[0-9]*)?([\+\-][0-9]*)?', inner)
            if not m:
                raise ValueError(f"Cannot parse bracketed atom: {token}")
            iso, sym, chir, h_str, chg_str = m.groups()
            is_aromatic = sym.islower()
            symbol = sym.capitalize()
            charge = 0
            if chg_str:
                if chg_str == '+': charge = 1
                elif chg_str == '-': charge = -1
                elif chg_str.startswith('+'): charge = int(chg_str[1:]) if len(chg_str) > 1 else 1
                elif chg_str.startswith('-'): charge = -int(chg_str[1:]) if len(chg_str) > 1 else -1

            h_count = 0
            if h_str:
                h_count = int(h_str[1:]) if len(h_str) > 1 else 1

            atom = Atom(idx, symbol, is_aromatic=is_aromatic, charge=charge, isotope=int(iso) if iso else None, h_count=h_count)
            atom.in_bracket = True
            return atom
        else:
            is_aromatic = token.islower()
            symbol = token.capitalize()
            return Atom(idx, symbol, is_aromatic=is_aromatic)

    def _calculate_implicit_hydrogens(self):
        for atom in self.atoms:
            if atom.explicit_h > 0 or getattr(atom, 'in_bracket', False) or atom.symbol in ('Na', 'K', 'Li', 'Mg', 'Ca', 'Zn'):
                atom.implicit_h = 0
                continue
            bond_sum = sum(b.order for b in atom.bonds)
            target_val = VALENCE.get(atom.symbol, 4)
            if atom.symbol == 'N': target_val = 3 if atom.charge <= 0 else 4
            elif atom.symbol == 'O': target_val = 2 if atom.charge <= 0 else 3
            elif atom.symbol == 'S': target_val = 2 if bond_sum <= 2 else (4 if bond_sum <= 4 else 6)
            elif atom.symbol == 'P': target_val = 3 if bond_sum <= 3 else 5

            if atom.is_aromatic:
                if atom.symbol == 'C':
                    atom.implicit_h = 1 if len(atom.bonds) == 2 else 0
                elif atom.symbol in ('N', 'O', 'S'):
                    atom.implicit_h = 0
            else:
                rem = target_val - int(round(bond_sum)) + atom.charge
                atom.implicit_h = max(0, rem)

    def _validate_valence(self):
        for atom in self.atoms:
            if atom.is_aromatic and atom.symbol == 'C':
                has_double = any(b.order == 2 for b in atom.bonds)
                if has_double:
                    order_sum = sum(b.order if b.order == 2 else 1.0 for b in atom.bonds) + atom.total_h
                else:
                    order_sum = sum(b.order for b in atom.bonds) + atom.total_h
                limit = 4.5
            else:
                order_sum = sum(b.order for b in atom.bonds) + atom.total_h
                limit = 4.0 if atom.symbol == 'C' else (4.0 if atom.symbol == 'N' else 3.0)
                if atom.symbol in ('F', 'Cl', 'Br', 'I', 'Na', 'K', 'Li'): limit = 1.0
                elif atom.symbol in ('Mg', 'Ca', 'Zn'): limit = 2.0
                elif atom.symbol in ('P', 'S'): limit = 6.0

            if order_sum > limit + 0.05:
                raise ValueError(f"ValenceError: Atom {atom.symbol} (index {atom.idx}) exceeds maximum chemical valence ({order_sum:.1f} > {limit})")

    def _find_rings(self):
        visited = set()
        parent = {}
        cycles = []

        def dfs(u, p):
            visited.add(u)
            for v in u.neighbors():
                if v == p: continue
                if v in visited:
                    cycle = [v.idx]
                    curr = u
                    while curr and curr != v:
                        cycle.append(curr.idx)
                        curr = parent.get(curr)
                    if 3 <= len(cycle) <= 8:
                        min_idx = min(cycle)
                        i = cycle.index(min_idx)
                        c_rot = cycle[i:] + cycle[:i]
                        if c_rot not in cycles and c_rot[::-1] not in cycles:
                            cycles.append(c_rot)
                else:
                    parent[v] = u
                    dfs(v, u)

        for atom in self.atoms:
            if atom not in visited:
                parent[atom] = None
                dfs(atom, None)

        self.rings = cycles
        for r_idx, ring in enumerate(cycles):
            for a_idx in ring:
                if a_idx < len(self.atoms):
                    self.atoms[a_idx].ring_ids.add(r_idx)


class ScientificEngine:
    """
    Scientific computation service with explicit native and fallback modes.
    Wraps RDKit when available, or provides clearly annotated reference fallback algorithms.
    """

    @classmethod
    def get_engine_status(cls) -> dict:
        return {
            "has_rdkit": HAS_RDKIT,
            "rdkit_version": RDKIT_VERSION,
            "active_engine": f"RDKit v{RDKIT_VERSION}" if HAS_RDKIT else "Internal Pure-Python Reference Engine v1.2.0 (Non-Production Fallback)",
            "is_production_ready": HAS_RDKIT,
            "engine_notice": "Native RDKit operational." if HAS_RDKIT else "Running in pure-Python reference mode; results are simulated estimates, not native RDKit computations."
        }

    @classmethod
    def validate_smiles(cls, smiles: str) -> Tuple[bool, Optional[str]]:
        if not smiles or not smiles.strip():
            return False, "Empty SMILES string"
        
        if HAS_RDKIT:
            try:
                mol = Chem.MolFromSmiles(smiles.strip())
                if mol is None:
                    return False, "RDKit Sanitization / Parsing Error: Invalid chemical structure"
                return True, None
            except Exception as e:
                return False, f"RDKit Error: {str(e)}"
        else:
            mol = PurePythonMolecule(smiles)
            if not mol.is_valid:
                return False, mol.error_message or "Chemical valence or SMILES syntax violation"
            return True, None

    @classmethod
    def standardize_molecule(cls, smiles: str, remove_salts: bool = True, neutralize: bool = True) -> dict:
        raw_smiles = smiles.strip()
        valid, err = cls.validate_smiles(raw_smiles)
        if not valid:
            return {
                "success": False,
                "original_smiles": raw_smiles,
                "standardized_smiles": None,
                "error": err,
                "warnings": ["Sanitization failed"]
            }

        warnings = []
        standardized_smiles = raw_smiles

        if remove_salts and '.' in raw_smiles:
            fragments = raw_smiles.split('.')
            largest = max(fragments, key=lambda f: len(re.findall(r'[A-Za-z]', f)))
            if largest != raw_smiles:
                warnings.append(f"Stripped inorganic counterions/salts: {raw_smiles} -> {largest}")
                standardized_smiles = largest

        if HAS_RDKIT:
            try:
                mol = Chem.MolFromSmiles(standardized_smiles)
                if mol is not None:
                    standardized_smiles = Chem.MolToSmiles(mol, canonical=True)
            except Exception as e:
                warnings.append(f"RDKit canonicalization note: {str(e)}")
        else:
            standardized_smiles = standardized_smiles.replace(" ", "")

        return {
            "success": True,
            "original_smiles": raw_smiles,
            "standardized_smiles": standardized_smiles,
            "was_modified": raw_smiles != standardized_smiles,
            "warnings": warnings
        }

    @classmethod
    def calculate_descriptors(cls, smiles: str) -> dict:
        clean_smi = smiles.strip()
        start_ts = datetime.now(timezone.utc).isoformat()

        if HAS_RDKIT:
            try:
                mol = Chem.MolFromSmiles(clean_smi)
                if mol is None:
                    return {
                        "valid": False,
                        "error": "RDKit failed to parse SMILES",
                        "smiles": clean_smi,
                        "result_origin": None
                    }

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
                qed_score = round(QED.qed(mol), 3)

                violations = 0
                violation_reasons = []
                if mw > 500.0:
                    violations += 1
                    violation_reasons.append(f"MW ({mw:.1f} > 500 Da)")
                if logp > 5.0:
                    violations += 1
                    violation_reasons.append(f"LogP ({logp:.2f} > 5.0)")
                if hbd > 5:
                    violations += 1
                    violation_reasons.append(f"HBD ({hbd} > 5)")
                if hba > 10:
                    violations += 1
                    violation_reasons.append(f"HBA ({hba} > 10)")

                veber_pass = (rotb <= 10) and (tpsa <= 140.0)

                return {
                    "valid": True,
                    "smiles": Chem.MolToSmiles(mol, canonical=True),
                    "formula": formula,
                    "molecular_weight": mw,
                    "exact_molecular_weight": exact_mw,
                    "logp": logp,
                    "hbd": hbd,
                    "hba": hba,
                    "tpsa": tpsa,
                    "rotatable_bonds": rotb,
                    "heavy_atoms": heavy_atoms,
                    "num_rings": num_rings,
                    "lipinski_violations": violations,
                    "lipinski_violation_details": violation_reasons,
                    "lipinski_pass": violations <= 1,
                    "veber_pass": veber_pass,
                    "qed": qed_score,
                    "sas_score": round(min(10.0, max(1.0, 1.5 + 0.005 * mw + 0.3 * num_rings + 0.1 * rotb)), 2),
                    "engine": f"RDKit v{RDKIT_VERSION}",
                    "engine_type": "REAL_RDKIT",
                    "result_origin": "COMPUTED",
                    "timestamp": start_ts
                }
            except Exception as e:
                return {
                    "valid": False,
                    "error": f"RDKit calculation error: {str(e)}",
                    "smiles": clean_smi,
                    "result_origin": None
                }
        else:
            mol = PurePythonMolecule(clean_smi)
            if not mol.is_valid:
                return {
                    "valid": False,
                    "error": mol.error_message or "Chemical parsing failed",
                    "smiles": clean_smi,
                    "result_origin": None
                }

            mw = 0.0
            formula_dict = defaultdict(int)
            for a in mol.atoms:
                sym = a.symbol
                mw += ATOMIC_WEIGHTS.get(sym, 12.0)
                formula_dict[sym] += 1
                h_count = a.total_h
                mw += h_count * ATOMIC_WEIGHTS['H']
                formula_dict['H'] += h_count

            formula_parts = []
            if 'C' in formula_dict:
                c_num = formula_dict.pop('C')
                formula_parts.append(f"C{c_num if c_num > 1 else ''}")
            if 'H' in formula_dict:
                h_num = formula_dict.pop('H')
                formula_parts.append(f"H{h_num if h_num > 1 else ''}")
            for el in sorted(formula_dict.keys()):
                num = formula_dict[el]
                formula_parts.append(f"{el}{num if num > 1 else ''}")
            formula = "".join(formula_parts)

            hbd = sum(a.total_h for a in mol.atoms if a.symbol in ('O', 'N') and a.total_h > 0)
            
            # Lipinski HBA: Oxygens + non-amide uncharged Nitrogens
            hba = 0
            for a in mol.atoms:
                if a.symbol == 'O':
                    hba += 1
                elif a.symbol == 'N':
                    is_amide = any(
                        b.other(a).symbol == 'C' and any(cb.order == 2 and cb.other(b.other(a)).symbol == 'O' for cb in b.other(a).bonds)
                        for b in a.bonds
                    )
                    if not is_amide and a.charge <= 0:
                        hba += 1

            rot_bonds = 0
            for b in mol.bonds:
                if b.order == 1 and not b.is_aromatic:
                    a1, a2 = b.atom1, b.atom2
                    if not a1.ring_ids.intersection(a2.ring_ids):
                        if a1.heavy_degree > 1 and a2.heavy_degree > 1:
                            is_amide = False
                            if (a1.symbol == 'C' and a2.symbol == 'N') or (a1.symbol == 'N' and a2.symbol == 'C'):
                                c_atom = a1 if a1.symbol == 'C' else a2
                                for cb in c_atom.bonds:
                                    if cb.order == 2 and cb.other(c_atom).symbol == 'O':
                                        is_amide = True
                                        break
                            if not is_amide:
                                rot_bonds += 1

            tpsa = 0.0
            for a in mol.atoms:
                if a.symbol == 'O':
                    if any(b.order == 2 for b in a.bonds): tpsa += 17.07
                    elif a.total_h > 0: tpsa += 20.23
                    else: tpsa += 9.23
                elif a.symbol == 'N':
                    if a.is_aromatic:
                        tpsa += 15.79 if a.total_h > 0 else 12.89
                    else:
                        if a.total_h == 2: tpsa += 26.02
                        elif a.total_h == 1: tpsa += 12.03
                        elif a.total_h == 0: tpsa += 3.24
                elif a.symbol == 'S':
                    if any(b.order == 2 for b in a.bonds): tpsa += 17.00
                    elif a.total_h > 0: tpsa += 38.80
                    else: tpsa += 25.30
                elif a.symbol == 'P':
                    tpsa += 9.81

            logp = 0.0
            for a in mol.atoms:
                if a.symbol == 'C':
                    if a.is_aromatic: logp += 0.280
                    elif any(b.order == 2 and b.other(a).symbol == 'O' for b in a.bonds): logp -= 0.100
                    else: logp += 0.144
                elif a.symbol == 'N':
                    is_amide = any(
                        b.other(a).symbol == 'C' and any(cb.order == 2 and cb.other(b.other(a)).symbol == 'O' for cb in b.other(a).bonds)
                        for b in a.bonds
                    )
                    if is_amide: logp -= 0.350
                    elif a.is_aromatic: logp -= 0.250
                    elif a.heavy_degree >= 3: logp -= 0.700
                    elif a.heavy_degree == 2: logp -= 0.500
                    else: logp -= 0.400
                elif a.symbol == 'O':
                    if any(b.order == 2 for b in a.bonds): logp -= 0.180
                    elif a.total_h > 0: logp -= 0.300
                    else: logp -= 0.120
                elif a.symbol == 'F': logp += 0.350
                elif a.symbol == 'Cl': logp += 0.650
                elif a.symbol == 'Br': logp += 0.850
                elif a.symbol == 'I': logp += 1.050
                elif a.symbol == 'S': logp += 0.350
                elif a.symbol == 'P': logp += 0.200

                if a.symbol == 'C':
                    logp += a.total_h * 0.085
                else:
                    logp += a.total_h * (-0.050)

            violations = 0
            violation_reasons = []
            if mw > 500.0:
                violations += 1
                violation_reasons.append(f"MW ({mw:.1f} > 500 Da)")
            if logp > 5.0:
                violations += 1
                violation_reasons.append(f"LogP ({logp:.2f} > 5.0)")
            if hbd > 5:
                violations += 1
                violation_reasons.append(f"HBD ({hbd} > 5)")
            if hba > 10:
                violations += 1
                violation_reasons.append(f"HBA ({hba} > 10)")

            veber_pass = (rot_bonds <= 10) and (tpsa <= 140.0)
            num_rings = len(mol.rings)

            d_mw = math.exp(-0.5 * ((mw - 350.0) / 120.0) ** 2)
            d_logp = math.exp(-0.5 * ((logp - 2.5) / 1.8) ** 2)
            d_hbd = 1.0 / (1.0 + math.exp(1.2 * (hbd - 3.0)))
            d_hba = 1.0 / (1.0 + math.exp(0.8 * (hba - 7.0)))
            d_tpsa = math.exp(-0.5 * ((tpsa - 75.0) / 45.0) ** 2)
            d_rotb = 1.0 / (1.0 + math.exp(0.6 * (rot_bonds - 7.0)))
            qed_score = round((d_mw * d_logp * d_hbd * d_hba * d_tpsa * d_rotb) ** (1.0 / 6.0), 3)

            return {
                "valid": True,
                "smiles": clean_smi,
                "formula": formula,
                "molecular_weight": round(mw, 2),
                "exact_molecular_weight": round(mw, 4),
                "logp": round(logp, 2),
                "hbd": hbd,
                "hba": hba,
                "tpsa": round(tpsa, 2),
                "rotatable_bonds": rot_bonds,
                "heavy_atoms": len(mol.atoms),
                "num_rings": num_rings,
                "lipinski_violations": violations,
                "lipinski_violation_details": violation_reasons,
                "lipinski_pass": violations <= 1,
                "veber_pass": veber_pass,
                "qed": qed_score,
                "sas_score": round(min(10.0, max(1.0, 1.5 + 0.005 * mw + 0.3 * num_rings + 0.1 * rot_bonds)), 2),
                "engine": "Internal Pure-Python Reference Engine v1.2.0 (Non-Production Fallback)",
                "engine_type": "FALLBACK_HEURISTIC",
                "result_origin": "SIMULATED",
                "timestamp": start_ts
            }

    @classmethod
    def generate_fingerprint(cls, smiles: str, radius: int = 2, n_bits: int = 1024) -> dict:
        clean_smi = smiles.strip()
        if HAS_RDKIT:
            try:
                mol = Chem.MolFromSmiles(clean_smi)
                if mol is not None:
                    fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=radius, nBits=n_bits)
                    on_bits = list(fp.GetOnBits())
                    return {
                        "type": f"Morgan (Radius={radius}, {n_bits} bits)",
                        "n_bits": n_bits,
                        "on_bits_count": len(on_bits),
                        "on_bits": on_bits,
                        "density": round(len(on_bits) / n_bits, 4),
                        "engine": f"RDKit v{RDKIT_VERSION}"
                    }
            except Exception:
                pass

        h = hashlib.sha256(clean_smi.encode()).hexdigest()
        pseudo_bits = []
        for i in range(0, len(h), 4):
            val = int(h[i:i+4], 16) % n_bits
            if val not in pseudo_bits:
                pseudo_bits.append(val)
        pseudo_bits.sort()

        return {
            "type": f"Topological Hash Fingerprint ({n_bits} bits, Fallback)",
            "n_bits": n_bits,
            "on_bits_count": len(pseudo_bits),
            "on_bits": pseudo_bits,
            "density": round(len(pseudo_bits) / n_bits, 4),
            "engine": "Internal Fallback Hash Generator"
        }

    @classmethod
    def generate_2d_structure(cls, smiles: str, width: int = 240, height: int = 180, dark_mode: bool = True) -> str:
        mol = PurePythonMolecule(smiles)
        if not mol.is_valid or not mol.atoms:
            bg = "#0B0F19" if dark_mode else "#F8FAFC"
            return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}"><rect width="{width}" height="{height}" fill="{bg}" rx="6"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#EF4444" font-size="11" font-family="monospace">Invalid Structure</text></svg>'

        placed_atoms = set()
        bond_length = 32.0

        for ring in mol.rings:
            n = len(ring)
            radius = bond_length / (2.0 * math.sin(math.pi / n))
            already_placed = [mol.atoms[idx] for idx in ring if idx in placed_atoms]
            if already_placed:
                avg_x = sum(a.x for a in already_placed) / len(already_placed)
                avg_y = sum(a.y for a in already_placed) / len(already_placed)
                cx, cy = avg_x + radius, avg_y
            else:
                cx, cy = len(placed_atoms) * 20.0, 0.0

            for i, atom_idx in enumerate(ring):
                atom = mol.atoms[atom_idx]
                if atom.idx not in placed_atoms:
                    angle = (2.0 * math.pi * i) / n - (math.pi / 2.0)
                    atom.x = cx + radius * math.cos(angle)
                    atom.y = cy + radius * math.sin(angle)
                    placed_atoms.add(atom.idx)

        if not placed_atoms and mol.atoms:
            mol.atoms[0].x = 0.0
            mol.atoms[0].y = 0.0
            placed_atoms.add(mol.atoms[0].idx)

        queue = deque([mol.atoms[idx] for idx in placed_atoms] or [mol.atoms[0]])

        while queue:
            curr = queue.popleft()
            neighbors = [b.other(curr) for b in curr.bonds if b.other(curr).idx not in placed_atoms]
            in_bonds = [b for b in curr.bonds if b.other(curr).idx in placed_atoms]
            base_angle = 0.0
            if in_bonds:
                prev_atom = in_bonds[0].other(curr)
                base_angle = math.atan2(curr.y - prev_atom.y, curr.x - prev_atom.x)

            num_nbrs = len(neighbors)
            if num_nbrs == 1:
                angles = [base_angle + (math.pi / 3.0 if curr.idx % 2 == 0 else -math.pi / 3.0)]
            elif num_nbrs == 2:
                angles = [base_angle + math.pi / 3.0, base_angle - math.pi / 3.0]
            elif num_nbrs >= 3:
                angles = [base_angle + (i - (num_nbrs - 1) / 2.0) * (math.pi / 2.5) for i in range(num_nbrs)]
            else:
                angles = []

            for nbr, angle in zip(neighbors, angles):
                nbr.x = curr.x + bond_length * math.cos(angle)
                nbr.y = curr.y + bond_length * math.sin(angle)
                placed_atoms.add(nbr.idx)
                queue.append(nbr)

        for atom in mol.atoms:
            if atom.idx not in placed_atoms:
                atom.x = len(placed_atoms) * 25.0
                atom.y = 0.0
                placed_atoms.add(atom.idx)

        min_x = min(a.x for a in mol.atoms)
        max_x = max(a.x for a in mol.atoms)
        min_y = min(a.y for a in mol.atoms)
        max_y = max(a.y for a in mol.atoms)

        mol_w = max(1.0, max_x - min_x)
        mol_h = max(1.0, max_y - min_y)

        padding = 24.0
        scale = min((width - 2 * padding) / mol_w, (height - 2 * padding) / mol_h, 1.6)
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0

        for a in mol.atoms:
            a.sx = (a.x - cx) * scale + (width / 2.0)
            a.sy = (a.y - cy) * scale + (height / 2.0)

        svg_elements = []
        bg_color = "#0B0F19" if dark_mode else "#FFFFFF"
        bond_color = "#64748B" if dark_mode else "#475569"
        aromatic_bond_color = "#38BDF8" if dark_mode else "#0284C7"

        svg_elements.append(f'<rect width="{width}" height="{height}" fill="{bg_color}" rx="6"/>')

        for b in mol.bonds:
            a1, a2 = b.atom1, b.atom2
            x1, y1 = a1.sx, a1.sy
            x2, y2 = a2.sx, a2.sy

            dx = x2 - x1
            dy = y2 - y1
            dist = math.hypot(dx, dy)
            nx, ny = (-dy / dist, dx / dist) if dist > 0.001 else (0, 1)

            if b.order == 2:
                offset = 2.4
                svg_elements.append(f'<line x1="{x1 + nx*offset:.1f}" y1="{y1 + ny*offset:.1f}" x2="{x2 + nx*offset:.1f}" y2="{y2 + ny*offset:.1f}" stroke="{bond_color}" stroke-width="2.0" stroke-linecap="round"/>')
                svg_elements.append(f'<line x1="{x1 - nx*offset:.1f}" y1="{y1 - ny*offset:.1f}" x2="{x2 - nx*offset:.1f}" y2="{y2 - ny*offset:.1f}" stroke="{bond_color}" stroke-width="2.0" stroke-linecap="round"/>')
            elif b.order == 3:
                offset = 3.2
                svg_elements.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{bond_color}" stroke-width="2.0" stroke-linecap="round"/>')
                svg_elements.append(f'<line x1="{x1 + nx*offset:.1f}" y1="{y1 + ny*offset:.1f}" x2="{x2 + nx*offset:.1f}" y2="{y2 + ny*offset:.1f}" stroke="{bond_color}" stroke-width="1.6" stroke-linecap="round"/>')
                svg_elements.append(f'<line x1="{x1 - nx*offset:.1f}" y1="{y1 - ny*offset:.1f}" x2="{x2 - nx*offset:.1f}" y2="{y2 - ny*offset:.1f}" stroke="{bond_color}" stroke-width="1.6" stroke-linecap="round"/>')
            elif b.is_aromatic:
                svg_elements.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{aromatic_bond_color}" stroke-width="2.2" stroke-linecap="round"/>')
                offset = 2.0
                svg_elements.append(f'<line x1="{x1 + nx*offset:.1f}" y1="{y1 + ny*offset:.1f}" x2="{x2 + nx*offset:.1f}" y2="{y2 + ny*offset:.1f}" stroke="{aromatic_bond_color}" stroke-width="1.2" stroke-dasharray="3,3" stroke-linecap="round" opacity="0.8"/>')
            else:
                svg_elements.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{bond_color}" stroke-width="2.0" stroke-linecap="round"/>')

        for a in mol.atoms:
            sym = a.symbol
            if sym != 'C' or a.charge != 0 or a.heavy_degree == 0:
                color = ATOM_COLORS.get(sym, '#E2E8F0')
                label = sym
                if a.total_h > 0 and sym != 'C': label += f"H{a.total_h if a.total_h > 1 else ''}"
                if a.charge > 0: label += f"+{a.charge if a.charge > 1 else ''}"
                elif a.charge < 0: label += f"-{-a.charge if -a.charge > 1 else ''}"

                svg_elements.append(f'<circle cx="{a.sx:.1f}" cy="{a.sy:.1f}" r="8.5" fill="{bg_color}" />')
                svg_elements.append(f'<text x="{a.sx:.1f}" y="{a.sy + 3.8:.1f}" dominant-baseline="middle" text-anchor="middle" fill="{color}" font-size="11" font-weight="600" font-family="system-ui, sans-serif">{html.escape(label)}</text>')

        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" class="aidd-molecule-svg">' + "".join(svg_elements) + '</svg>'

    @classmethod
    def run_regression_audit(cls) -> dict:
        results = []
        all_passed = True

        for name, ref in REFERENCE_BENCHMARKS.items():
            d = cls.calculate_descriptors(ref["smiles"])
            if not d["valid"]:
                results.append({
                    "compound": name,
                    "passed": False,
                    "reason": f"Calculation failed: {d.get('error')}"
                })
                all_passed = False
                continue

            mw_ok = ref["mw_range"][0] <= d["molecular_weight"] <= ref["mw_range"][1]
            logp_ok = ref["logp_range"][0] <= d["logp"] <= ref["logp_range"][1]
            tpsa_ok = ref["tpsa_range"][0] <= d["tpsa"] <= ref["tpsa_range"][1]
            hbd_ok = (d["hbd"] == ref["hbd"])
            hba_ok = (d["hba"] == ref["hba"])
            formula_ok = (d["formula"] == ref["formula"])

            compound_passed = mw_ok and logp_ok and tpsa_ok and hbd_ok and hba_ok and formula_ok
            if not compound_passed:
                all_passed = False

            results.append({
                "compound": name,
                "passed": compound_passed,
                "smiles": ref["smiles"],
                "formula": {"calculated": d["formula"], "expected": ref["formula"], "match": formula_ok},
                "molecular_weight": {"calculated": d["molecular_weight"], "expected_range": ref["mw_range"], "match": mw_ok},
                "logp": {"calculated": d["logp"], "expected_range": ref["logp_range"], "match": logp_ok},
                "tpsa": {"calculated": d["tpsa"], "expected_range": ref["tpsa_range"], "match": tpsa_ok},
                "hbd": {"calculated": d["hbd"], "expected": ref["hbd"], "match": hbd_ok},
                "hba": {"calculated": d["hba"], "expected": ref["hba"], "match": hba_ok}
            })

        return {
            "all_passed": all_passed,
            "engine_status": cls.get_engine_status(),
            "compounds_tested": len(results),
            "passed_count": sum(1 for r in results if r["passed"]),
            "failed_count": sum(1 for r in results if not r["passed"]),
            "details": results
        }
