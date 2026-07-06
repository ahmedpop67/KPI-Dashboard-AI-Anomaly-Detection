"""
lstm_autoencoder/model.py — LSTM Autoencoder architecture for drift
detection.

Standard seq2seq autoencoder: an encoder LSTM compresses an input
sequence into a fixed-size latent vector (its final hidden state), and a
decoder LSTM reconstructs the sequence from that latent vector. Trained
only on "normal" sequences, it becomes good at reconstructing normal
patterns and comparatively bad at reconstructing patterns it's never
seen — that reconstruction error is the drift signal.

Loss: L = MSE(x, x_hat) = (1/T) * sum((x_t - x_hat_t)^2), per the
project's specified formula.
"""

import torch
import torch.nn as nn


class LSTMAutoencoder(nn.Module):
    def __init__(self, n_features: int, hidden_dim: int = 32, num_layers: int = 1) -> None:
        super().__init__()
        self.n_features = n_features
        self.hidden_dim = hidden_dim

        self.encoder = nn.LSTM(
            input_size=n_features, hidden_size=hidden_dim,
            num_layers=num_layers, batch_first=True,
        )
        self.decoder = nn.LSTM(
            input_size=hidden_dim, hidden_size=hidden_dim,
            num_layers=num_layers, batch_first=True,
        )
        self.output_layer = nn.Linear(hidden_dim, n_features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, n_features) -> reconstruction of same shape."""
        batch_size, seq_len, _ = x.shape

        _, (hidden, _) = self.encoder(x)
        latent = hidden[-1]  # (batch, hidden_dim) — final layer's hidden state

        decoder_input = latent.unsqueeze(1).repeat(1, seq_len, 1)
        decoder_output, _ = self.decoder(decoder_input)

        reconstruction = self.output_layer(decoder_output)
        return reconstruction
