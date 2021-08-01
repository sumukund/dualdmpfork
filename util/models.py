import numpy as np
import torch
from functools import reduce
import scipy as sp
from sklearn.preprocessing import normalize

class Dataset:
    def __init__(self, data):
        self.keys = data.keys
        self.num_nodes = data.num_nodes
        self.num_edges = data.num_edges
        self.num_node_features = data.num_node_features
        self.contains_isolated_nodes = data.contains_isolated_nodes()
        self.contains_self_loops = data.contains_self_loops()
        self.z1 = data['z1']
        self.z2 = data['z2']
        self.x_pos = data['x_pos']
        self.x_norm = data['x_norm']
        self.edge_index = data['edge_index']

class Mesh:
    def __init__(self, path):
        self.path = path
        self.vs, self.faces = self.fill_from_file(path)
        self.fn, self.fa = self.compute_face_normals()
        self.device = 'cpu'
        self.build_gemm() #self.edges, self.ve
        self.vn = self.compute_vert_normals()
        #self.build_uni_lap()
        self.build_vf()
        self.build_mesh_lap()
        self.build_div()
        #self.poisson_mesh_edit()
    
    def fill_from_file(self, path):
        vs, faces = [], []
        f = open(path)
        for line in f:
            line = line.strip()
            splitted_line = line.split()
            if not splitted_line:
                continue
            elif splitted_line[0] == 'v':
                vs.append([float(v) for v in splitted_line[1:4]])
            elif splitted_line[0] == 'f':
                face_vertex_ids = [int(c.split('/')[0]) for c in splitted_line[1:]]
                assert len(face_vertex_ids) == 3
                face_vertex_ids = [(ind - 1) if (ind >= 0) else (len(vs) + ind) for ind in face_vertex_ids]
                faces.append(face_vertex_ids)
        f.close()
        vs = np.asarray(vs)
        faces = np.asarray(faces, dtype=int)

        assert np.logical_and(faces >= 0, faces < len(vs)).all()
        return vs, faces

    def build_gemm(self):
        self.ve = [[] for _ in self.vs]
        self.vei = [[] for _ in self.vs]
        edge_nb = []
        sides = []
        edge2key = dict()
        edges = []
        edges_count = 0
        nb_count = []
        for face_id, face in enumerate(self.faces):
            faces_edges = []
            for i in range(3):
                cur_edge = (face[i], face[(i + 1) % 3])
                faces_edges.append(cur_edge)
            for idx, edge in enumerate(faces_edges):
                edge = tuple(sorted(list(edge)))
                faces_edges[idx] = edge
                if edge not in edge2key:
                    edge2key[edge] = edges_count
                    edges.append(list(edge))
                    edge_nb.append([-1, -1, -1, -1])
                    sides.append([-1, -1, -1, -1])
                    self.ve[edge[0]].append(edges_count)
                    self.ve[edge[1]].append(edges_count)
                    self.vei[edge[0]].append(0)
                    self.vei[edge[1]].append(1)
                    nb_count.append(0)
                    edges_count += 1
            for idx, edge in enumerate(faces_edges):
                edge_key = edge2key[edge]
                edge_nb[edge_key][nb_count[edge_key]] = edge2key[faces_edges[(idx + 1) % 3]]
                edge_nb[edge_key][nb_count[edge_key] + 1] = edge2key[faces_edges[(idx + 2) % 3]]
                nb_count[edge_key] += 2
            for idx, edge in enumerate(faces_edges):
                edge_key = edge2key[edge]
                sides[edge_key][nb_count[edge_key] - 2] = nb_count[edge2key[faces_edges[(idx + 1) % 3]]] - 1
                sides[edge_key][nb_count[edge_key] - 1] = nb_count[edge2key[faces_edges[(idx + 2) % 3]]] - 2
        self.edges = np.array(edges, dtype=np.int32)
        self.gemm_edges = np.array(edge_nb, dtype=np.int64)
        self.sides = np.array(sides, dtype=np.int64)
        self.edges_count = edges_count
        # lots of DS for loss

        self.nvs, self.nvsi, self.nvsin, self.ve_in = [], [], [], []
        for i, e in enumerate(self.ve):
            self.nvs.append(len(e))
            self.nvsi += len(e) * [i]
            self.nvsin += list(range(len(e)))
            self.ve_in += e
        self.vei = reduce(lambda a, b: a + b, self.vei, [])
        self.vei = torch.from_numpy(np.array(self.vei).ravel()).to(self.device).long()
        self.nvsi = torch.from_numpy(np.array(self.nvsi).ravel()).to(self.device).long()
        self.nvsin = torch.from_numpy(np.array(self.nvsin).ravel()).to(self.device).long()
        self.ve_in = torch.from_numpy(np.array(self.ve_in).ravel()).to(self.device).long()

        self.max_nvs = max(self.nvs)
        self.nvs = torch.Tensor(self.nvs).to(self.device).float()
        self.edge2key = edge2key

    def compute_face_normals(self):
        face_normals = np.cross(self.vs[self.faces[:, 1]] - self.vs[self.faces[:, 0]], self.vs[self.faces[:, 2]] - self.vs[self.faces[:, 1]])
        norm = np.sqrt(np.sum(np.square(face_normals), 1))
        face_areas = 0.5 * np.sqrt((face_normals**2).sum(axis=1))
        face_normals /= np.tile(norm, (3, 1)).T

        return face_normals, face_areas

    def compute_vert_normals(self):
        vert_normals = np.zeros((3, len(self.vs)))
        face_normals = self.fn
        faces = self.faces

        nv = len(self.vs)
        nf = len(faces)
        mat_rows = faces.reshape(-1)
        mat_cols = np.array([[i] * 3 for i in range(nf)]).reshape(-1)
        mat_vals = np.ones(len(mat_rows))
        f2v_mat = sp.sparse.csr_matrix((mat_vals, (mat_rows, mat_cols)), shape=(nv, nf))
        vert_normals = sp.sparse.csr_matrix.dot(f2v_mat, face_normals)
        vert_normals = normalize(vert_normals, norm='l2', axis=1)

        return vert_normals
    
    def build_uni_lap(self):
        """compute uniform laplacian matrix"""
        vs = torch.tensor(self.vs.T, dtype=torch.float)
        edges = self.edges
        ve = self.ve

        sub_mesh_vv = [edges[v_e, :].reshape(-1) for v_e in ve]
        sub_mesh_vv = [set(vv.tolist()).difference(set([i])) for i, vv in enumerate(sub_mesh_vv)]

        num_verts = vs.size(1)
        mat_rows = [np.array([i] * len(vv), dtype=np.int64) for i, vv in enumerate(sub_mesh_vv)]
        mat_rows = np.concatenate(mat_rows)
        mat_cols = [np.array(list(vv), dtype=np.int64) for vv in sub_mesh_vv]
        mat_cols = np.concatenate(mat_cols)

        mat_rows = torch.from_numpy(mat_rows).long()
        mat_cols = torch.from_numpy(mat_cols).long()
        mat_vals = torch.ones_like(mat_rows).float() * -1.0
        neig_mat = torch.sparse.FloatTensor(torch.stack([mat_rows, mat_cols], dim=0),
                                            mat_vals,
                                            size=torch.Size([num_verts, num_verts]))
        vs = vs.T

        sum_count = torch.sparse.mm(neig_mat, torch.ones((num_verts, 1)).type_as(vs))
        mat_rows_ident = np.array([i for i in range(num_verts)])
        mat_cols_ident = np.array([i for i in range(num_verts)])
        mat_ident = np.array([-s for s in sum_count[:, 0]])
        mat_rows_ident = torch.from_numpy(mat_rows_ident).long()
        mat_cols_ident = torch.from_numpy(mat_cols_ident).long()
        mat_ident = torch.from_numpy(mat_ident).long()
        mat_rows = torch.cat([mat_rows, mat_rows_ident])
        mat_cols = torch.cat([mat_cols, mat_cols_ident])
        mat_vals = torch.cat([mat_vals, mat_ident])

        self.lapmat = torch.sparse.FloatTensor(torch.stack([mat_rows, mat_cols], dim=0),
                                            mat_vals,
                                            size=torch.Size([num_verts, num_verts]))
    
    def build_vf(self):
        vf = [set() for _ in range(len(self.vs))]
        for i, f in enumerate(self.faces):
            vf[f[0]].add(i)
            vf[f[1]].add(i)
            vf[f[2]].add(i)
        self.vf = vf
    
    def build_mesh_lap(self):
        """compute mesh laplacian matrix"""
        vs = self.vs
        vf = self.vf
        fa = self.fa
        edges = self.edges
        faces = self.faces
        e_dict = {}
        
        for e in edges:
            e0 = min(e)
            e1 = max(e)
            e_dict[(e0, e1)] = []
        for v in range(len(vs)):
            n_f = vf[v]
            for f in n_f:
                n_v = faces[f]
                if n_v[1] == v:
                    n_v = n_v[[1,2,0]]
                elif n_v[2] == v:
                    n_v = n_v[[2,1,0]]
                s = vs[n_v[1]] - vs[n_v[0]]
                t = vs[n_v[2]] - vs[n_v[1]]
                u = vs[n_v[0]] - vs[n_v[2]]
                i1 = np.inner(-s, t)
                i2 = np.inner(-t, u)
                n1 = np.linalg.norm(s) * np.linalg.norm(t)
                n2 = np.linalg.norm(t) * np.linalg.norm(u)
                c1 = np.clip(i1 / n1, -1.0, 1.0)
                c2 = np.clip(i2 / n2, -1.0, 1.0)
                cot1 = c1 / np.sqrt(1 - c1 ** 2)
                cot2 = c2 / np.sqrt(1 - c2 ** 2)
                keys1 = (min(n_v[0], n_v[1]), max(n_v[0], n_v[1]))
                keys2 = (min(n_v[0], n_v[2]), max(n_v[0], n_v[2]))
                if len(e_dict[keys1]) < 2:
                    e_dict[keys1].append(cot2)
                if len(e_dict[keys2]) < 2:
                    e_dict[keys2].append(cot1)
        for e in e_dict:
            e_dict[e] = -0.5 * (e_dict[e][0] + e_dict[e][1])
        
        C_ind = [[], []]
        C_val = []
        ident = [0] * len(vs)
        for e in e_dict:
            C_ind[0].append(e[0])
            C_ind[1].append(e[1])
            C_ind[0].append(e[1])
            C_ind[1].append(e[0])
            C_val.append(e_dict[e])
            C_val.append(e_dict[e])
            ident[e[0]] += -1.0 * e_dict[e]
            ident[e[1]] += -1.0 * e_dict[e]
        for i in range(len(vs)):
            C_ind[0].append(i)
            C_ind[1].append(i)
        C_val = C_val + ident
        C_ind = torch.LongTensor(C_ind)
        C_val = torch.FloatTensor(C_val)
        # cotangent matrix
        C = torch.sparse.FloatTensor(C_ind, C_val, torch.Size([len(vs), len(vs)]))

        M_ind = torch.stack([torch.arange(len(vs)), torch.arange(len(vs))], dim=0).long()
        M_val = []
        for v in range(len(vs)):
            faces = list(vf[v])
            va = 3.0 / (sum(fa[faces]) + 1e-12)
            M_val.append(va)
        M_val = torch.FloatTensor(M_val)
        # diagonal mass inverse matrix
        Minv = torch.sparse.FloatTensor(M_ind, M_val, torch.Size([len(vs), len(vs)]))
        #L = torch.sparse.mm(Minv, sm.to_dense())
        self.mesh_lap = C

    def build_div(self):
        vs = self.vs
        vn = self.vn
        faces = self.faces
        fn = self.fn
        fa = self.fa
        vf = self.vf
        grad_b = [[] for _ in range(len(vs))]
        for i, v in enumerate(vf):
            for t in v:
                f = faces[t]
                f_n = fn[t]
                a = fa[t]
                if f[1] == i:
                    f = [f[1], f[2], f[0]]
                elif f[2] == i:
                    f = [f[2], f[1], f[0]]
                x_kj = vs[f[2]] - vs[f[1]]
                x_kj = f_n * np.dot(x_kj, f_n) + np.cross(f_n, x_kj)
                x_kj /= 2
                grad_b[i].append(x_kj.tolist())

        div_v = [[] for _ in range(len(vn))]
        for i in range(len(vn)):
            tn = vn[i]
            g = np.array(grad_b[i])
            div_v[i] = np.sum(g, 0) * tn
        self.div = np.array(div_v)

    def poisson_mesh_edit(self):
        new_vs = []
        C = self.mesh_lap.to_dense()
        B = self.div
        # boundary condition
        C_add = torch.eye(len(self.vs))
        C = torch.cat([C, C_add], dim=0)
        B_add = torch.from_numpy(self.vs)
        B = torch.cat([torch.from_numpy(B), B_add], dim=0)
        A = torch.matmul(C.T, C)
        Ainv = torch.inverse(A)
        CtB = torch.matmul(C.T.float(), B.float())
        new_vs = torch.matmul(Ainv, CtB)

        return new_vs