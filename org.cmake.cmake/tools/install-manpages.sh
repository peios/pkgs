#!/bin/sh
set -eu
stage=$1
version=$2
mkdir -p "$stage/usr/share/man/man1"
for tool in cmake ctest cpack; do
  case "$tool" in
    cmake) purpose='configure and generate project build systems' ;;
    ctest) purpose='run project tests and submit testing dashboards' ;;
    cpack) purpose='generate installers and binary distribution packages' ;;
  esac
  "$stage/usr/bin/$tool" --help > "$stage/.command-help"
  test -s "$stage/.command-help"
  {
    printf '.TH "%s" "1" "" "CMake %s" "User Commands"\n' "$tool" "$version"
    printf '.SH NAME\n%s \\- %s\n' "$tool" "$purpose"
    printf '.SH SYNOPSIS\n.B %s\n[options]\n' "$tool"
    printf '.SH DESCRIPTION\nCommand-line reference generated from the packaged executable.\n'
    printf 'For the complete installed reference, run\n.B "%s --help-manual %s(1)"\n.\n' "$tool" "$tool"
    printf '.SH OPTIONS\n.nf\n'
    sed -e 's/\\/\\e/g' -e "s/^[.']/\\\\\&&/" "$stage/.command-help"
    printf '.fi\n.SH SEE ALSO\n.BR cmake (1),\n.BR ctest (1),\n.BR cpack (1)\n'
  } > "$stage/.command-man"
  gzip -n -9 -c "$stage/.command-man" > "$stage/usr/share/man/man1/$tool.1.gz"
done
rm -f "$stage/.command-help" "$stage/.command-man"
