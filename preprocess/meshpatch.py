import numpy as np
import pyvista as pv
import pymeshfix
from pymeshfix import PyTMesh
import pymeshlab as pml
import argparse

# takes in a file
def get_parser() -> argparse:
    parser = argparse.ArgumentParser(description='create datasets(noisy mesh & smoothed mesh) from a single clean mesh')
    parser.add_argument('-i', '--input', type=str, required=True)
    parser.add_argument('-o', '--output', type=str, required=True)
    args = parser.parse_args()
    return args

class MeshRepair:
    # Fills all the holes having at least 'nbe' boundary edges. If
    # 'refine' is true, adds inner vertices to reproduce the
    # sampling density of the surroundings. Returns number of holes
    # patched.  If 'nbe' is 0 (default), all the holes are patched.
    def fillBoundaries(mfix):
        mfix.remove_smallest_components()
        mfix.fill_small_boundaries(nbe=1, refine=True)
        mfix.clean(max_iters=5, inner_loops=0.5)
        vert, faces = mfix.return_arrays()
        mfix = pymeshfix.MeshFix(vert, faces)
        #repairs holes and removes artifacts
        mfix.repair()

class MeshPatch: 
    def meshPatch(input, output):
        #patches simple holes
        pymeshfix.clean_from_file(input, output)

class PyMeshLab:
    #pymeshlab functions to clean mesh before dual DMP
    def selfIntersections(ms):
        ms.compute_selection_by_self_intersections_per_face()
        ms.meshing_remove_selected_vertices()
    def removeTVertices(ms):
        ms.meshing_remove_t_vertices()
    def removeDuplicates(ms):
        ms.meshing_remove_duplicate_faces()
        ms.meshing_remove_duplicate_vertices()
        ms.meshing_remove_null_faces()
    def repairManifold(ms):
        ms.meshing_repair_non_manifold_edges()
    def removeConnected(ms):
        ms.meshing_remove_connected_component_by_diameter()

def main(): 
    args = get_parser()
    print(args)
    ms = pml.MeshSet()
    ms.load_new_mesh(args.input)
    #clean mesh with MeshLab, save to file. 
    PyMeshLab.selfIntersections(ms)
    PyMeshLab.removeTVertices(ms)
    PyMeshLab.removeDuplicates(ms)
    PyMeshLab.repairManifold(ms)
    PyMeshLab.removeConnected(ms)
    ms.save_current_mesh('mesh.ply')
    mesh = pv.read(args.input)
    mesh.save('mesh2.ply')
    #converts it to a PyTMesh object
    mfix = PyTMesh()
    mfix.load_file('mesh2.ply')
    MeshRepair.fillBoundaries(mfix)    
    mfix.save_file(args.input) 
    MeshPatch.meshPatch(args.input, args.output)
    

if __name__ == "__main__":
    main()