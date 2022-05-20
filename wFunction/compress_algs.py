# import quantit as qtt
# import torch
import quimb.tensor as qtn
import quimb
import numpy as np
# from multimethod import multimethod
from typing import List

"""
Ce serait un exercice interessant de réimplmenter l'algo de compression avec quimb.
"""

# @multimethod
# def mpsmps_env_prep(mpsA:qtt.networks.MPS,mpsB:qtt.networks.MPS):
#     S = len(mpsA)+2
#     out = qtt.networks.MPT(len(mpsA)+2)
#     out[0] = torch.eye(mpsA[0].size()[0],mpsB[0].size()[0])
#     out[-1] = torch.eye(mpsA[-1].size()[2],mpsB[-1].size()[2])
#     for i in range(S-1,1,-1):
#         out[i-1] = mps_mps_right_env(mpsA[i-2],mpsB[i-2],out[i])
#     return out

# def mps_mps_right_env(tensA,tensB,env):
#     return torch.tensordot(tensB,torch.tensordot(env,tensA.conj(),dims=([1],[2])),dims=([1,2],[2,0]))
# def mps_mps_left_env(tensA,tensB,env):
#     tmp = torch.tensordot(env,tensB,dims=([0],[0]))
#     return torch.tensordot(tmp,tensA.conj(),dims=([0,1],[0,1]))

# def print_sizes(x:qtt.networks.MPS):
#     for t in x:
#         print(t.size(),end=",")
#     print("\n")

class Env_holder:
    """
    class to hold the MPTs that makes up the enviroments of a 1d-sweeping tensor algorithm.
    Takes care of the fiddling with the site index. The environment generated by the tensors at site i can be accessed by using [j,i] where j is the jth environment List
    """
    def __init__(self,env):
        self.env = env

    def __getitem__(self,i:tuple[int,int]):
        i,j = i
        return self.env[i][j+1]

    def __setitem__(self,i:tuple[int,int],value):
        i,j = i
        self.env[i][j+1] = value

# @multimethod
# def sum_sweep(MPSes:List[qtt.networks.MPS],target:qtt.networks.MPS,env:List[qtt.networks.MPT],direction:int,tol:float):
#     oc = target.orthogonality_center
#     #Loop from oc to end in direction and then back to oc.
#     Env = Env_holder(env)
#     if oc == 0:
#         direction = -1
#     if oc == len(target)-1:
#         direction = 1
#     while True:
#         direction  = direction - 2*(oc == (len(target)-1) or oc==0)*direction # change direction at N-2 or 1
#         # compute update by summing all [env_[i,j-1]]-[t_[i,j]] or [t_[i,j]-[env_[i,j+1]]]
            
#         # svd to extract psi_[j]
#         # update env at site j
#         # next site
#         if direction == 1:
#             Tens = torch.tensordot(torch.tensordot(torch.tensordot(Env[0,oc-1],MPSes[0][oc],dims=([0],[0])),MPSes[0][oc+1],dims=([2],[0])),Env[0,oc+2],dims=([3],[0]))
#             for i,t in enumerate(MPSes[1:]):
#                 Tens += torch.tensordot(torch.tensordot(torch.tensordot(Env[i+1,oc-1],t[oc],dims=([0],[0])),t[oc+1],dims=([2],[0])),Env[i+1,oc+2],dims=([3],[0]))
#             U,d,V = qtt.linalg.svd(Tens,split=2,tol=tol)
#             target[oc] = U
#             for i,t in enumerate(MPSes):
#                 Env[i,oc] = mps_mps_left_env(target[oc],t[oc],Env[i,oc-1])
#         else:
#             Tens = torch.tensordot(torch.tensordot(torch.tensordot(Env[0,oc-2],MPSes[0][oc-1],dims=([0],[0])),MPSes[0][oc],dims=([2],[0])),Env[0,oc+1],dims=([3],[0]))
#             for i,t in enumerate(MPSes[1:]):
#                 Tens += torch.tensordot(torch.tensordot(torch.tensordot(Env[i+1,oc-2],t[oc-1],dims=([0],[0])),t[oc],dims=([2],[0])),Env[i+1,oc+1],dims=([3],[0]))
#             U,d,V = qtt.linalg.svd(Tens,split=2,tol=tol)
#             target[oc] = V.conj().permute([2,0,1])
#             for i,t in enumerate(MPSes):
#                 Env[i,oc] = mps_mps_right_env(target[oc],t[oc],Env[i,oc+1])

#         oc += direction
#         if oc == target.orthogonality_center:
#             target[oc] = torch.zeros(Env[0,oc-1].size()[1],target[oc].size()[1],Env[0,oc+1].size()[1])
#             for i,t in enumerate(MPSes):
#                 target[oc] += torch.tensordot(torch.tensordot(Env[i,oc-1],t[oc],dims=([0],[0]) ),Env[i,oc+1],dims=([2],[0]) )
#             break
#     #compute state fidelity and return.
#     out = torch.tensordot(target[oc],target[oc].conj(),dims=([0,1,2],[0,1,2])).item()
#     return out

# @multimethod
def mpsmps_env_prep(mpsA:qtn.MatrixProductState,mpsB:qtn.MatrixProductState):
    outleft = []
    outleft.append(qtn.Tensor(data = 1,inds = ()))
    oc = mpsA.calc_current_orthog_center()
    if oc[0] == oc[1]:
        oc = oc[0]
    else:
        oc = mpsA.L-1
    for i in range(oc):
        outleft.append((outleft[-1]|mpsA[i]|mpsB[i]).contract())
    outright = []
    outright.append(qtn.Tensor(data = 1,inds = ()))
    for i in range(mpsA.L - oc - 1):
        outright.append((outright[-1]|mpsA[-i-1]|mpsB[-i-1]).contract())
    outright.reverse()
    return outleft+[qtn.Tensor()]+outright

# @multimethod
def sum_sweep(MPSes:List[qtn.MatrixProductState],target:qtn.MatrixProductState,envs,direction,tol,oc):
    Env = Env_holder(envs)
    starting_oc = oc
    L = target.L
    if oc == 0:
        direction = -1
    if oc == L-1:
        direction = 1
    while True:
        direction  = direction - 2*(oc == (L-1) or oc==0)*direction
        if direction == 1:
            Tens = (Env[0,oc-1]|MPSes[0][oc]|MPSes[0][oc+1]|Env[0,oc+2]).contract()
            for i,t in enumerate(MPSes[1:]):
                Tens += (Env[i+1,oc-1]|MPSes[i+1][oc]|MPSes[i+1][oc+1]|Env[i+1,oc+2]).contract()
            n = len(MPSes[0][oc+1].inds)-1
            U,d,V = qtn.tensor_split(Tens,right_inds=Tens.inds[-n:],left_inds=None,absorb=None,cutoff=tol)
            U.drop_tags()
            for tag in target[oc].tags:
                U.add_tag(tag)
            target[oc] = U
            for i,t in enumerate(MPSes):
                Env[i,oc] = (target[oc].H|t[oc]|Env[i,oc-1]).contract()
                assert(len(Env[i,oc].inds) == 2)
        else:
            Tens = (Env[0,oc-2]|MPSes[0][oc-1]|MPSes[0][oc]|Env[0,oc+1]).contract()
            for i,t in enumerate(MPSes[1:]):
                Tens += (Env[i+1,oc-2]|MPSes[i+1][oc-1]|MPSes[i+1][oc]|Env[i+1,oc+1]).contract()
            n = len(MPSes[0][oc-1].inds)-1
            U,d,V = qtn.tensor_split(Tens,left_inds=Tens.inds[:n],cutoff=tol,absorb=None)
            V.drop_tags()
            for tag in target[oc].tags:
                V.add_tag(tag)
            target[oc] = V
            for i,t in enumerate(MPSes):
                Env[i,oc] = (target[oc].H|t[oc]|Env[i,oc+1]).contract()
                assert(len(Env[i,oc].inds) == 2)
            
        oc += direction

        if oc == starting_oc:
            tags = target[oc].tags
            tmp = (Env[0,oc-1]| MPSes[0][oc]|Env[0,oc+1]).contract()
            for i,t in enumerate(MPSes[1:]):
                tmp += (Env[i+1,oc-1]|t[oc]|Env[i+1,oc+1]).contract()
            tmp.drop_tags()
            for tag in tags:
                tmp.add_tag(tag)
            target[oc] = tmp
            break
    out = target[oc]@target[oc].H
    return out

# @multimethod
def MPS_compressing_sum(MPSes:List[qtn.MatrixProductState],target_norm2,tol:float,crit:float):
    #check free indices are compatible across all input MPS
    mps0 = MPSes[0]
    N = mps0.L
    tens_arr = [np.random.rand(4,4,x.ind_size(mps0.site_ind_id.format(c))) for c,x in enumerate(mps0)]
    tens_arr[0] = tens_arr[0][0,:,:]
    tens_arr[-1] = tens_arr[-1][:,0,:]
    for mpsi in MPSes[1:]:
        assert(mpsi.L == N)
        c = 0
        for x in mpsi:
            s = x.ind_size(mpsi.site_ind_id.format(c))
            assert(s == tens_arr[c].shape[-1])
            c += 1
        mpsi.site_ind_id = mps0.site_ind_id

    # other shape format than lrp are buggy. it always convert to lrp, and it doesn't treat edge tensor correctly when converting.
    out = qtn.MatrixProductState(tens_arr,shape='lrp',site_ind_id=mps0.site_ind_id,site_tag_id='out{}')
    oc = out.calc_current_orthog_center()
    if oc[0] == oc[1]:
        oc = oc[0]
    else:
        oc = out.L-1
    envs = [mpsmps_env_prep(out,m) for m in MPSes]
    cost = 1.0e18
    new_cost = 0
    direction = 1
    iter_count = 0
    while True:
        sum_sweep_out = sum_sweep(MPSes,out,envs,direction,tol,oc)
        new_cost = target_norm2 - sum_sweep_out
        if new_cost < crit:
            break
        cost = new_cost
        iter_count += 1
        if (iter_count > 1000):
            print("Compressing sum failed to converge")
            break
    return out

# @multimethod
# def MPS_compressing_sum(MPSes:List[qtt.networks.MPS],target_norm2,tol:float,crit:float):
#     """ perform the sum of MPS and compress the result using a tol truncating SVD, stop when the fidelity is stationnary to the crit"""
#     length_MPS = len(MPSes[0])
#     out = qtt.networks.random_MPS(length_MPS,2,2)
#     out[0] = out[0][0:1,:,:]
#     out[-1] = out[-1][:,:,0:1]
#     out.move_oc(0)
#     assert(all([len(m)==length_MPS for m in MPSes]))
#     envs = [mpsmps_env_prep(out,m) for m in MPSes]
#     cost = 1.0e18
#     new_cost = 0
#     direction = 1
#     iter_count = 0
#     while True:
#         sum_sweep_out = sum_sweep(MPSes,out,envs,direction,tol)
#         new_cost = target_norm2 - sum_sweep_out
#         if new_cost < crit:
#             break
#         cost = new_cost
#         iter_count += 1
#         if (iter_count > 1000):
#             print("Compressing sum failed to converge")
#             break
#     return out

# def mps_operator_mps_left_env(mpsA:torch.Tensor,operator:torch.Tensor,mpsB:torch.Tensor,env):
#     out = torch.tensordot(env,mpsB,dims=([0],[0]))
#     out = torch.tensordot(out,operator,dims=([0,2],[0,3]))
#     out = torch.tensordot(out,mpsA.conj(),dims=([0,2],[0,1]))
#     return out

# def mps_operator_mps_right_env(mpsA:torch.Tensor,operator:torch.Tensor,mpsB:torch.Tensor,env):
#     out = torch.tensordot(env,mpsB,dims=([0],[2]))
#     out = torch.tensordot(out,operator,dims=([0,3],[2,3]))
#     out = torch.tensordot(out,mpsA.conj(),dims=([0,3],[2,1]))
#     return out

# def mpsoperatormps_env_prep(mpsA:qtt.networks.MPS,mpo:qtt.networks.MPO,mpsB:qtt.networks.MPS,oc):
#     S = len(mpsA)+2
#     out = qtt.networks.MPT(len(mpsA)+2)
#     out[0] = torch.tensordot(torch.eye(mpsA[0].size()[0],mpsB[0].size()[0]),torch.ones([1]),dims=([],[])).permute([0,2,1]).to(mpsA[0])
#     out[-1] = torch.tensordot(torch.eye(mpsA[-1].size()[2],mpsB[-1].size()[2]),torch.ones([1]),dims=([],[])).permute(0,2,1).to(mpsA[0])
#     for i in range(S-1,oc+1,-1):
#         out[i-1] = mps_operator_mps_right_env(mpsA[i-2],mpo[i-2],mpsB[i-2],out[i])
#     for i in range(1,oc+1):
#         out[i] = mps_operator_mps_right_env(mpsA[i-1],mpo[i-1],mpsB[i-1],out[i-1])
#     return out

# def three_terms_recursion(operator:qtt.netwoks.MPO,state_n:qtt.networks.MPS,state_nm1:qtt.networks.MPS,tol:float,crit:float):
#    length_MPS = len(state_n[0]) 
#    assert(len(state_n) == length_MPS)
#    assert(len(operator) == length_MPS)
#    out = qtt.networks.random_MPS
#    envs = [qtt.networks.MPT() for i in range(2)]
#    envs[0] = mps_operator_mps_left_env()
