"""Adversarial impostor, never an attested engine. Portable replacement for shell execution."""
import sys
from pathlib import Path

print('AutoDock Vina 36dd023-mod')
if '--config' in sys.argv:
    config = Path(sys.argv[sys.argv.index('--config') + 1])
    fields = dict(line.split('=', 1) for line in config.read_text().splitlines() if '=' in line)
    fields = {key.strip(): value.strip() for key, value in fields.items()}
    source = Path(fields['ligand']).read_text()
    Path(fields['out']).write_text('MODEL 1\nREMARK VINA RESULT: -8.7 0 0\n' + source + '\nENDMDL\n')
    print('mode |   affinity | dist from best mode\n1 -8.7 0 0')
