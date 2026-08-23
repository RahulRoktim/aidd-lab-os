import re
import math
from collections import defaultdict, deque

# Atomic weights
ATOMIC_WEIGHTS = {
    'H': 1.008, 'C': 12.011, 'N': 14.007, 'O': 15.999, 'F': 18.998,
    'P': 30.974, 'S': 32.065, 'Cl': 35.453, 'Br': 79.904, 'I': 126.904,
    'B': 10.811, 'Na': 22.990, 'K': 39.098, 'Ca': 40.078
}

# TPSA atom contributions (Ertl et al., 2000)
TPSA_VALUES = {
    'N_3_0': 3.24,   # tertiary amine (R3N)
    'N_2_1': 12.03,  # secondary amine (R2NH)
    'N_1_2': 26.02,  # primary amine (RNH2)
    'N_aro_0': 12.89, # aromatic nitrogen (pyridine-like)
    'N_aro_1': 15.79, # aromatic NH (pyrrole-like)
    'N_double_0': 12.36, # R=N-R
    'N_amide_0': 3.01, # tertiary amide
    'N_amide_1': 16.61, # secondary amide
    'N_amide_2': 29.10, # primary amide
    'N_nitro': 45.0, # nitro N+O2
    'O_single_0': 9.23,  # ether / ester oxygen (-O-)
    'O_single_1': 20.23, # alcohol / phenol (-OH)
    'O_double_0': 17.07, # carbonyl (=O)
    'O_acid': 37.3,      # carboxylic acid / carboxylate
    'S_single_0': 25.3,  # thioether
    'S_single_1': 38.8,  # thiol (-SH)
    'S_double_0': 17.0,  # sulfoxide / sulfone (=S or S=O)
    'P_0': 9.81
}

# Crippen LogP atomic contributions (simplified Wildman & Crippen 1999)
LOGP_CONTRIBUTIONS = {
    'C_aliphatic': 0.144,
    'C_aromatic': 0.358,
    'C_carbonyl': -0.210,
    'C_halogenated': 0.220,
    'H_carbon': 0.110,
    'H_hetero': -0.300,
    'N_amine_aliphatic': -0.800,
    'N_amine_aromatic': -0.400,
    'N_amide': -0.700,
    'N_aromatic': -0.350,
    'O_ether': -0.150,
    'O_alcohol': -0.500,
    'O_carbonyl': -0.350,
    'F': 0.420,
    'Cl': 0.690,
    'Br': 0.860,
    'I': 1.100,
    'S': 0.350,
    'P': 0.200
}

print("Constants loaded successfully")
