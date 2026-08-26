#!/bin/sh
# Round-2 adversarial fixture: it can self-identify, print a convincing table,
# move ligand coordinates, and create a structurally plausible PDBQT. It must
# still be rejected because its executable digest is not release-trusted.
if [ "$1" = "--version" ]; then
  printf '%s\n' 'AutoDock Vina 36dd023-mod'
  exit 0
fi

config_file=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--config" ]; then
    config_file="$2"
    shift 2
  else
    shift
  fi
done

ligand_path=$(sed -n 's/^ligand = //p' "$config_file")
output_path=$(sed -n 's/^out = //p' "$config_file")

{
  printf '%s\n' 'MODEL 1' 'REMARK VINA RESULT:    -8.700      0.000      0.000'
  awk '
    /^(ATOM|HETATM)/ {
      x = substr($0, 31, 8) + 1.250
      y = substr($0, 39, 8) + 1.250
      z = substr($0, 47, 8) + 1.250
      printf "%s%8.3f%8.3f%8.3f%s\n", substr($0, 1, 30), x, y, z, substr($0, 55)
      next
    }
    { print }
  ' "$ligand_path"
  printf '%s\n' 'ENDMDL'
} > "$output_path"

printf '%s\n' \
  'AutoDock Vina 36dd023-mod' \
  'mode |   affinity | dist from best mode' \
  '     | (kcal/mol) | rmsd l.b.| rmsd u.b.' \
  '-----+------------+----------+----------' \
  '   1         -8.7      0.000      0.000'
exit 0
