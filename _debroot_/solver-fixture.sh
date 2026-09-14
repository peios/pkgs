set -eu
mkdir -p /tmp/repo
for spec in 'pekit-fixture-beta 1.0' 'pekit-fixture-beta 2.0' 'pekit-fixture-alpha 1.0'; do
  set -- $spec
  name=$1; version=$2
  root=/tmp/$name-$version
  mkdir -p "$root/DEBIAN"
  printf 'Package: %s\nVersion: %s\nArchitecture: all\nMaintainer: Test <test@example.invalid>\nDescription: disposable apt solver test\n' "$name" "$version" > "$root/DEBIAN/control"
  if [ "$name" = pekit-fixture-alpha ]; then printf 'Depends: pekit-fixture-beta (>= 2.0)\n' >> "$root/DEBIAN/control"; fi
  dpkg-deb --build "$root" "/tmp/repo/$name-$version.deb"
done
cd /tmp/repo
for deb in *.deb; do
  dpkg-deb -f "$deb"
  printf 'Filename: %s\nSize: %s\nSHA256: %s\n\n' "$deb" "$(stat -c %s "$deb")" "$(sha256sum "$deb" | cut -d' ' -f1)"
done > Packages
gzip -k Packages
rm /etc/apt/sources.list.d/debian.sources
printf 'deb [trusted=yes] file:/tmp/repo ./\n' > /etc/apt/sources.list
