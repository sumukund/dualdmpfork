import numpy as np
import pyvista as pv
import pymeshfix
from pymeshfix import PyTMesh
import argparse
import argparse

# takes in a file
def get_parser():
    parser = argparse.ArgumentParser(description='create datasets(noisy mesh & smoothed mesh) from a single clean mesh')
    parser.add_argument('-i', '--input', type=str, required=True)
    parser.add_argument('-o', '--output', type=str, required=True)
    args = parser.parse_args()

    for k, v in vars(args).items():
        print('{:12s}: {}'.format(k, v))

    return args

filename = args.input

orig_mesh = pv.read(filename)
#converts it to a PyTMesh object
mfix = PyTMesh(False)
mfix.load_file(filename)

# Fills all the holes having at least 'nbe' boundary edges. If
# 'refine' is true, adds inner vertices to reproduce the
# sampling density of the surroundings. Returns number of holes
# patched.  If 'nbe' is 0 (default), all the holes are patched.

mfix.fill_small_boundaries(nbe=1, refine=True)
mfix.clean(max_iters=5, inner_loops=0.5)
vert, faces = mfix.return_arrays()
mfix = pymeshfix.MeshFix(vert, faces)
#repairs holes and removes artifacts
#mfix.repair()
mfix.plot()
mfix.save(args.input)