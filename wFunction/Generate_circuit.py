import quimb.tensor as qtn
import qiskit as qs
from qiskit.quantum_info.operators import Operator
from qiskit.extensions.unitary import UnitaryGate
import numpy as np
import re
from collections import defaultdict
from . import interpolate as terp
from . import mps2qbitsgates as mpqb
from . import compress_algs as calgs
from . import mpo2qbitsgates as mqg
from .mps2qbitsgates import MPS2gates2
from .Chebyshev import controled_MPO
from qiskit.converters import circuit_to_gate
import typing
# import quantit as qtt
from jax.config import config
# import torch
config.update("jax_enable_x64", True)

TN = qtn.TensorNetwork

def qtens2operator(tens:qtn.Tensor):
    """ To transpose or not to transpose, that is the question."""
    # print(tens.tags)
    # print(tens.data.reshape(4,4))
    ar = np.array(tens.data).transpose([3,2,1,0]).reshape(4,4).conj()
    return Operator(ar)

def extract_layer_link(tags,regexp):
    for tag in tags:
        match = re.search(regexp,tag)
        if match:
            layer = match.group(1)
            link = match.group(2)
    return int(layer),int(link)

def extract_layer(inds,regexp):
    layer = int(re.search(regexp,inds[0]).group(1))
    layer = max(layer,int(re.search(regexp,inds[1]).group(1)))
    return layer

def extract_qbits(inds,regexp):
    qbits0 = int(re.search(regexp,inds[0]).group(1))
    qbits1 = qbits0
    for ind in inds:
        nqbits = int(re.search(regexp,ind).group(1))
        if abs(qbits0 - nqbits) > 1: #we always act on neighbour qbits.
            return None
        qbits0 = min(qbits0,nqbits)
        qbits1 = max(qbits1,nqbits)
    return qbits0,qbits1

def prep_list_dict(tn:TN):
    md = defaultdict(list)
    for t in tn:
        layer,link = extract_layer_link(t.tags,"O(\d+),(\d+)")
        tags = [tag for tag in t.tags]
        md[layer].append({"obj":qtens2operator(t), "qubits":((link),(link)+1),'label':tags[2]})
    return md

def net2circuit(net:TN,nqbits,registers,name):
    circuit = qs.QuantumCircuit(registers,name=name)
    op_dict = prep_list_dict(net)
    largest_key = max(op_dict.keys())
    # for layer in range(largest_key,-1,-1): #reverse order of application of the gates.
    for layer in range(largest_key+1):
        op_list = op_dict[layer]
        for op in op_list:
            circuit.unitary(**op)
    return circuit

def compute_Nlayer(net:TN,layer_rgx:typing.Pattern):
    max_layer = 0
    for tens in net:
        for tag in tens.tags:
                match = re.search(layer_rgx,tag)
                if match:
                    layer = match.group(1)
                max_layer = max(max_layer,int(layer))
    return max_layer+1

def reverse_net2circuit(net:TN,layer_tag:str,op_tag:str,register:qs.QuantumRegister,name:str):
    """
    converts a tensor network to a qiskit quantum circuit. Tensors must be tag in reverse order of layer and in forward order within a layer.
    """
    layer_rgx = re.compile(layer_tag.format('(\d+)'))
    Circ = qs.QuantumCircuit(register)
    # op_rgx = re.compile(op_tag.format('(\d+)'))
    nlayer = compute_Nlayer(net,layer_rgx)
    for l in reversed(range(nlayer)):
        Layer = net.select_any(layer_tag.format(l))
        for o in range(register.size-1):
            Op = Layer[op_tag.format(o)]
            Matrix = np.array(Op.data).transpose([3,2,1,0]).reshape(4,4)
            Qop = UnitaryGate(Operator(Matrix),layer_tag.format(l)+'_'+op_tag.format(o))
            Circ.append(Qop,[o,o+1])
    return Circ.reverse_bits()




def poly_by_part(f:callable,precision:float,nqbit,domain:tuple[float,float],qbmask:int=0,fulldomain=None,fullnqbits=None):
    """Recursive separation of the domain until the interpolation is able to reconstruct with a small enough error. Each polynomial in the return is paired with its bit domain"""
    if fulldomain is None:
        fulldomain = domain
    if fullnqbits is None:
        fullnqbits = nqbit
    qbdomain = (qbmask,qbmask+(1<<nqbit)-1)
    if nqbit > 1:
        poly = terp.interpolate(f,10,domain,domain)
        if (np.abs(f(domain[0])-poly(domain[0])) < precision and np.abs(f(domain[1])-poly(domain[1])) < precision ):
            return [(poly,qbdomain)]
        else:
            nqbit-=1
            midpoint = (domain[0]+domain[1])/2 
            leftdomain = (domain[0],midpoint)
            rightdomain=(midpoint,domain[1])
            leftbitmask = 1<<nqbit|qbmask
            return [*poly_by_part(f,precision,nqbit,leftdomain,qbmask,fulldomain,fullnqbits),*poly_by_part(f,precision,nqbit,rightdomain,leftbitmask,fulldomain,fullnqbits)]
    else:
        #we ran out of qbits... use a linear interpolation sampling the actual value the qbit can access.
        #There's no point in having a proper interpolation in this case.
        #We need to transform x0 to the nearest power of two greater, and x1 smaller
        x0,x1 = domain
        x0 = terp.bits2range(qbdomain[0],fulldomain,fullnqbits)
        x1 = terp.bits2range(qbdomain[1],fulldomain,fullnqbits)
        y0,y1 = f(x0),f(x1)
        poly = np.polynomial.Polynomial([(y1*x0-y0*x1)/(x0-x1),(y0-y1)/(x0-x1)],domain,domain)
        return [(poly,qbdomain)]

def Generate_MPS(f,MPS_precision,nqbit,domain):
    polys = poly_by_part(f,MPS_precision,nqbit,domain)
    mpses = [terp.polynomial2MPS(poly,nqbit,pdomain,domain) for poly,pdomain in polys]
    Norm2 = np.sum([m.H@m for m in mpses])
    return calgs.MPS_compressing_sum(mpses,Norm2,0.1*MPS_precision,MPS_precision)

def Generate_unitary_net(f,MPS_precision,Gate_precision,nqbit,domain,Nlayer,mps2gates = mpqb.MPS2Gates):
    mps = Generate_MPS(f,MPS_precision,nqbit,domain) 
    oc = mps.calc_current_orthog_center()[0]
    mps[oc]/= np.sqrt(mps[oc].H@mps[oc])#Set the norm to one, freshly computed to correct any norm error in the opimization
    unitary_set,Infidelity = mps2gates(mps,Gate_precision,Nlayer)
    # print(Infidelity)
    return unitary_set


def Generate_f_circuit(f,MPS_precision,Gate_precision,nqbit,domain,register,Nlayer,name="function_gate"):
    net = Generate_unitary_net(f,MPS_precision,Gate_precision,nqbit,domain,Nlayer,MPS2gates2)
    return reverse_net2circuit(net,'L{}','Op{}',register,name)

def Generate_f_gate(f,MPS_precision,Gate_precision,nqbit,domain,Nlayer,name="function_gate"):
    register = qs.QuantumRegister(nqbit)
    return circuit_to_gate(Generate_f_circuit(f,MPS_precision,Gate_precision,nqbit,domain,register,Nlayer,name))

# def Generate_g_circuit(f,MPO_precision,Gate_precision,nqbit,domain,register,Nlayer,endian="big",name="function_gate"):
#     a,b = domain
#     dtrans = lambda x :( (b-a) * x + b+a)/2
#     ff = lambda x: f(dtrans(x))
#     MPO_func = controled_MPO(ff,nqbit,MPO_precision,endian) 
#     gates,error = mqg.MPSO2Gates(MPO_func,Gate_precision,Nlayer)
#     circuit = net2circuit(gates,nqbit,register,name)
#     return circuit

# def Generate_g_gate(f,MPO_precision,Gate_precision,nqbit,domain,Nlayer,name="function_gate"):
#     register = qs.QuantumRegister(nqbit)
#     return circuit_to_gate(Generate_g_circuit(f,MPO_precision,Gate_precision,nqbit,domain,register,Nlayer,name))
    

if __name__=='__main__':
    # import mps2qbitsgates as mpqb 
    # import quantit as qtt
    import matplotlib.pyplot as plt
    import seaborn as sb
    sb.set_theme()
    import jax.numpy as jnp
    def f(x):
        return np.exp(-x**2)
    nqbit = 4
    Nlayer = 2
    domain = (-3,3)
    Gate_precision = 1e-12
    MPS_precision = 0.001
    register = qs.QuantumRegister(nqbit)
    circuit = Generate_f_circuit(f,MPS_precision,Gate_precision,register.size,domain,register,Nlayer)
    print(circuit)
    # polys = poly_by_part(f,precision,nqbit,domain)
    # for poly,bitdomain in polys:
    #     subdomain = (terp.bits2range(bitdomain[0],domain,nqbit),terp.bits2range(bitdomain[1],domain,nqbit))
    #     w = np.linspace(*subdomain,300)
    #     plt.plot(w,poly(w))
    # plt.show()
    # mpses = [terp.polynomial2MPS(poly,nqbit,pdomain,domain) for poly,pdomain in polys]
    # X = calgs.MPS_compressing_sum(mpses,0.1*precision,precision)
    # # X = qtt.networks.random_MPS(5,5,2)
    # qX = mpqb.qttMPS2quimbTN(X,'lfq')
    # qX.compress_all(inplace=True).compress_all(inplace=True)
    # qX /= jnp.sqrt((qX@qX.conj()))
    # O = mpqb.TwoqbitsPyramid(qX)
    # print(O)
    # O.draw()
    # reg,circuit = net2circuit(O,5)
    # print(circuit)
    # list_dict = prep_list_dict(O)
    # print(qi.TwoQubitBasisDecomposer( qs.extensions.UnitaryGate(list_dict[0][0])))
    # register = qs.QuantumRegister(nqbit)
    # gate = Generate_circuit(f,precision,nqbit,domain,register,"normalp=0.001")
    # print(gate)
    from qiskit.circuit import qpy_serialization
    with open('normal.qpy', 'wb') as fd:
        qpy_serialization.dump(circuit,fd)
