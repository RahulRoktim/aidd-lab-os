#!/bin/sh
# Deliberately fake executable for regression testing.  It prints a
# Vina-shaped numeric table and exits zero, but it never identifies itself as
# AutoDock Vina and never creates an output PDBQT.
printf '%s\n' \
  'mode |   affinity | dist from best mode' \
  '     | (kcal/mol) | rmsd l.b.| rmsd u.b.' \
  '-----+------------+----------+----------' \
  '   1         -9.9      0.000      0.000'
exit 0
