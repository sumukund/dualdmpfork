import numpy as np
import torch
import torch.nn as nn
import copy
import datetime
import os
import sys
import random
import glob
import argparse
import json
import wandb
import util.loss as Loss
import util.models as Models
import util.datamaker as Datamaker
import pymeshlab as ml
from ray import tune
from ray.tune import CLIReporter
from ray.tune.suggest.bayesopt import BayesOptSearch
from ray.tune.schedulers import ASHAScheduler, MedianStoppingRule
from ray.tune.integration.wandb import WandbLogger, wandb_mixin
from functools import partial
from util.objmesh import ObjMesh
from util.datamaker import Dataset
from util.mesh import Mesh
from util.networks import PosNet, NormalNet, LightNormalNet, BigNormalNet

from torch.utils.tensorboard import SummaryWriter
from torch_geometric.data import Data

@wandb_mixin
def train(config):
    """ --- create dataset --- """
    os.chdir("/home/shota/DMP_adv")
    mesh_dic, dataset = Datamaker.create_dataset(FLAGS.input)
    gt_file, n_file, s_file, mesh_name = mesh_dic["gt_file"], mesh_dic["n_file"], mesh_dic["s_file"], mesh_dic["mesh_name"]
    gt_mesh, n_mesh, o1_mesh, s_mesh = mesh_dic["gt_mesh"], mesh_dic["n_mesh"], mesh_dic["o1_mesh"], mesh_dic["s_mesh"]
    dt_now = datetime.datetime.now()
    """ --- create model instance --- """
    device = torch.device('cuda:' + str(FLAGS.gpu) if torch.cuda.is_available() else 'cpu')
    #set_random_seed()
    posnet = PosNet(device).to(device)
    #set_random_seed()
    normnet = NormalNet(device).to(device)
    #normnet = BigNormalNet(device).to(device)
    optimizer_pos = torch.optim.Adam(posnet.parameters(), lr=FLAGS.pos_lr)

    norm_optimizers = {}
    norm_optimizers["SGD"] = torch.optim.SGD(normnet.parameters(), lr=FLAGS.norm_lr)
    norm_optimizers["Adam"] = torch.optim.Adam(normnet.parameters(), lr=FLAGS.norm_lr)
    norm_optimizers["RMSprop"] = torch.optim.RMSprop(normnet.parameters(), lr=FLAGS.norm_lr)
    norm_optimizers["Adadelta"] = torch.optim.Adadelta(normnet.parameters(), lr=FLAGS.norm_lr)
    norm_optimizers["AdamW"] = torch.optim.AdamW(normnet.parameters(), lr=FLAGS.norm_lr)

    optimizer_norm = norm_optimizers[FLAGS.norm_optim]
    scheduler_pos = torch.optim.lr_scheduler.StepLR(optimizer_pos, step_size=500, gamma=1.0)
    scheduler_norm = torch.optim.lr_scheduler.StepLR(optimizer_norm, step_size=500, gamma=1.0)

    """ --- output experimental conditions --- """
    log_dir = "./logs/" + mesh_name + dt_now.isoformat()
    writer = SummaryWriter(log_dir=log_dir)
    log_file = log_dir + "/condition.json"
    condition = {"PosNet": str(posnet).split("\n"), "NormNet": str(normnet).split("\n"), "optimizer_pos": str(optimizer_pos).split("\n"), "optimizer_norm": str(optimizer_norm).split("\n")}

    with open(log_file, mode="w") as f:
        l = json.dumps(condition, indent=2)
        f.write(l)

    os.makedirs("datasets/" + mesh_name + "/output", exist_ok=True)

    """ --- initial condition --- """
    min_mad = 1000
    min_dfrm = 1000
    min_rmse_norm = 1000
    min_rmse_pos = 1000
    init_mad = Loss.mad(n_mesh.fn, gt_mesh.fn)
    init_vn_loss = Loss.pos_rec_loss(n_mesh.vn, gt_mesh.vn)
    init_fn_loss = Loss.pos_rec_loss(n_mesh.fn, gt_mesh.fn)

    """ --- learning loop --- """
    for epoch in range(1, FLAGS.iter+1):
        #posnet.train()
        normnet.train()
        ##optimizer_pos.zero_grad()
        optimizer_norm.zero_grad()

        #pos = posnet(dataset)
        #loss_pos1 = Loss.pos_rec_loss(pos, n_mesh.vs)
        #loss_pos2 = Loss.mesh_laplacian_loss(pos, n_mesh)

        norm = normnet(dataset)
        loss_norm1 = Loss.norm_rec_loss(norm, n_mesh.fn)
        loss_norm2, new_fn = Loss.fn_bnf_loss(torch.from_numpy(n_mesh.vs).to(norm.device), norm, n_mesh)

        #fn2 = Models.compute_fn(pos, n_mesh.faces).float()

        #loss_pos3 = Loss.pos_norm_loss(pos, norm, n_mesh)
        
        loss = config["k3"] * loss_norm1 + config["k4"] * loss_norm2
        loss.backward()
        nn.utils.clip_grad_norm_(normnet.parameters(), FLAGS.grad_crip)
        #optimizer_pos.step()
        optimizer_norm.step()
        #scheduler_pos.step()
        scheduler_norm.step()

        # writer.add_scalar("pos1", loss_pos1, epoch)
        # writer.add_scalar("pos2", loss_pos2, epoch)
        # writer.add_scalar("pos3", loss_pos3, epoch)
        writer.add_scalar("norm1", loss_norm1, epoch)
        writer.add_scalar("norm2", loss_norm2, epoch)
        
        # report
        # o1_mesh.vs = pos.to('cpu').detach().numpy().copy()
        # Mesh.compute_face_normals(o1_mesh)
        # Mesh.compute_vert_normals(o1_mesh)
        norm_mad = Loss.mad(norm, gt_mesh.fn)
        tune.report(loss=norm_mad)
        wandb.log({"loss": norm_mad})


parser = argparse.ArgumentParser(description='DMP_adv for mesh')
parser.add_argument('-i', '--input', type=str, required=True)
parser.add_argument('--pos_lr', type=float, default=0.01)
parser.add_argument('--norm_lr', type=float, default=0.001)
parser.add_argument('--norm_optim', type=str, default='Adam')
parser.add_argument('--grad_crip', type=float, default=0.8)
parser.add_argument('--iter', type=int, default=1000)
parser.add_argument('--k1', type=float, default=1.0)
parser.add_argument('--k2', type=float, default=1.4)
parser.add_argument('--k3', type=float, default=1.0)
parser.add_argument('--k4', type=float, default=0.5)
parser.add_argument('--k5', type=float, default=1.0)
parser.add_argument('--gpu', type=int, default=0)
parser.add_argument('--ntype', type=str, default='hybrid')
FLAGS = parser.parse_args()

for k, v in vars(FLAGS).items():
    print('{:12s}: {}'.format(k, v))

config = {
    "k3": tune.uniform(3.0, 5.0),
    "k4": tune.uniform(0.1, 3.0),
    "wandb":{
        "project": "DMP_tune",
    }
}

# scheduler = MedianStoppingRule(
#     time_attr = "training_iteration",
#     metric="loss", mode="min",
#     grace_period=100,
#     min_samples_required=3,
# )

scheduler = ASHAScheduler(
    time_attr = "training_iteration",
    metric="loss", mode="min",
    max_t=FLAGS.iter,
    grace_period=100,
)

search_alg = BayesOptSearch(metric='loss', mode='min')

reporter = CLIReporter(
    metric_columns = ["loss", "training_iteration"],
    max_progress_rows=20,
    max_report_frequency=100,
)

ray_result = tune.run(
    train, config=config,
    resources_per_trial={"cpu":4, "gpu":2},
    num_samples=100,
    local_dir="./ray_results",
    search_alg=search_alg,
    scheduler=scheduler,
    progress_reporter=reporter,
    loggers=[WandbLogger],
)

best_trial = ray_result.get_best_trial("loss", "min", "last")
print('Best trial config: {}'.format(best_trial.config))
print('Best trial final validation loss: {}'.format(best_trial.last_result['loss']))