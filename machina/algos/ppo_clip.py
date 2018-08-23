# Copyright 2018 DeepX Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
#
# This is an implementation of Proximal Policy Optimization
# in which gradient is clipped by the size especially.
# See https://arxiv.org/abs/1707.06347
# 

import torch
import torch.nn as nn
from machina.misc import logger

def make_pol_loss(pol, batch, clip_param, ent_beta):
    obs = batch['obs']
    acs = batch['acs']
    advs = batch['advs']
    init_hs = batch['init_hs']
    masks = batch['dones']
    old_llh = pol.pd.llh(
        batch['acs'],
        batch,
    )

    _, _, pd_params = pol(obs, init_hs, masks)
    new_llh = pol.pd.llh(acs, pd_params)
    ratio = torch.exp(new_llh - old_llh)
    pol_loss1 = ratio * advs
    pol_loss2 = torch.clamp(ratio, 1.0 - clip_param, 1.0 + clip_param) * advs
    pol_loss =  - torch.mean(torch.min(pol_loss1, pol_loss2))

    ent = pol.pd.ent(pd_params)
    pol_loss -= ent_beta * torch.mean(ent)

    return pol_loss

def update_pol(pol, optim_pol, batch, clip_param, ent_beta, max_grad_norm):
    pol_loss = make_pol_loss(pol, batch, clip_param, ent_beta)
    optim_pol.zero_grad()
    pol_loss.backward()
    torch.nn.utils.clip_grad_norm_(pol.parameters(), max_grad_norm)
    optim_pol.step()
    return pol_loss.detach().cpu().numpy()

def make_vf_loss(vf, batch, clip_param, clip=False):
    obs = batch['obs']
    rets = batch['rets']
    init_hs = batch['init_hs']
    masks = batch['dones']

    vs, _ = vf(obs, init_hs, masks)
    vfloss1 = (vs - rets)**2
    if clip:
        vpredclipped = vs + torch.clamp(vf(obs) - vs, -clip_param, clip_param)
        vfloss2 = (vpredclipped - rets)**2
        vf_loss = 0.5 * torch.mean(torch.max(vfloss1, vfloss2))
    else:
        vf_loss = 0.5 * torch.mean(vfloss1)
    return vf_loss

def update_vf(vf, optim_vf, batch, clip_param, clip, max_grad_norm):
    vf_loss = make_vf_loss(vf, batch, clip_param, clip)
    optim_vf.zero_grad()
    vf_loss.backward()
    torch.nn.utils.clip_grad_norm_(vf.parameters(), max_grad_norm)
    optim_vf.step()
    return vf_loss.detach().cpu().numpy()

def train(data, pol, vf,
        optim_pol, optim_vf,
        epoch, batch_size,# optimization hypers
        clip_param=0.2, ent_beta=1e-3,
        max_grad_norm=0.5,
        clip_vfunc=False
        ):

    pol_losses = []
    vf_losses = []
    logger.log("Optimizing...")
    for batch in data.iterate(batch_size, epoch):
        pol_loss = update_pol(pol, optim_pol, batch, clip_param, ent_beta, max_grad_norm)
        vf_loss = update_vf(vf, optim_vf, batch, clip_param, clip_vfunc, max_grad_norm)

        pol_losses.append(pol_loss)
        vf_losses.append(vf_loss)
    logger.log("Optimization finished!")

    return dict(PolLoss=pol_losses, VfLoss=vf_losses)
