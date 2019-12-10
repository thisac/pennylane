# Copyright 2019 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
This module contains the CircuitGraph class which is used to generate a DAG (directed acyclic graph)
representation of a quantum circuit from an Operator queue.
"""
from collections import namedtuple, Counter
import networkx as nx

import numpy as np
from .utils import _flatten
import pennylane as qml


def _by_idx(x):
    """Sorting key for Operators: queue index aka temporal order.

    Args:
        x (Operator): node in the circuit graph
    Returns:
        int: sorting key for the node
    """
    return x.queue_idx


def _is_observable(x):
    """Predicate for deciding if an Operator instance is an observable.

    .. note::
       Currently some :class:`Observable` instances are not observables in this sense,
       since they can be used as gates as well.

    Args:
        x (Operator): node in the circuit graph
    Returns:
        bool: True iff x is an observable
    """
    return getattr(x, "return_type", None) is not None


Layer = namedtuple("Layer", ["ops", "param_inds"])
"""Parametrized layer of the circuit.

Args:

    ops (list[Operator]): parametrized operators in the layer
    param_inds (list[int]): corresponding free parameter indices
"""
# TODO define what a layer is

LayerData = namedtuple("LayerData", ["pre_ops", "ops", "param_inds", "post_ops"])
"""Parametrized layer of the circuit.

Args:
    pre_ops (list[Operator]): operators that precede the layer
    ops (list[Operator]): parametrized operators in the layer
    param_inds (tuple[int]): corresponding free parameter indices
    post_ops (list[Operator]): operators that succeed the layer
"""


class CircuitGraph:
    """Represents a quantum circuit as a directed acyclic graph.

    In this representation the :class:`~.Operator` instances are the nodes of the graph,
    and each directed edge represent a subsystem (or a group of subsystems) on which the two
    Operators act subsequently. This representation can describe the causal relationships
    between arbitrary quantum channels and measurements, not just unitary gates.

    Args:
        ops (Iterable[Operator]): quantum operators constituting the circuit, in temporal order
        variable_deps (dict[int, list[ParameterDependency]]): Free parameters of the quantum circuit.
            The dictionary key is the parameter index.
    """

    def __init__(self, ops, variable_deps):
        self.variable_deps = variable_deps

        self._grid = {}
        """dict[int, list[Operator]]: dictionary representing the quantum circuit as a grid.
        Here, the key is the wire number, and the value is a list containing the operators on that wire.
        """
        for k, op in enumerate(ops):
            op.queue_idx = k  # store the queue index in the Operator
            for w in set(
                _flatten(op.wires)
            ):  # flatten the nested wires lists of Tensor observables
                # Add op to the grid, to the end of wire w
                self._grid.setdefault(w, []).append(op)

        # TODO: State preparations demolish the incoming state entirely, and therefore should have no incoming edges.

        self._graph = nx.DiGraph()  #: nx.DiGraph: DAG representation of the quantum circuit
        # Iterate over each (populated) wire in the grid
        for wire in self._grid.values():
            # Add the first operator on the wire to the graph
            # This operator does not depend on any others
            self._graph.add_node(wire[0])

            for i in range(1, len(wire)):
                # For subsequent operators on the wire:
                if wire[i] not in self._graph:
                    # Add them to the graph if they are not already
                    # in the graph (multi-qubit operators might already have been placed)
                    self._graph.add_node(wire[i])

                # Create an edge between this and the previous operator
                self._graph.add_edge(wire[i - 1], wire[i])

    @property
    def observables_in_order(self):
        """Observables in the circuit, in a fixed topological order.

        The topological order used by this method is guaranteed to be the same
        as the order in which the measured observables are returned by the quantum function.
        Currently the topological order is determined by the queue index.

        Returns:
            list[Observable]: observables
        """
        nodes = [node for node in self._graph.nodes if _is_observable(node)]
        return sorted(nodes, key=_by_idx)

    observables = observables_in_order

    @property
    def operations_in_order(self):
        """Operations in the circuit, in a fixed topological order.

        Currently the topological order is determined by the queue index.

        The complement of :meth:`QNode.observables`. Together they return every :class:`Operator`
        instance in the circuit.

        Returns:
            list[Operation]: operations
        """
        nodes = [node for node in self._graph.nodes if not _is_observable(node)]
        return sorted(nodes, key=_by_idx)

    operations = operations_in_order

    @property
    def graph(self):
        """The graph representation of the quantum circuit.

        The graph has nodes representing :class:`.Operator` instances,
        and directed edges pointing from nodes to their immediate dependents/successors.

        Returns:
            networkx.DiGraph: the directed acyclic graph representing the quantum circuit
        """
        return self._graph

    def wire_indices(self, wire):
        """Operator indices on the given wire.

        Args:
            wire (int): wire to examine

        Returns:
            list[int]: indices of operators on the wire, in temporal order
        """
        return [op.queue_idx for op in self._grid[wire]]

    def ancestors(self, ops):
        """Ancestors of a given set of operators.

        Args:
            ops (Iterable[Operator]): set of operators in the circuit

        Returns:
            set[Operator]: ancestors of the given operators
        """
        return set().union(*(nx.dag.ancestors(self._graph, o) for o in ops)) - set(ops)

    def descendants(self, ops):
        """Descendants of a given set of operators.

        Args:
            ops (Iterable[Operator]): set of operators in the circuit

        Returns:
            set[Operator]: descendants of the given operators
        """
        return set().union(*(nx.dag.descendants(self._graph, o) for o in ops)) - set(ops)

    def _in_topological_order(self, ops):
        """Sorts a set of operators in the circuit in a topological order.

        Args:
            ops (Iterable[Operator]): set of operators in the circuit

        Returns:
            Iterable[Operator]: same set of operators, topologically ordered
        """
        G = nx.DiGraph(self._graph.subgraph(ops))
        return nx.dag.topological_sort(G)

    def ancestors_in_order(self, ops):
        """Operator ancestors in a topological order.

        Currently the topological order is determined by the queue index.

        Args:
            ops (Iterable[Operator]): set of operators in the circuit

        Returns:
            list[Operator]: ancestors of the given operators, topologically ordered
        """
        # return self._in_topological_order(self.ancestors(ops))  # an abitrary topological order
        return sorted(self.ancestors(ops), key=_by_idx)

    def descendants_in_order(self, ops):
        """Operator descendants in a topological order.

        Currently the topological order is determined by the queue index.

        Args:
            ops (Iterable[Operator]): set of operators in the circuit

        Returns:
            list[Operator]: descendants of the given operators, topologically ordered
        """
        return sorted(self.descendants(ops), key=_by_idx)

    def nodes_between(self, a, b):
        r"""Nodes on all the directed paths between the two given nodes.

        Returns the set of all nodes ``s`` that fulfill :math:`a \le s \le b`.
        There is a directed path from ``a`` via ``s`` to ``b`` iff the set is nonempty.
        The endpoints belong to the path.

        Args:
            a (Operator): initial node
            b (Operator): final node

        Returns:
            set[Operator]: nodes on all the directed paths between a and b
        """
        A = self.descendants([a])
        A.add(a)
        B = self.ancestors([b])
        B.add(b)
        return A & B

    @property
    def layers(self):
        """Identify the parametrized layer structure of the circuit.

        Returns:
            list[Layer]: layers of the circuit
        """
        # FIXME maybe layering should be greedier, for example [a0 b0 c1 d1] should layer as [a0 c1], [b0, d1] and not [a0], [b0 c1], [d1]
        # keep track of the current layer
        current = Layer([], [])
        layers = [current]

        # sort vars by first occurrence of the var in the ops queue
        variable_ops_sorted = sorted(self.variable_deps.items(), key=lambda x: x[1][0].op.queue_idx)

        # iterate over all parameters
        for param_idx, gate_param_tuple in variable_ops_sorted:
            # iterate over ops depending on that param
            for op, _ in gate_param_tuple:
                # get all predecessor ops of the op
                sub = self.ancestors((op,))

                # check if any of the dependents are in the
                # currently assembled layer
                if set(current.ops) & sub:
                    # operator depends on current layer, start a new layer
                    current = Layer([], [])
                    layers.append(current)

                # store the parameters and ops indices for the layer
                current.ops.append(op)
                current.param_inds.append(param_idx)

        return layers

    def iterate_layers(self):
        """Parametrized layers of the circuit.

        Returns:
            Iterable[LayerData]: layers with extra metadata
        """
        # iterate through each layer
        for ops, param_inds in self.layers:
            pre_queue = self.ancestors_in_order(ops)
            post_queue = self.descendants_in_order(ops)
            yield LayerData(pre_queue, ops, tuple(param_inds), post_queue)

    @staticmethod
    def list_at_index_or_none(list, idx):
        if len(list) > idx:
            return list[idx]
        else:
            return None

    @staticmethod
    def empty_list_to_none(list):
        if list:
            return list
        else:
            return [None]

    def greedy_layers(self):
        l = 0
        greedy_grid = self._grid.copy()

        greedy_grid = {
            wire: list(
                filter(
                    lambda op: not (
                        isinstance(op, qml.operation.Observable) and op.return_type is not None
                    ),
                    greedy_grid[wire],
                )
            )
            for wire in greedy_grid
        }

        while True:
            layer_ops = {
                wire: CircuitGraph.list_at_index_or_none(greedy_grid[wire], l)
                for wire in greedy_grid
            }
            num_ops = Counter(layer_ops.values())

            if None in num_ops and num_ops[None] == len(greedy_grid):
                break

            for (wire, op) in layer_ops.items():
                if op is None:
                    greedy_grid[wire].append(None)
                    continue

                # push back to next layer if not all args wires are there yet
                if op.num_wires > num_ops[op]:
                    greedy_grid[wire].insert(l, None)

            l += 1

        observables = {
            wire: CircuitGraph.empty_list_to_none(list(
                filter(
                    lambda op: isinstance(op, qml.operation.Observable)
                    and op.return_type is not None,
                    self._grid[wire],
                )
            ))
            for wire in self._grid
        }

        return [greedy_grid[wire] for wire in greedy_grid], [observables[wire] for wire in observables]

    def update_node(self, old, new):
        """Replaces the given circuit graph node with a new one.

        Args:
            old (Operator): node to replace
            new (Operator): replacement

        Raises:
            ValueError: if the new :class:`~.Operator` does not act on the same wires as the old one
        """
        # NOTE Does not alter the graph edges in any way. variable_deps is not changed, _grid is not changed. Dangerous!
        if new.wires != old.wires:
            raise ValueError("The new Operator must act on the same wires as the old one.")
        new.queue_idx = old.queue_idx
        nx.relabel_nodes(self._graph, {old: new}, copy=False)  # change the graph in place

    op_dict = {
        "PauliX": "X",
        "PauliY": "Y",
        "PauliZ": "Z",
        "Identity": "I",
        "Hadamard": "H",
    }

    def operator_string(self, op):
        name = op.name
        if name in self.op_dict:
            name = self.op_dict[name]

        if op.num_params == 0:
            return name

        return "{}({})".format(
            name,
            ",".join(
                [
                    str(par) if not isinstance(par, qml.variable.Variable) else par.render()
                    for par in op.params
                ]
            ),
        )

    def observable_string(self, obs):
        if obs.return_type == qml.operation.Expectation:
            return "<{}>".format(self.operator_string(obs))
        elif obs.return_type == qml.operation.Variance:
            return "Var[{}]".format(self.operator_string(obs))
        elif obs.return_type == qml.operation.Sample:
            return "Sample[{}]".format(self.operator_string(obs))

    def string_representation(self, op):
        if op is None:
            return "─"
        elif isinstance(op, qml.operation.Observable) and op.return_type is not None:
            return self.observable_string(op)
        elif isinstance(op, str):
            return op
        else:
            return self.operator_string(op)

    def build_string_representations(self, grid):
        grid_copy = grid.copy()
        j = 0

        # Transpose to work in layers
        grid = list(map(list, zip(*grid)))
        grid_copy = list(map(list, zip(*grid_copy)))

        # Iterate over all layers
        for i in range(len(grid)):
            layer_ops = set(grid[i])
            
            for op in layer_ops:
                if op is None:
                    continue

                if op.num_wires > 1:
                    additional = [None] * len(grid[0])
                    sorted_wires = op.wires.copy()
                    sorted_wires.sort()
                    additional[sorted_wires[0]] = "╗"
                    additional[sorted_wires[-1]] = "╝"
                    for k in range(sorted_wires[0] + 1, sorted_wires[-1]):
                        if k in sorted_wires:
                            additional[k] = "╣"
                        else:
                            additional[k] = "║"

                    grid_copy.insert(i + j + 1, additional)

                    j += 1

        grid = list(map(list, zip(*grid)))
        grid_copy = list(map(list, zip(*grid_copy)))

        return list(map(lambda l: list(map(self.string_representation, l)), grid_copy))

    def is_box(self, str):
        return str in ["╗", "╝", "╣", "║"]

    def justify_all(self, arr, width, fill_char, prepend=""):
        for i in range(len(arr)):
            arr[i] = prepend + str.ljust(arr[i], width, fill_char)

        return arr

    def render(self):
        grid, obs = self.greedy_layers()

        repr_grid = self.build_string_representations(grid)
        obs_repr = list(map(lambda l: list(map(self.string_representation, l)), obs))
        len_grid = list(map(lambda l: list(map(len, l)), repr_grid))
        obs_len = list(map(lambda l: list(map(len, l)), obs_repr))

        widths = np.max(len_grid, axis=0)

        repr_grid = list(map(list, zip(*repr_grid)))
        for i in range(len(widths)):
            if not any([self.is_box(repr) for repr in repr_grid[i]]):
                repr_grid[i] = self.justify_all(repr_grid[i], widths[i], "─", "──")
            else:
                repr_grid[i] = self.justify_all(repr_grid[i], widths[i], "─")

        repr_grid = list(map(list, zip(*repr_grid)))
        print(repr_grid)

        obs_width = np.max(obs_len)
        obs_repr = np.vectorize(lambda x: "┤" + x.ljust(obs_width, " "))(obs_repr)

        all_repr = np.hstack([repr_grid, obs_repr])

        for wire in range(len(all_repr)):
            print("{}: ──".format(wire), end="")

            for repr in all_repr[wire]:
                print("{}".format(repr), end="")

            print()
