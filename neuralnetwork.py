"""Small feed-forward policy network used by the active simulation."""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np


class NNetwork:
    """A ReLU multilayer perceptron with a softmax policy output."""

    @staticmethod
    def getTotalWeights(*layers):
        if len(layers) < 2 or any(type(layer) is not int or layer <= 0 for layer in layers):
            raise ValueError("network layers must be positive integers")
        return sum((layers[i] + 1) * layers[i + 1] for i in range(len(layers) - 1))

    def __init__(self, inputs, *layers, weights: Iterable[float] | None = None):
        if type(inputs) is not int or inputs <= 0:
            raise ValueError("network input count must be a positive integer")
        if not layers or any(type(layer) is not int or layer <= 0 for layer in layers):
            raise ValueError("network layers must be positive integers")
        self.input_count = inputs
        self.output_count = layers[-1]
        self.layers = []
        self.acts = []

        self.n_layers = len(layers)
        for i in range(self.n_layers):
            self.acts.append(self.act_relu)
            if i == 0:
                shape = (layers[0], inputs + 1)
            else:
                shape = (layers[i], layers[i - 1] + 1)
            # Explicit weights are used by the deterministic engine. Build a
            # non-random placeholder in that case so merely constructing a
            # policy never mutates NumPy's process-global RNG.
            self.layers.append(
                self.getInitialWeights(*shape) if weights is None else np.zeros(shape, dtype=float)
            )

        self.acts[-1] = self.acts_softmax
        if weights is not None:
            self.set_weights(weights)

    def getInitialWeights(self, n, m):
        return np.random.triangular(-1, 0, 1, size=(n, m))

    @staticmethod
    def act_relu(x):
        return np.maximum(x, 0.0)

    @staticmethod
    def act_th( x):
        return (x > 0).astype(float)

    @staticmethod
    def acts_softmax(x):
        e_x = np.exp(x - np.max(x))
        total = e_x.sum(axis=0)
        return e_x / total if total else np.full_like(x, 1.0 / len(x))

    def get_weights(self):
        return np.hstack([w.ravel() for w in self.layers]).copy()

    def set_weights(self, weights):
        values = np.asarray(list(weights), dtype=float)
        expected = self.getTotalWeights(self.input_count, *[layer.shape[0] for layer in self.layers])
        if values.ndim != 1 or len(values) != expected:
            raise ValueError("network weight count does not match architecture")
        if not np.isfinite(values).all():
            raise ValueError("network weights must be finite")
        off = 0
        for i, w in enumerate(self.layers):
            w_set = values[off:off + w.size]
            off += w.size
            self.layers[i] = np.array(w_set, dtype=float).reshape(w.shape)

    def _forward_with_trace(self, inputs: Sequence[float]):
        features = np.asarray(list(inputs), dtype=float)
        if features.ndim != 1 or len(features) != self.input_count or not np.isfinite(features).all():
            raise ValueError("network inputs do not match the architecture")
        activations = [features]
        pre_activations = []
        for i, w in enumerate(self.layers):
            pre_activation = w @ np.append(activations[-1], 1.0)
            pre_activations.append(pre_activation)
            activations.append(self.acts[i](pre_activation))
        return activations, pre_activations

    def predict(self, inputs):
        activations, _ = self._forward_with_trace(inputs)
        return activations[-1].copy()

    def learn(self, inputs, action_index: int, reward: float, learning_rate: float = 0.05):
        """Apply one reward-weighted policy-gradient update."""

        if type(action_index) is not int or not 0 <= action_index < self.output_count:
            raise ValueError("action index is outside the policy output")
        if not isinstance(reward, (int, float)) or not np.isfinite(reward):
            raise ValueError("reward must be finite")
        if not isinstance(learning_rate, (int, float)) or not 0 < learning_rate <= 1 or not np.isfinite(learning_rate):
            raise ValueError("learning rate must be in (0, 1]")

        activations, pre_activations = self._forward_with_trace(inputs)
        probabilities = activations[-1].copy()
        target = np.zeros(self.output_count, dtype=float)
        target[action_index] = 1.0
        delta = float(reward) * (target - probabilities)
        for i in range(len(self.layers) - 1, -1, -1):
            old_weights = self.layers[i].copy()
            self.layers[i] += float(learning_rate) * np.outer(delta, np.append(activations[i], 1.0))
            if i > 0:
                propagated = old_weights.T @ delta
                delta = propagated[:-1] * (pre_activations[i - 1] > 0)
        return probabilities
