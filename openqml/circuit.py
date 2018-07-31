# Copyright 2018 Xanadu Quantum Technologies Inc.
r"""
Quantum circuits
================

**Module name:** :mod:`openqml.circuit`

.. currentmodule:: openqml.circuit

Quantum circuits, implemented by the :class:`Circuit` class, are abstract representations of the programs that quantum computers and simulators can execute.
In OpenQML they are typically encapsulated inside :class:`QNode` instances in the computational graph.
Each OpenQML plugin typically :meth:`provides <openqml.plugin.PluginAPI.templates>` a few ready-made parametrized circuit templates (variational quantum circuits)
that can be used in quantum machine learning tasks, but the users can also build their own circuits
out of the :class:`GateSpec` instances the plugin :meth:`supports <openqml.plugin.PluginAPI.gates>`.


Classes
-------

.. autosummary::
   GateSpec
   Command
   ParRef
   Circuit
   QNode


QNode methods
-------------

.. currentmodule:: openqml.circuit.QNode

.. autosummary::
   evaluate
   gradient_finite_diff
   gradient_angle

.. currentmodule:: openqml.circuit

----
"""

import autograd.numpy as np
import autograd.extend

import logging as log
import numbers



__all__ = ['GateSpec', 'Command', 'ParRef', 'Circuit', 'QNode']


class GateSpec:
    """A type of quantum operation supported by a backend, and its properies.

    GateSpec is used to describe both unitary quantum gates and measurements/observables.

    Args:
      name  (str): name of the operation
      n_sys (int): number of subsystems it acts on
      n_par (int): number of real parameters it takes
      grad  (str): gradient computation method (generator, numeric?)
      par_domain (str): domain of the gate parameters: 'N': natural numbers (incl. zero), 'R': floats. Parameters outside the domain are truncated into it.
    """
    def __init__(self, name, n_sys=1, n_par=1, grad=None, *, par_domain='R'):
        self.name  = name   #: str: name of the gate
        self.n_sys = n_sys  #: int: number of subsystems it acts on
        self.n_par = n_par  #: int: number of real parameters it takes
        self.grad  = grad   #: str: gradient computation method (generator, numeric?)
        self.par_domain = par_domain  # str: domain of the gate parameters: 'N': natural numbers (incl. zero), 'R': floats

    def __str__(self):
        return self.name +': {} params, {} subsystems'.format(self.n_par, self.n_sys)


class Command:
    """Gate closure.

    Applying a given gate with given parameters on given subsystems.
    A quantum circuit can be described as a list of Commands.

    Args:
      gate (GateSpec): quantum operation to apply
      par (Sequence[float, int, ParRef]): parameter values
      reg (Sequence[int]): Subsystems to which the operation is applied. Note that the order matters here.
        TODO collections.OrderedDict to automatically avoid duplicate indices?
    """
    def __init__(self, gate, reg, par=[]):
        #if not isinstance(reg, Sequence):
        #    reg = [reg]
        if len(par) != gate.n_par:
            raise ValueError('Wrong number of parameters.')
        if len(reg) != gate.n_sys:
            raise ValueError('Wrong number of subsystems.')

        # convert fixed parameters into nonnegative integers if necessary,
        # it's up to the user to make sure the free parameters (ParRefs) have integer values when evaluating the circuit
        if gate.par_domain == 'N':
            def convert_par_to_N(p):
                if isinstance(p, ParRef):
                    return p
                if not isinstance(p, numbers.Integral):
                    p = int(p)
                    log.warning('Real parameter value truncated to int.')
                if p < 0:
                    p = 0
                    log.warning('Negative parameter value set to zero.')
                return p
            par = list(map(convert_par_to_N, par))

        self.gate = gate  #: GateSpec: quantum operation to apply
        self.par  = par   #: Sequence[float, ParRef]: parameter values
        self.reg  = reg   #: Sequence[int]: subsystems to which the operation is applied

    def __str__(self):
        return self.gate.name +'({}) | \t[{}]'.format(", ".join(map(str, self.par)), ", ".join(map(str, self.reg)))


class ParRef:
    """Parameter reference.

    Represents a circuit parameter with a non-fixed value.
    Each time the circuit is executed, it is given a vector of parameter values. ParRef is essentially an index into that vector.

    Args:
      idx (int): parameter index >= 0
    """
    def __init__(self, idx):
        self.idx = idx  #: int: parameter index

    def __str__(self):
        return 'ParRef: {}'.format(self.idx)


class Circuit:
    """Quantum circuit.

    The quantum circuit is described in terms of a list of :class:`Command` instances.
    The Commands must not be used elsewhere, as they are mutable and are sometimes written into.

    .. note::

       The `out` argument reflects the way Strawberry Fields currently stores measurement results
       in a classical variable associated with the mode being measured. This approach does not work if one wishes to measure
       the same subsystem several times during the circuit and retain all the results.

    Args:
      seq (Sequence[Command]): sequence of quantum operations to apply to the state
      name (str): circuit name
      out (None, Sequence[int]): Subsystem indices from which the circuit output array is constructed.
        The command sequence should contain a measurement for each subsystem listed here.
        None means the circuit returns no value.
    """
    def __init__(self, seq, name='', out=None):
        self.seq  = list(seq)  #: list[Command]:
        self.name = name  #: str: circuit name
        self.pars = {}    #: dict[int->list[Command]]: map from non-fixed parameter index to the list of Commands (in this circuit!) that depend on it
        self.out = out    #: Sequence[int]: subsystem indices for circuit output

        # TODO check the validity of the circuit?
        # count the subsystems and parameter references used
        subsys = set()
        for cmd in self.seq:
            subsys.update(cmd.reg)
            for p in cmd.par:
                if isinstance(p, ParRef):
                    self.pars.setdefault(p.idx, []).append(cmd)
        self.n_sys = len(subsys)  #: int: number of subsystems

        msg = "Circuit '{}': ".format(self.name)
        # remap the subsystem indices to a continuous range 0..n_sys-1
        if not self.check_indices(subsys, msg+'subsystems: '):
            # we treat the subsystem indices as abstract labels, but preserve their relative order nevertheless in case the architecture benefits from it
            m = dict(zip(sorted(subsys), range(len(subsys))))
            for cmd in self.seq:
                cmd.reg = [m[s] for s in cmd.reg]
            log.info(msg +'subsystem indices remapped.')

        # parameter indices must not contain gaps
        if not self.check_indices(self.pars.keys(), msg+'params: '):
            raise ValueError(msg +'parameter indices ambiguous.')


    @property
    def n_par(self):
        """Number of non-fixed parameters used in the circuit.

        Returns:
          int: number of non-fixed parameters
        """
        return len(self.pars)

    @staticmethod
    def check_indices(inds, msg):
        """Check if the given indices form a gapless range starting from zero.

        Args:
          inds (set[int]): set of indices

        Returns:
          bool: True if the indices are ok
        """
        if len(inds) == 0:
            return True
        ok = True
        if min(inds) < 0:
            log.warning(msg + 'negative indices')
            ok = False
        n_ind = max(inds) +1
        if n_ind > len(inds)+10:
            log.warning(msg + '> 10 unused indices')
            return False
        temp = set(range(n_ind))
        temp -= inds
        if len(temp) != 0:
            log.warning(msg + 'unused indices: {}'.format(temp))
            return False
        return ok

    def __str__(self):
        return "Quantum circuit '{}': len={}, n_sys={}, n_par={}".format(self.name, len(self), self.n_sys, self.n_par)

    def __len__(self):
        return len(self.seq)


class QNode:
    """Quantum node in the computational graph, encapsulating a circuit and a backend for executing it.

    Each quantum node is defined by a :class:`Circuit` instance representing the quantum program, and
    a :class:`~openqml.plugin.PluginAPI` instance representing the backend to execute it on.
    """
    def __init__(self, circuit, backend):
        self.circuit = circuit  #: Circuit: quantum circuit representing the program
        self.backend = backend  #: PluginAPI: backend for executing the program

    @autograd.extend.primitive
    def evaluate(self, params, **kwargs):
        """Evaluate the node.

        .. todo:: rename to __call__?

        .. todo:: Should we delete the backend state after the call to save memory?

        Args:
          params (Sequence[float]): circuit parameters
        Returns:
          vector[float]: (approximate) expectation value(s) of the measured observable(s)
        """
        return self.backend.execute_circuit(self.circuit, params, **kwargs)


    def gradient_finite_diff(self, params, which=None, h=1e-7, order=1, **kwargs):
        """Compute the gradient of the node using finite differences.

        Given an n-parameter quantum circuit, this function computes its gradient with respect to the parameters
        using the finite difference method.

        Args:
          params (Sequence[float]): point in parameter space at which to evaluate the gradient
          which  (Sequence[int], None): return the gradient with respect to these parameters. None means all.
          h (float): step size
          order (int): Finite difference method order, 1 or 2. The order-1 method evaluates the circuit at n+1 points of the parameter space,
            the order-2 method at 2n points.

        Returns:
          vector[float]: gradient vector
        """
        if which is None:
            which = range(len(params))
        which = set(which)  # make the indices unique
        params = np.asarray(params)
        grad = np.zeros(len(which))
        if order == 1:
            # value at the evaluation point
            x0 = self.backend.execute_circuit(self.circuit, params, **kwargs)
            for i, k in enumerate(which):
                # shift the k:th parameter by h
                temp = params.copy()
                temp[k] += h
                x = self.backend.execute_circuit(self.circuit, temp, **kwargs)
                grad[i] = (x-x0) / h
        elif order == 2:
            # symmetric difference
            for i, k in enumerate(which):
                # shift the k:th parameter by +-h/2
                temp = params.copy()
                temp[k] += 0.5*h
                x2 = self.backend.execute_circuit(self.circuit, temp, **kwargs)
                temp[k] = params[k] -0.5*h
                x1 = self.backend.execute_circuit(self.circuit, temp, **kwargs)
                grad[i] = (x2-x1) / h
        else:
            raise ValueError('Order must be 1 or 2.')
        return grad


    def gradient_angle(self, params, which=None, **kwargs):
        """Compute the gradient of the node using the angle method.

        Given an n-parameter quantum circuit, this function computes its gradient with respect to the parameters
        using the angle method. The method only works for one-parameter gates where the generator only has two unique eigenvalues.
        The circuit is evaluated twice for each incidence of each parameter in the circuit.

        Args:
          params (Sequence[float]): point in parameter space at which to evaluate the gradient
          which  (Sequence[int], None): return the gradient with respect to these parameters. None means all.

        Returns:
          vector[float]: gradient vector
        """
        if which is None:
            which = range(len(params))
        which = set(which)  # make the indices unique
        params = np.asarray(params)
        grad = np.zeros(len(which))
        n = self.circuit.n_par
        for i, k in enumerate(which):
            # find the Commands in which the parameter appears, use the product rule
            for cmd in self.circuit.pars[k]:
                if cmd.gate.n_par != 1:
                    raise ValueError('For now we can only differentiate one-parameter gates.')
                # we temporarily edit the Command so that parameter k is replaced by a new one,
                # which we can modify without affecting other Commands depending on the original.
                orig = cmd.par[0]
                assert(orig.idx == k)
                cmd.par[0] = ParRef(n)  # reference to a new, temporary parameter
                self.circuit.pars[n] = None  # we just need to add something to the map, it's not actually used
                # shift it by pi/2 and -pi/2
                temp = np.r_[params, params[k]+np.pi/2]
                x2 = self.backend.execute_circuit(self.circuit, temp, **kwargs)
                temp[-1] = params[k] -np.pi/2
                x1 = self.backend.execute_circuit(self.circuit, temp, **kwargs)
                # restore the original parameter
                cmd.par[0] = orig
                del self.circuit.pars[n]
                grad[i] += (x2-x1) / 2
        return grad


# define the vector-Jacobian product function for QNode.evaluate
#autograd.extend.defvjp(QNode.evaluate, lambda ans, self, params: lambda g: g * self.gradient_angle(params), argnums=[1])
autograd.extend.defvjp(QNode.evaluate, lambda ans, self, params: lambda g: g * self.gradient_finite_diff(params), argnums=[1])