# Copyright 2018 Xanadu Quantum Technologies Inc.

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
Integration tests for templates, including integration of passing outputs of initialization functions
in :mod:`pennylane.init`, and running templates in larger circuits.
"""
# pylint: disable=protected-access,cell-var-from-loop
import pytest
import pennylane as qml
from pennylane.templates.layers import (CVNeuralNetLayers, CVNeuralNetLayer,
                                        StronglyEntanglingLayers, StronglyEntanglingLayer,
                                        RandomLayers, RandomLayer)
from pennylane.init import (strong_ent_layers_uniform, strong_ent_layer_uniform,
                            strong_ent_layers_normal, strong_ent_layer_normal,
                            random_layers_uniform, random_layer_uniform,
                            random_layers_normal, random_layer_normal,
                            cvqnn_layers_uniform, cvqnn_layer_uniform,
                            cvqnn_layers_normal, cvqnn_layer_normal)


class TestParameterIntegration:
    """Tests integration with the parameter initialization functions from pennylane.init"""

    @pytest.mark.parametrize('parfun', [cvqnn_layers_uniform, cvqnn_layers_normal])
    def test_integration_cvqnn_layers(self, parfun, gaussian_device, n_subsystems, n_layers):
        """Checks that pennylane.init.cvqnn_layers_uniform() integrates
        with pennnylane.templates.layers.CVNeuralNetLayers()."""

        p = parfun(n_layers=n_layers, n_wires=n_subsystems)

        @qml.qnode(gaussian_device)
        def circuit(weights):
            CVNeuralNetLayers(*weights, wires=range(n_subsystems))
            return qml.expval(qml.Identity(0))

        circuit(weights=p)

    @pytest.mark.parametrize('parfun', [cvqnn_layer_uniform, cvqnn_layer_normal])
    def test_integration_cvqnn_layer(self, parfun, gaussian_device, n_subsystems):
        """Checks that parameters generated by methods from pennylane.init integrate
        with pennnylane.templates.layers.CVNeuralNetLayer()."""

        p = parfun(n_wires=n_subsystems)

        @qml.qnode(gaussian_device)
        def circuit(weights):
            CVNeuralNetLayer(*weights, wires=range(n_subsystems))
            return qml.expval(qml.Identity(0))

        circuit(weights=p)

    @pytest.mark.parametrize('parfun', [strong_ent_layers_uniform, strong_ent_layers_normal])
    def test_integration_stronglyentangling_layers(self, parfun, qubit_device, n_subsystems, n_layers):
        """Checks that parameters generated by methods from pennylane.init integrate
        with pennnylane.templates.layers.StronglyEntanglingLayers()."""

        p = parfun(n_layers=n_layers, n_wires=n_subsystems)

        @qml.qnode(qubit_device)
        def circuit(weights):
            StronglyEntanglingLayers(*weights, wires=range(n_subsystems))
            return qml.expval(qml.Identity(0))

        circuit(weights=p)

    @pytest.mark.parametrize('parfun', [strong_ent_layer_uniform, strong_ent_layer_normal])
    def test_integration_stronglyentangling_layer(self, parfun, qubit_device, n_subsystems):
        """Checks that parameters generated by methods from pennylane.init integrate
        with pennnylane.templates.layers.StronglyEntanglingLayer()."""

        p = parfun(n_wires=n_subsystems)

        @qml.qnode(qubit_device)
        def circuit(weights):
            StronglyEntanglingLayer(*weights, wires=range(n_subsystems))
            return qml.expval(qml.Identity(0))

        circuit(weights=p)

    @pytest.mark.parametrize('parfun', [random_layers_uniform, random_layers_normal])
    def test_integration_random_layers(self, parfun, qubit_device, n_subsystems, n_layers):
        """Checks that parameters generated by methods from pennylane.init integrate
        with pennnylane.templates.layers.RandomLayers()."""

        p = parfun(n_layers=n_layers, n_wires=n_subsystems)

        @qml.qnode(qubit_device)
        def circuit(weights):
            RandomLayers(*weights, wires=range(n_subsystems))
            return qml.expval(qml.Identity(0))

        circuit(weights=p)

    @pytest.mark.parametrize('parfun', [random_layer_uniform, random_layer_normal])
    def test_integration_random_layer(self, parfun, qubit_device, n_subsystems):
        """Checks that parameters generated by methods from pennylane.init integrate
        with pennnylane.templates.layers.RandomLayer()."""

        p = parfun(n_wires=n_subsystems)

        @qml.qnode(qubit_device)
        def circuit(weights):
            RandomLayer(*weights, wires=range(n_subsystems))
            return qml.expval(qml.Identity(0))

        circuit(weights=p)


class TestCircuitIntegration:
    """Tests the integration of templates into larger circuits."""
    #TODO