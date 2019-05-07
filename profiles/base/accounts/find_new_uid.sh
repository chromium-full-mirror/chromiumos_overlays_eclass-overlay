#!/bin/bash
set -euo pipefail

files="$(dirname $0)/user/*"
echo -n "Your new UID is: "
awk --field-separator : '
  BEGIN { max = 20099 }
  /^uid:/ { if ($2 <= 29999 && $2 > max) max = $2 }
  END { print max + 1}' $files
