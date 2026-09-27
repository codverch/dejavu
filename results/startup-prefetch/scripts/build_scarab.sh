#!/bin/bash
# Build Scarab from one worktree on phoebe-login and ship it to the pod.
#
#   build_scarab.sh <worktree>        e.g. /h/deepanjm/dejavu-wt/baseline
#
# The pod cannot see /h and has no build toolchain for this tree, so the binary is built here
# with the conda-provided dependencies (agentic-stuff/env.sh) and copied, with the shared
# libraries it needs, to $POD_ROOT/scarab/<branch>-<sha>/ (run it with LD_LIBRARY_PATH=lib).
# The CMake cache holds absolute paths, so every worktree has its own build directory.
set -euo pipefail
WT=$(cd "${1:?worktree}" && pwd)
POD_ROOT=${POD_ROOT:-/localdisk/deepanjm/isca-traces/startup-prefetch}
KX="kubectl exec -i -n deepanjm deepanjm-a100 -c work --"
source /h/deepanjm/agentic-stuff/env.sh >/dev/null 2>&1
export SCARAB_ROOT=$WT
cd "$WT/src"
[ -f build/opt/Makefile ] || make build/opt/Makefile BUILD_TYPE=SCARABOPT CC=gcc CXX=g++ ASM=as
make gitrev
make -j4 -C build/opt
BR=$(git -C "$WT" rev-parse --abbrev-ref HEAD); SHA=$(git -C "$WT" rev-parse --short HEAD)
DIRTY=$(git -C "$WT" status --porcelain -- src | grep -q . && echo "-dirty" || true)
PKG=$(mktemp -d); mkdir -p "$PKG/scarab/lib"
cp build/opt/scarab "$PKG/scarab/"
cp -L build/opt/deps/dynamorio/lib64/release/libdynamorio.so "$PKG/scarab/lib/"
for l in liblz4.so.1 libz.so.1 libsnappy.so.1 libstdc++.so.6 libgcc_s.so.1; do cp -L "$CONDA_ENV/lib/$l" "$PKG/scarab/lib/"; done
cp PARAMS.golden_cove "$PKG/scarab/"
[ -f PARAMS.golden_cove_pow2 ] && cp PARAMS.golden_cove_pow2 "$PKG/scarab/"
echo "$BR $SHA$DIRTY" > "$PKG/scarab/VERSION"
DEST=$POD_ROOT/scarab/$BR-$SHA$DIRTY
tar -C "$PKG" -czf - scarab | $KX bash -c "rm -rf $DEST && mkdir -p $DEST && tar -C $DEST --strip-components=1 -xzf - && LD_LIBRARY_PATH=$DEST/lib ldd $DEST/scarab | grep -q 'not found' && exit 1 || true"
rm -rf "$PKG"
echo "$DEST"
